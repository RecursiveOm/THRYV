"""Local, explicit workspace grants. No model-provided absolute path is trusted."""

import hashlib
import json
import os
import re
import stat
import uuid
from contextlib import contextmanager
from itertools import islice
from pathlib import Path

LIMIT = 48_000
PRIVATE = re.compile(
    r"(^\.env(?:\.|$)|^\.(?:git|ssh|aws|gnupg|config|local|codex)$|"
    r"credential|secret|token|password|^id_(?:rsa|ed25519|ecdsa)|\.(?:pem|key|p12|pfx|sqlite|db)$)",
    re.I,
)
SECRET = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----|"
    r"(?im:^.*(?:api[_-]?key|secret|password|access[_-]?token|refresh[_-]?token)\s*[:=].*$)|"
    r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{16,})\b"
)
SKIP = {"node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build"}


def sanitized(text):
    return SECRET.sub("[REDACTED]", text)[:LIMIT]


class Workspaces:
    def __init__(self, directory):
        self.path = Path(directory) / "workspaces.json"

    def grants(self):
        if not self.path.exists():
            return {}
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as handle:
            info = os.fstat(handle.fileno())
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("Workspace grants must be private")
            return json.load(handle)

    def save(self, grants):
        temporary = self.path.with_name("workspaces-" + uuid.uuid4().hex + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(grants, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def add(self, value):
        root = Path(value).expanduser().resolve(strict=True)
        info = root.stat()
        if (
            not root.is_dir()
            or info.st_uid != os.getuid()
            or root in (Path.home(), Path("/"))
            or any(PRIVATE.search(p) for p in root.parts)
            or str(root).startswith(("/etc/", "/proc/", "/sys/", "/dev/", "/usr/"))
        ):
            raise ValueError("Choose an owned project directory")
        grants = self.grants()
        for identifier, grant in grants.items():
            if grant["path"] == str(root):
                return identifier
        if len(grants) >= 20:
            raise ValueError("Workspace limit reached")
        identifier = str(uuid.uuid4())
        grants[identifier] = {
            "path": str(root),
            "name": root.name[:80],
            "inode": info.st_ino,
            "device": info.st_dev,
        }
        self.save(grants)
        return identifier

    def remove(self, identifier):
        grants = self.grants()
        grants.pop(identifier, None)
        self.save(grants)

    @contextmanager
    def root(self, identifier):
        grant = self.grants().get(identifier)
        if not grant:
            raise ValueError("Workspace not authorized locally")
        fd = os.open(grant["path"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != (grant["device"], grant["inode"]):
                raise ValueError("Workspace moved; authorize again")
            yield fd
        finally:
            os.close(fd)

    @contextmanager
    def parent(self, identifier, path):
        if not isinstance(path, str) or len(path) > 500 or "\\" in path or "\x00" in path:
            raise ValueError("Invalid path")
        parts = path.split("/")
        if any(p in ("", ".", "..") or PRIVATE.search(p) for p in parts):
            raise ValueError("Private or escaping path")
        with self.root(identifier) as root:
            fd = os.dup(root)
            try:
                for part in parts[:-1]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = child
                yield fd, parts[-1]
            finally:
                os.close(fd)

    def read(self, identifier, path):
        with self.parent(identifier, path) as (parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > LIMIT:
                    raise ValueError("Not a bounded regular file")
                raw = handle.read(LIMIT + 1)
        text = raw.decode("utf-8")
        if "\x00" in text or len(raw) > LIMIT:
            raise ValueError("Not a text file")
        return {
            "path": path,
            "content": sanitized(text),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
            "redacted": bool(SECRET.search(text)),
        }

    def write(self, identifier, path, content, expected):
        raw = content.encode("utf-8")
        if len(raw) > LIMIT or "\x00" in content or SECRET.search(content):
            raise ValueError("Oversized or sensitive content")
        with self.parent(identifier, path) as (parent, name):
            if expected:
                original = self.read(identifier, path)
                if original["sha256"] != expected or original["redacted"]:
                    raise ValueError("File changed or contains protected values")
            else:
                # Exclusive create never overwrites another actor's file.
                fd = os.open(
                    name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent
                )
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
                return {"path": path, "sha256": hashlib.sha256(raw).hexdigest()}
            # Compare again through the same directory descriptor before the atomic replacement.
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError("Unsafe edit target")
                if hashlib.sha256(handle.read(LIMIT + 1)).hexdigest() != expected:
                    raise ValueError("File changed")
            temporary = ".thryv-edit-" + uuid.uuid4().hex
            fd = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, info.st_mode & 0o777, dir_fd=parent
            )
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.rename(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
        return {"path": path, "sha256": hashlib.sha256(raw).hexdigest()}

    def files(self, identifier):
        found = []
        with self.root(identifier) as root:

            def visit(fd, prefix, depth):
                if depth > 8 or len(found) >= 500:
                    return
                with os.scandir(fd) as entries:
                    names = sorted(entry.name for entry in islice(entries, 1000))
                for name in names:
                    if PRIVATE.search(name) or name in SKIP or len(found) >= 500:
                        continue
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    path = prefix + name
                    if stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                        found.append({"path": path, "size": info.st_size})
                    elif stat.S_ISDIR(info.st_mode):
                        child = os.open(
                            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                        )
                        try:
                            visit(child, path + "/", depth + 1)
                        finally:
                            os.close(child)

            visit(root, "", 0)
        return found

    def execute(self, tool, args):
        identifier = str(uuid.UUID(args["workspace_id"]))
        if tool == "workspace_list" and set(args) == {"workspace_id"}:
            return {"files": self.files(identifier)}
        if tool in {"workspace_read", "workspace_metadata"} and set(args) == {
            "workspace_id",
            "path",
        }:
            result = self.read(identifier, args["path"])
            if tool == "workspace_metadata":
                result.pop("content")
            return result
        if tool == "workspace_write" and set(args) == {"workspace_id", "path", "content", "sha256"}:
            return self.write(identifier, args["path"], args["content"], args["sha256"])
        if tool == "workspace_search" and set(args) == {"workspace_id", "query"}:
            if not isinstance(args["query"], str) or not 1 <= len(args["query"]) <= 200:
                raise ValueError("Invalid search")
            matches = []
            for file in self.files(identifier):
                try:
                    content = self.read(identifier, file["path"])["content"]
                except (ValueError, OSError, UnicodeError):
                    continue
                for number, line in enumerate(content.splitlines(), 1):
                    if args["query"].casefold() in line.casefold():
                        matches.append({"path": file["path"], "line": number, "text": line[:300]})
                        if len(matches) >= 40:
                            return {"matches": matches, "truncated": True}
            return {"matches": matches}
        raise ValueError("Blocked workspace tool")
