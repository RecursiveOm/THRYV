import ipaddress
import os
import platform
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

# Fixed executables/flags. The only variable launch argument is a validated public URL.
APPLICATIONS = {
    "chrome": (
        ("/opt/google/chrome/google-chrome",),
        ("--new-window", "about:blank", "--ozone-platform=x11"),
        {"google-chrome", "google-chrome-stable"},
    ),
    "vscode": (
        ("/usr/share/code/code", "/usr/bin/code"),
        ("--new-window", "--ozone-platform=x11"),
        {"code"},
    ),
}


def trusted_executable(candidates):
    for candidate in candidates:
        path = Path(candidate).resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            continue
        # Reject executables or parent directories writable by unprivileged users.
        if any(p.stat().st_uid != 0 or p.stat().st_mode & 0o022 for p in (path, *path.parents)):
            continue
        return str(path)
    return None


class Windows:
    """Only window IDs/classes are inspected; titles and desktop contents are never read."""

    def __init__(self):
        from Xlib.display import Display

        self.display = Display()

    def matching(self, classes):
        prop = self.display.screen().root.get_full_property(
            self.display.intern_atom("_NET_CLIENT_LIST"), 0
        )
        found = set()
        for identifier in prop.value if prop else []:
            try:
                window = self.display.create_resource_object("window", int(identifier))
                names = window.get_wm_class() or ()
                if (
                    any(n.lower() in classes for n in names)
                    and window.get_attributes().map_state == 2
                ):
                    found.add(int(identifier))
            except Exception:
                continue  # A window may close while the list is read.
        return found

    def close(self):
        self.display.close()


def execute(tool, arguments, expires_at, *, project_path=None):
    if time.time() >= expires_at:
        return {"code": "timeout"}
    if tool == "get_system_info" and arguments == {}:
        system = platform.system()
        if system not in ("Linux", "Windows", "Darwin"):
            return {"code": "unsupported_platform"}
        machine = platform.machine()
        return {
            "code": "system_info",
            "platform": system,
            "architecture": machine if machine in ("x86_64", "aarch64", "arm64") else "unknown",
        }
    url = None
    if tool == "open_url":
        if not isinstance(arguments, dict) or set(arguments) != {"url"}:
            return {"code": "blocked"}
        url = arguments["url"]
        try:
            if (
                not isinstance(url, str)
                or len(url) > 2048
                or any(ord(c) <= 32 for c in url)
                or "\\" in url
            ):
                raise ValueError
            parsed = urlsplit(url)
            host = (parsed.hostname or "").encode("idna").decode("ascii")
            if (
                parsed.scheme not in {"https", "http"}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in {None, 80, 443}
                or host.endswith((".local", ".localhost", ".internal", ".test", "."))
            ):
                raise ValueError
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                if "." not in host:
                    raise ValueError from None
            else:
                if not address.is_global or address.is_multicast or address.is_reserved:
                    raise ValueError
        except (ValueError, UnicodeError):
            return {"code": "blocked"}
        arguments = {"application": "chrome"}
    if (
        tool not in {"open_application", "open_url"}
        or not isinstance(arguments, dict)
        or set(arguments) != {"application"}
        or not isinstance(arguments["application"], str)
        or arguments["application"] not in APPLICATIONS
    ):
        return {"code": "blocked"}
    if platform.system() != "Linux":
        return {"code": "unsupported_platform"}
    candidates, flags, classes = APPLICATIONS[arguments["application"]]
    if url:
        flags = tuple(url if flag == "about:blank" else flag for flag in flags)
    executable = trusted_executable(candidates)
    if not executable:
        return {"code": "application_missing"}
    windows = None
    try:
        windows = Windows()
        before = windows.matching(classes)
        if arguments["application"] in {"chrome", "vscode"}:
            # Existing native Wayland instances ignore X11 flags when forwarding a launch.
            # A dedicated, fixed local profile makes window verification reliable.
            profile_name = (
                "chrome-profile" if arguments["application"] == "chrome" else "vscode-profile"
            )
            profile = Path.home() / ".local/share/thryv-companion" / profile_name
            profile.mkdir(parents=True, exist_ok=True, mode=0o700)
            if profile.is_symlink() or profile.stat().st_uid != os.getuid():
                return {"code": "blocked"}
            profile.chmod(0o700)
            flags = (*flags, "--user-data-dir=" + str(profile))
            if arguments["application"] == "chrome":
                flags = (*flags, "--no-first-run", "--no-default-browser-check")
        if project_path is not None:
            if arguments["application"] != "vscode" or not Path(project_path).is_absolute():
                return {"code": "blocked"}
            flags = (*flags, "--disable-extensions", "--", project_path)
        # Reaping is bounded; the application remains owned by the desktop user.
        process = subprocess.Popen(
            [executable, *flags],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        deadline = min(expires_at, time.time() + 15)
        while time.time() < deadline:
            if windows.matching(classes) - before:
                process.poll()
                return {"code": "url_opened" if url else "application_opened"}
            if process.poll() not in (None, 0):
                return {"code": "launch_failed"}
            time.sleep(0.2)
        return {"code": "launch_unconfirmed"}
    except Exception:
        # Missing display access is not proof that a window opened.
        return {"code": "launch_unconfirmed"}
    finally:
        if windows:
            windows.close()
