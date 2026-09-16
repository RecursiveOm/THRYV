"""Fixed development operations in disposable, network-isolated project snapshots."""

import atexit
import configparser
import hashlib
import os
import re
import resource
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from itertools import islice
from pathlib import Path

from thryv_companion.executor import trusted_executable
from thryv_companion.workspaces import LIMIT, Workspaces, sanitized

RUNNERS = {
    "python-server": ("python", "-m", "http.server"),
    "pytest": ("python", "-m", "pytest", "-q"),
    "unittest": ("python", "-m", "unittest", "discover"),
    "ruff": ("python", "-m", "ruff", "check", "."),
    "mypy": ("python", "-m", "mypy", "."),
    "python-build": ("python", "-m", "build", "--no-isolation"),
    "npm-test": ("/usr/bin/npm", "run", "test"),
    "make-test": ("/usr/bin/make", "test"),
    "make-lint": ("/usr/bin/make", "lint"),
    "make-build": ("/usr/bin/make", "build"),
    "npm-lint": ("/usr/bin/npm", "run", "lint"),
    "npm-types": ("/usr/bin/npm", "run", "typecheck"),
    "npm-build": ("/usr/bin/npm", "run", "build"),
    "npm-dev": ("/usr/bin/npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port"),
}
PROCESSES = {}


def limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))


def stop_process(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)


def close_servers():
    for item in list(PROCESSES.values()):
        stop_process(item["process"])
        item["snapshot"].cleanup()
    PROCESSES.clear()


atexit.register(close_servers)


def prune_servers(store):
    grants = store.grants()
    for identifier, item in list(PROCESSES.items()):
        if (
            item["workspace_id"] not in grants
            or item["expires_at"] <= time.time()
            or item["process"].poll() is not None
        ):
            stop_process(item["process"])
            item["snapshot"].cleanup()
            del PROCESSES[identifier]


def listening_ports(process):
    """Inspect only this process tree's private network namespace, never host connections."""
    host = os.readlink("/proc/self/ns/net")
    pending = [process.pid]
    ports = set()
    for _ in range(10):
        if not pending:
            break
        pid = pending.pop()
        try:
            children = Path(f"/proc/{pid}/task/{pid}/children").read_text()[:200]
            pending.extend(int(value) for value in children.split()[:10])
            if os.readlink(f"/proc/{pid}/ns/net") == host:
                continue
            for table in ("tcp", "tcp6"):
                with open(f"/proc/{pid}/net/{table}") as handle:
                    lines = handle.read(64000).splitlines()[1:]
                for line in lines:
                    fields = line.split()
                    if len(fields) > 3 and fields[3] == "0A":
                        ports.add(int(fields[1].split(":")[1], 16))
        except (OSError, ValueError):
            continue
    return sorted(ports)


def configure(store, identifier, name, runner, cwd="."):
    if runner not in RUNNERS or not re.fullmatch(r"[a-z][a-z0-9_-]{0,29}", name):
        raise ValueError("Choose a fixed runner and command name")
    if cwd != ".":
        with store.parent(identifier, cwd + "/placeholder"):
            pass
    with store.root(identifier):
        pass
    grants = store.grants()
    commands = grants[identifier].setdefault("commands", {})
    if len(commands) >= 12 and name not in commands:
        raise ValueError("Command limit reached")
    commands[name] = {"runner": runner, "cwd": cwd}
    store.save(grants)


def sandbox(store, identifier, cwd=".", git=False, network=False):
    executable = trusted_executable(["/usr/bin/bwrap"])
    if not executable:
        raise ValueError("Local bubblewrap sandbox is required")
    grant = store.grants().get(identifier)
    if not grant:
        raise ValueError("Workspace revoked")
    snapshot = tempfile.TemporaryDirectory(prefix="thryv-dev-")
    root = Path(snapshot.name) / "project"
    root.mkdir()
    size = 0
    try:
        for file in store.files(identifier):
            # Snapshots exclude protected and dependency paths; rejected files stay absent.
            try:
                data = store.read(identifier, file["path"])
            except (OSError, ValueError, UnicodeError):
                continue
            if data["redacted"]:
                continue
            size += data["size"]
            if size > 20_000_000:
                raise ValueError("Project snapshot size limit reached")
            target = root / file["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(data["content"])
        args = [
            executable,
            "--die-with-parent",
            "--unshare-all",
            "--new-session",
            "--cap-drop",
            "ALL",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/bin",
            "/bin",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/home",
            "--dir",
            "/home/runner",
            "--bind",
            str(root),
            "/workspace",
            "--clearenv",
            "--setenv",
            "PATH",
            "/runtime/bin:/usr/bin:/bin",
            "--setenv",
            "HOME",
            "/home/runner",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--setenv",
            "CI",
            "1",
            "--setenv",
            "GIT_TERMINAL_PROMPT",
            "0",
            "--setenv",
            "GIT_CONFIG_NOSYSTEM",
            "1",
        ]
        # A fixed Python runtime and read-only project dependencies; never mount the user's home.
        runtime = Path(sys.base_prefix).resolve()
        args += ["--ro-bind", str(runtime), "/runtime"]
        dependencies = []
        project = Path(grant["path"])
        for relative in ["node_modules", f"{cwd}/node_modules", ".venv/lib", f"{cwd}/.venv/lib"]:
            source = project / relative
            if (
                source.is_dir()
                and not source.is_symlink()
                and source.resolve().is_relative_to(project)
            ):
                destination = "/workspace/" + relative.removeprefix("./")
                args += ["--ro-bind", str(source), destination]
                if relative.endswith(".venv/lib"):
                    for package in source.glob("python*/site-packages"):
                        dependencies.append(destination + "/" + str(package.relative_to(source)))
        args += ["--setenv", "PYTHONPATH", ":".join(dependencies)]
        if git:
            source = project / ".git"
            if not source.is_dir() or source.is_symlink():
                raise ValueError("A standalone Git repository is required")
            args += ["--bind" if git == "write" else "--ro-bind", str(source), "/workspace/.git"]
            # Project-controlled Git config must not enable hooks, filters, pagers or helpers.
            read_git_config(project)
            clean = Path(snapshot.name) / "gitconfig"
            clean.write_text(
                "[core]\nrepositoryformatversion = 0\nbare = false\nfilemode = false\n"
            )
            args += [
                "--ro-bind",
                str(clean),
                "/workspace/.git/config",
                "--setenv",
                "GIT_CONFIG_NOSYSTEM",
                "1",
                "--setenv",
                "GIT_CONFIG_GLOBAL",
                "/dev/null",
            ]
            if (source / "config.worktree").exists():
                args += ["--ro-bind", "/dev/null", "/workspace/.git/config.worktree"]
            if network:
                args += ["--share-net", "--ro-bind", "/etc/ssl/certs", "/etc/ssl/certs"]
                agent = os.environ.get("SSH_AUTH_SOCK", "")
                if grant.get("git_ssh") and agent and Path(agent).is_socket():
                    known = Path.home() / ".ssh/known_hosts"
                    if (
                        not known.is_file()
                        or known.is_symlink()
                        or known.stat().st_size > 1_000_000
                    ):
                        raise ValueError("An existing verified GitHub SSH host key is required")
                    copied = Path(snapshot.name) / "known_hosts"
                    copied.write_bytes(known.read_bytes())
                    args += [
                        "--bind",
                        agent,
                        "/tmp/git-agent",
                        "--setenv",
                        "SSH_AUTH_SOCK",
                        "/tmp/git-agent",
                        "--ro-bind",
                        str(copied),
                        "/tmp/git-known-hosts",
                        "--setenv",
                        "GIT_SSH_COMMAND",
                        "/usr/bin/ssh -F /dev/null -o BatchMode=yes -o StrictHostKeyChecking=yes "
                        "-o UserKnownHostsFile=/tmp/git-known-hosts "
                        "-o GlobalKnownHostsFile=/dev/null",
                    ]
        work = "/workspace" + ("" if cwd == "." else "/" + cwd)
        if not (root / cwd).is_dir():
            raise ValueError("Configured working directory is unavailable")
        # Apply the process limit after entering the private user/PID namespace, so the
        # desktop user's existing threads cannot prevent sandbox creation.
        args += ["--chdir", work, "--", "/usr/bin/prlimit", "--nproc=64", "--as=8589934592", "--"]
        return snapshot, args
    except BaseException:
        snapshot.cleanup()
        raise


def capture(args, deadline, cancelled=lambda: False):
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        shell=False,
        start_new_session=True,
        close_fds=True,
        preexec_fn=limits,
    )
    output = bytearray()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    timed_out = False
    try:
        while process.poll() is None:
            if time.time() >= deadline or cancelled():
                timed_out = True
                stop_process(process)
                break
            for key, _ in selector.select(0.1):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                output.extend(chunk)
                if len(output) > LIMIT:
                    timed_out = True
                    stop_process(process)
                    break
        # Nonblocking drain avoids inherited-pipe hangs from child processes.
        os.set_blocking(process.stdout.fileno(), False)
        output.extend(process.stdout.read(LIMIT - min(len(output), LIMIT)) or b"")
    finally:
        stop_process(process)
        selector.close()
        process.stdout.close()
    return {
        "exit_code": process.returncode,
        "output": sanitized(output.decode("utf-8", "replace")),
        "interrupted": timed_out,
        "verified": process.returncode == 0 and not timed_out,
    }


def execute(store: Workspaces, tool, args, deadline, cancelled=lambda: False):
    identifier = str(uuid.UUID(args["workspace_id"]))
    with store.root(identifier):
        pass
    commands = store.grants()[identifier].get("commands", {})
    prune_servers(store)
    if tool == "development_processes" and set(args) == {"workspace_id"}:
        return {
            "processes": [
                {
                    "id": key,
                    "command": item["command"],
                    "configured_port": item["port"],
                    "listening_ports": listening_ports(item["process"]),
                    "port_scope": "isolated namespace; no host port exposed",
                    "running": item["process"].poll() is None,
                    "expires_at": item["expires_at"],
                }
                for key, item in PROCESSES.items()
                if item["workspace_id"] == identifier
            ]
        }
    if tool == "development_stop" and set(args) == {"workspace_id", "process_id"}:
        item = PROCESSES.get(args["process_id"])
        if not item or item["workspace_id"] != identifier:
            raise ValueError("Not a THRYV-owned process in this workspace")
        stop_process(item["process"])
        item["snapshot"].cleanup()
        del PROCESSES[args["process_id"]]
        return {"stopped_process": args["process_id"], "verified": True}
    if tool == "development_start" and set(args) == {"workspace_id", "command", "port"}:
        config = commands.get(args["command"])
        if (
            not config
            or config["runner"] not in {"npm-dev", "python-server"}
            or len(PROCESSES) >= 2
        ):
            raise ValueError("No approved server or process capacity")
        port = args["port"]
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("Invalid development port")
        snapshot, prefix = sandbox(store, identifier, config["cwd"])
        argv = list(RUNNERS[config["runner"]]) + [str(port)]
        if argv[0] == "python":
            argv[0] = "/runtime/bin/python3"
            argv += ["--bind", "127.0.0.1"]
        try:
            process = subprocess.Popen(
                prefix + argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                start_new_session=True,
                close_fds=True,
                preexec_fn=limits,
            )
        except BaseException:
            snapshot.cleanup()
            raise
        process_id = str(uuid.uuid4())
        PROCESSES[process_id] = {
            "process": process,
            "snapshot": snapshot,
            "workspace_id": identifier,
            "port": port,
            "command": args["command"],
            "expires_at": time.time() + 900,
        }
        time.sleep(0.2)
        return {
            "process_id": process_id,
            "running": process.poll() is None,
            "configured_port": port,
            "readiness_verified": False,
            "port_scope": "isolated namespace; no host port exposed",
        }
    if tool == "development_commands" and set(args) == {"workspace_id"}:
        return {"commands": commands, "sandbox": "local snapshot; no network or host writes"}
    if tool == "development_run" and set(args) == {"workspace_id", "command", "test_path"}:
        config = commands.get(args["command"])
        if not config or config["runner"] in {"npm-dev", "python-server"}:
            raise ValueError("Authorize this command locally first")
        argv = list(RUNNERS[config["runner"]])
        if argv[0] == "python":
            argv[0] = "/runtime/bin/python3"
        selected = args["test_path"]
        if selected:
            if config["runner"] != "pytest" or not re.fullmatch(r"[\w./-]+(?:::[\w]+)*", selected):
                raise ValueError("Only a relative pytest file/node selector is accepted")
            file = selected.split("::")[0]
            store.read(identifier, (config["cwd"] + "/" if config["cwd"] != "." else "") + file)
            argv.append(selected)
        snapshot, prefix = sandbox(store, identifier, config["cwd"])
        try:
            result = capture(prefix + argv, min(deadline, time.time() + 60), cancelled)
            return {
                **result,
                "command": args["command"],
                "cwd": config["cwd"],
                "isolated_snapshot": True,
            }
        finally:
            snapshot.cleanup()
    if tool == "workspace_git" and set(args) == {"workspace_id", "operation"}:
        operations = {
            "status": ["status", "--short"],
            "diff": ["diff", "--no-ext-diff", "--no-textconv"],
            "log": ["log", "-5", "--format=%h %s"],
            "branch": ["branch", "--show-current"],
        }
        if args["operation"] not in operations:
            raise ValueError("Blocked Git operation")
        snapshot, prefix = sandbox(store, identifier, git=True)
        try:
            result = capture(
                prefix
                + [
                    "/usr/bin/git",
                    "--no-pager",
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    "core.hooksPath=/dev/null",
                    *operations[args["operation"]],
                ],
                min(deadline, time.time() + 15),
                cancelled,
            )
            result["review_hash"] = review_hash(store, identifier)
            return result
        finally:
            snapshot.cleanup()
    if tool in {"workspace_git_write", "workspace_git_fetch"}:
        return git_change(store, identifier, tool, args, deadline, cancelled)
    raise ValueError("Blocked development operation")


def review_hash(store, identifier):
    entries = []
    for file in store.files(identifier):
        try:
            data = store.read(identifier, file["path"])
        except (OSError, ValueError, UnicodeError):
            continue
        entries.append((file["path"], data["sha256"]))
    # Include index and refs so an externally staged change/commit invalidates approval too.
    root = Path(store.grants()[identifier]["path"]) / ".git"
    for path in [
        root / "HEAD",
        root / "index",
        root / "packed-refs",
        *islice((root / "refs").glob("**/*"), 200),
    ]:
        if path.is_symlink():
            raise ValueError("Symbolic Git metadata is unsupported")
        if path.is_file():
            if path.stat().st_size > 8_000_000:
                raise ValueError("Git review size limit")
            entries.append(
                (str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest())
            )
    return hashlib.sha256(repr(entries).encode()).hexdigest()


def read_git_config(project):
    root = Path(project) / ".git"
    if root.is_symlink() or not root.is_dir():
        raise ValueError("A standalone Git repository is required")
    fd = os.open(root / "config", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as handle:
        import stat

        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 64000:
            raise ValueError("Unsafe Git configuration")
        content = handle.read(64001)
        if len(content) > 64000:
            raise ValueError("Unsafe Git configuration")
    config = configparser.RawConfigParser(strict=False)
    config.read_string(content)
    return config


def git_change(store, identifier, tool, args, deadline, cancelled):
    fetch = tool == "workspace_git_fetch"
    if set(args) != (
        {"workspace_id"}
        if fetch
        else {"workspace_id", "operation", "paths", "message", "branch", "review_hash"}
    ):
        raise ValueError("Invalid Git arguments")
    op = "fetch" if fetch else args["operation"]
    if op not in {"add", "commit", "fetch", "push"}:
        raise ValueError("Blocked Git mutation")
    if not fetch and review_hash(store, identifier) != args["review_hash"]:
        raise ValueError("Workspace changed since review; inspect it again")
    grant = store.grants()[identifier]
    config = read_git_config(grant["path"])
    network = op in {"fetch", "push"}
    snapshot, prefix = sandbox(store, identifier, git="write", network=network)
    command = [
        "/usr/bin/git",
        "--no-pager",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "credential.helper=",
        "-c",
        "http.followRedirects=false",
        "-c",
        "protocol.file.allow=never",
        "-c",
        "protocol.ext.allow=never",
    ]
    try:
        if op == "add":
            if not isinstance(args["paths"], list) or not 1 <= len(args["paths"]) <= 20:
                raise ValueError("Select files")
            for path in args["paths"]:
                if store.read(identifier, path)["redacted"]:
                    raise ValueError("Protected staged file")
            argv = ["add", "--", *args["paths"]]
        elif op == "commit":
            name = config.get("user", "name", fallback="").strip('"')
            email = config.get("user", "email", fallback="").strip('"')
            if not name or not email or any(ord(c) < 32 for c in name + email):
                raise ValueError("Configure repository Git user.name and user.email locally")
            # Reject protected paths and secret-bearing staged content before creating a commit.
            staged = capture(
                prefix + command + ["diff", "--cached", "--no-ext-diff", "--no-textconv"],
                deadline,
                cancelled,
            )
            from thryv_companion.workspaces import SECRET

            if (
                not staged["verified"]
                or "[REDACTED]" in staged["output"]
                or SECRET.search(args["message"])
            ):
                raise ValueError("Staged data is sensitive or exceeds review limits")
            names = capture(
                prefix + command + ["diff", "--cached", "--name-only"], deadline, cancelled
            )
            for path in names["output"].splitlines():
                with store.parent(identifier, path):
                    pass
            if not isinstance(args["message"], str) or not 1 <= len(args["message"]) <= 200:
                raise ValueError("Use a bounded commit message")
            argv = [
                "-c",
                "user.name=" + name,
                "-c",
                "user.email=" + email,
                "commit",
                "-m",
                args["message"],
            ]
        else:
            remote = config.get('remote "origin"', "url", fallback="")
            match = re.fullmatch(
                r"(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?", remote
            )
            if not match or ".." in match[1].split("/"):
                raise ValueError("Only the existing GitHub origin is supported")
            repo = match[1]
            agent = grant.get("git_ssh") and os.environ.get("SSH_AUTH_SOCK")
            remote = ("git@github.com:" if agent else "https://github.com/") + repo + ".git"
            if op == "push":
                if not agent:
                    raise ValueError(
                        "Authorize an existing Git SSH agent locally for authenticated push"
                    )
                branch = args["branch"]
                if (
                    not re.fullmatch(r"[A-Za-z0-9][\w./-]{0,99}", branch)
                    or ".." in branch
                    or branch.endswith("/")
                ):
                    raise ValueError("Invalid target branch")
                argv = [
                    "push",
                    remote,
                    "HEAD:refs/heads/" + branch,
                ]  # Never force, delete or push all refs.
            else:
                argv = ["fetch", "--no-tags", "--no-recurse-submodules", remote]
        result = capture(prefix + command + argv, min(deadline, time.time() + 45), cancelled)
        if result["verified"] and op == "commit":
            commit = capture(prefix + command + ["rev-parse", "HEAD"], deadline, cancelled)
            result["commit"] = commit["output"].strip()
        return result
    finally:
        snapshot.cleanup()
