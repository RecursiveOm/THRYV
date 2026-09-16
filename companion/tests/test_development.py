import subprocess
import time

import pytest

from thryv_companion.development import configure, execute
from thryv_companion.workspaces import Workspaces


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    store = Workspaces(state)
    identifier = store.add(root)
    configure(store, identifier, "tests", "unittest")
    return root, store, identifier


def run(store, identifier, **kwargs):
    return execute(
        store,
        "development_run",
        {"workspace_id": identifier, "command": "tests", "test_path": "", **kwargs},
        time.time() + 20,
    )


def test_real_failure_edit_rerun_and_snapshot_confinement(project):
    root, store, identifier = project
    (root / "test_sample.py").write_text(
        "import unittest\nclass T(unittest.TestCase):\n"
        " def test_add(self): self.assertEqual(1+1,3)\n"
    )
    result = run(store, identifier)
    assert result["exit_code"] != 0 and "FAIL" in result["output"]
    original = store.read(identifier, "test_sample.py")
    store.write(
        identifier,
        "test_sample.py",
        original["content"].replace("1+1,3", "1+1,2"),
        original["sha256"],
    )
    result = run(store, identifier)
    assert result["verified"] and "OK" in result["output"]
    assert not (root / "__pycache__").exists()


def test_project_code_cannot_read_host_or_environment(project):
    root, store, identifier = project
    (root / ".env").write_text("PRIVATE=fixture-value")
    (root / "test_isolation.py").write_text("""import unittest, os, pathlib, socket
class T(unittest.TestCase):
 def test_boundary(self):
  self.assertFalse(pathlib.Path('/workspace/.env').exists())
  self.assertNotIn('DEEPSEEK_API_KEY', os.environ)
  self.assertFalse(pathlib.Path('/home/thryv').exists())
  with self.assertRaises(OSError): socket.create_connection(('1.1.1.1',443),timeout=.2)
""")
    result = run(store, identifier)
    assert result["verified"], result


def test_no_arbitrary_runner_arguments_or_unapproved_command(project):
    _, store, identifier = project
    with pytest.raises(ValueError):
        configure(store, identifier, "bad", "bash")
    with pytest.raises(ValueError):
        run(store, identifier, command="shell")
    with pytest.raises(ValueError):
        run(store, identifier, test_path="../../etc/passwd")


def test_git_actual_results_and_destructive_operation_rejection(project):
    root, store, identifier = project
    subprocess.run(["/usr/bin/git", "init", "-q", str(root)], check=True)
    (root / "main.py").write_text("print(1)")
    args = {"workspace_id": identifier, "operation": "status"}
    result = execute(store, "workspace_git", args, time.time() + 15)
    assert result["verified"] and "main.py" in result["output"]
    with pytest.raises(ValueError):
        execute(store, "workspace_git", {**args, "operation": "reset --hard"}, time.time() + 15)


def test_git_confirmed_stage_commit_and_stale_review(project):
    from thryv_companion.development import review_hash

    root, store, identifier = project
    subprocess.run(["/usr/bin/git", "init", "-q", str(root)], check=True)
    subprocess.run(["/usr/bin/git", "-C", str(root), "config", "user.name", "Fixture"], check=True)
    subprocess.run(
        ["/usr/bin/git", "-C", str(root), "config", "user.email", "fixture@example.com"], check=True
    )
    (root / "main.py").write_text("print(1)\n")
    args = {
        "workspace_id": identifier,
        "operation": "add",
        "paths": ["main.py"],
        "message": "",
        "branch": "",
        "review_hash": review_hash(store, identifier),
    }
    staged = execute(store, "workspace_git_write", args, time.time() + 20)
    assert staged["verified"], staged
    with pytest.raises(ValueError):
        execute(
            store,
            "workspace_git_write",
            {**args, "operation": "commit", "message": "Initial"},
            time.time() + 20,
        )
    committed = execute(
        store,
        "workspace_git_write",
        {
            **args,
            "operation": "commit",
            "message": "Initial",
            "review_hash": review_hash(store, identifier),
        },
        time.time() + 20,
    )
    assert committed["verified"] and len(committed["commit"]) == 40, committed


def test_server_ownership_stop_and_revoke_cleanup(project):
    from thryv_companion.development import PROCESSES, prune_servers

    root, store, identifier = project
    (root / "index.html").write_text("fixture")
    configure(store, identifier, "preview", "python-server")
    started = execute(
        store,
        "development_start",
        {"workspace_id": identifier, "command": "preview", "port": 8765},
        time.time() + 20,
    )
    assert started["running"] and started["readiness_verified"] is False
    process_id = started["process_id"]
    for _ in range(30):
        inspected = execute(
            store, "development_processes", {"workspace_id": identifier}, time.time() + 20
        )
        if 8765 in inspected["processes"][0]["listening_ports"]:
            break
        time.sleep(0.1)
    assert 8765 in inspected["processes"][0]["listening_ports"]
    with pytest.raises(ValueError):
        execute(
            store,
            "development_stop",
            {"workspace_id": identifier, "process_id": "not-owned"},
            time.time() + 20,
        )
    execute(
        store,
        "development_stop",
        {"workspace_id": identifier, "process_id": process_id},
        time.time() + 20,
    )
    assert process_id not in PROCESSES
    started = execute(
        store,
        "development_start",
        {"workspace_id": identifier, "command": "preview", "port": 8765},
        time.time() + 20,
    )
    process = PROCESSES[started["process_id"]]["process"]
    store.remove(identifier)
    prune_servers(store)
    assert process.poll() is not None and not PROCESSES


def test_git_config_rejects_symlinks_and_special_files(project):
    import os

    from thryv_companion.development import read_git_config

    root, _, _ = project
    (root / ".git").mkdir()
    secret = root / ".env"
    secret.write_text("PRIVATE=fixture")
    config = root / ".git/config"
    config.symlink_to(secret)
    with pytest.raises(OSError):
        read_git_config(root)
    config.unlink()
    os.mkfifo(config)
    with pytest.raises(ValueError):
        read_git_config(root)
