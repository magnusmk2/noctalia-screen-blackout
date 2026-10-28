#!/usr/bin/env python3
"""Per-output black layers and cursor behavior for Noctalia on Hyprland."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import fcntl
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import socket
import subprocess
import sys
import time
import traceback


NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SCRIPT = Path(__file__).resolve()
HELPER = SCRIPT.with_name("blackout-layer")
CURSOR_INTERVAL = 0.2
LAYOUT_INTERVAL = 1.0
HIDE_TIMEOUT = 1.0
USAGE = "Usage: blackout.py list|blackout-all|restore-all|blackout <monitor>|restore <monitor>|toggle <monitor>|blackout-others <monitor>"


@lru_cache(maxsize=1)
def runtime_dir() -> Path:
    base = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    path = base / "noctalia-screen-blackout"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def pid_path(name: str) -> Path:
    if not NAME_RE.fullmatch(name):
        raise ValueError("Invalid monitor name")
    return runtime_dir() / f"{name}.pid"


def write_state(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(value) + "\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def control_lock():
    # Commands and watcher teardown share this lock so a new blackout cannot
    # race with the watcher deciding that the last blackout has disappeared.
    with (runtime_dir() / "control.lock").open("a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def hypr_request(command: str, *, as_json: bool = False):
    instance = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not instance:
        raise RuntimeError("No active Hyprland instance in the environment")
    base = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    address = base / "hypr" / instance / ".socket.sock"
    # Each request owns and promptly closes its socket. Never leave Hyprland's
    # synchronous request socket open while waiting between cursor samples.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(1.0)
        connection.connect(str(address))
        connection.sendall(f"{'j' if as_json else ''}/{command}".encode())
        chunks = []
        while chunk := connection.recv(65536):
            chunks.append(chunk)
    response = b"".join(chunks).decode()
    return json.loads(response) if as_json else response.strip()


def get_cursor_timeout() -> float:
    value = float(hypr_request("getoption cursor:inactive_timeout", as_json=True)["float"])
    if not math.isfinite(value) or not 0 <= value <= 20:
        raise ValueError("Invalid Hyprland cursor timeout")
    return value


def set_cursor_inactive_timeout(seconds: float) -> None:
    if not math.isfinite(seconds) or not 0 <= seconds <= 20:
        raise ValueError("Invalid cursor timeout")
    response = hypr_request(f"eval hl.config({{ cursor = {{ inactive_timeout = {seconds:g} }} }})")
    if response != "ok":
        raise RuntimeError(response or "Hyprland did not accept the cursor timeout")


def cursor_state_path() -> Path:
    return runtime_dir() / "cursor-state.json"


def cursor_watcher_path() -> Path:
    return runtime_dir() / "cursor-watch.pid"


def saved_cursor_timeout() -> float | None:
    path = cursor_state_path()
    try:
        saved = json.loads(path.read_text())
        if saved.get("instance") != os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            raise ValueError("Cursor state belongs to a previous session")
        value = float(saved["inactive_timeout"])
        if not math.isfinite(value) or not 0 <= value <= 20:
            raise ValueError("Invalid saved cursor timeout")
        return value
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        path.unlink(missing_ok=True)
        return None


def save_cursor_timeout(value: float) -> None:
    write_state(cursor_state_path(), {
        "instance": os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"),
        "inactive_timeout": value,
    })


def restore_cursor_timeout() -> None:
    value = saved_cursor_timeout()
    if value is not None:
        set_cursor_inactive_timeout(value)
        cursor_state_path().unlink(missing_ok=True)


def log_cursor_watcher(message: str) -> None:
    path = runtime_dir() / "cursor-watch.log"
    if path.exists() and path.stat().st_size > 1024 * 1024:
        path.replace(path.with_suffix(".log.1"))
    with path.open("a") as log:
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def cursor_watcher_pid() -> int | None:
    path = cursor_watcher_path()
    try:
        pid = int(path.read_text().strip())
        arguments = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        if str(SCRIPT).encode() in arguments and b"cursor-watch" in arguments:
            return pid
    except (OSError, ValueError):
        pass
    path.unlink(missing_ok=True)
    return None


def managed_pid(name: str) -> int | None:
    path = pid_path(name)
    try:
        pid = int(path.read_text().strip())
        # An atomically rebuilt binary leaves existing helpers with an exe
        # link ending in " (deleted)". They must remain restorable.
        executable = os.readlink(f"/proc/{pid}/exe").removesuffix(" (deleted)")
        arguments = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        if Path(executable).resolve() == HELPER and name.encode() in arguments:
            return pid
    except (OSError, ValueError):
        pass
    path.unlink(missing_ok=True)
    return None


def active_helpers() -> set[str]:
    return {
        path.stem for path in runtime_dir().glob("*.pid")
        if path != cursor_watcher_path() and NAME_RE.fullmatch(path.stem)
        and managed_pid(path.stem) is not None
    }


def sync_cursor_visibility() -> None:
    """Called with control_lock held after a mutating command."""
    active = active_helpers()
    watcher = cursor_watcher_pid()
    if active and watcher is None:
        with (runtime_dir() / "cursor-watch.log").open("ab") as log:
            process = subprocess.Popen(
                [sys.executable, str(SCRIPT), "cursor-watch"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log,
                start_new_session=True, close_fds=True,
            )
        write_state(cursor_watcher_path(), process.pid)
    elif not active and watcher is None:
        restore_cursor_timeout()


def monitored_outputs() -> list[dict]:
    return [monitor for monitor in hypr_request("monitors", as_json=True)
            if not monitor.get("disabled", False)]


def output_layout(monitors: list[dict]) -> list[dict]:
    outputs = []
    for monitor in monitors:
        name = monitor.get("name", "")
        if not NAME_RE.fullmatch(name):
            continue
        width = float(monitor.get("width", 0) or 0)
        height = float(monitor.get("height", 0) or 0)
        scale = float(monitor.get("scale", 1) or 1)
        if int(monitor.get("transform", 0) or 0) in {1, 3, 5, 7}:
            width, height = height, width
        if scale > 0:
            width /= scale
            height /= scale
        outputs.append({
            "name": name, "description": monitor.get("description", ""),
            "width": width, "height": height,
            "x": monitor.get("x", 0), "y": monitor.get("y", 0),
            "focused": monitor.get("focused", False),
        })
    return outputs


def get_outputs() -> list[dict]:
    outputs = output_layout(monitored_outputs())
    active = active_helpers()
    for output in outputs:
        output["active"] = output["name"] in active
    return outputs


def cursor_is_over_blackout(outputs: list[dict], active: set[str]) -> bool:
    x_text, y_text = hypr_request("cursorpos").split(",", 1)
    cursor_x, cursor_y = float(x_text), float(y_text)
    return any(
        output["name"] in active
        and output["x"] <= cursor_x < output["x"] + output["width"]
        and output["y"] <= cursor_y < output["y"] + output["height"]
        for output in outputs
    )


def cursor_watch() -> int:
    running = True

    def request_stop(_signal: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    with control_lock():
        existing = cursor_watcher_pid()
        if existing is not None and existing != os.getpid():
            return 0
        write_state(cursor_watcher_path(), os.getpid())
    log_cursor_watcher(f"started pid={os.getpid()}")
    try:
        last_timeout = get_cursor_timeout()
        original_timeout = saved_cursor_timeout()
        if original_timeout is None:
            original_timeout = last_timeout
            save_cursor_timeout(original_timeout)
        outputs = []
        next_layout = 0.0
        last_error = None
        while running:
            try:
                active = active_helpers()
                if not active:
                    with control_lock():
                        # Recheck under the same lock used for starting helpers.
                        if active_helpers():
                            continue
                        restore_cursor_timeout()
                        cursor_watcher_path().unlink(missing_ok=True)
                        return 0
                now = time.monotonic()
                if now >= next_layout:
                    outputs = output_layout(monitored_outputs())
                    observed_timeout = get_cursor_timeout()
                    if observed_timeout != last_timeout:
                        # Preserve a user/config change made while blackouts run.
                        original_timeout = observed_timeout
                        save_cursor_timeout(original_timeout)
                        last_timeout = observed_timeout
                    next_layout = now + LAYOUT_INTERVAL
                over_blackout = cursor_is_over_blackout(outputs, active)
                desired_timeout = HIDE_TIMEOUT if over_blackout else original_timeout
                if desired_timeout != last_timeout:
                    set_cursor_inactive_timeout(desired_timeout)
                    last_timeout = desired_timeout
                    log_cursor_watcher(f"cursor over blackout={over_blackout}; timeout={desired_timeout}")
                last_error = None
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                if error != last_error:
                    log_cursor_watcher(f"watch error: {error}")
                    last_error = error
                # If position cannot be determined, prefer the user's timeout.
                if last_timeout != original_timeout:
                    try:
                        set_cursor_inactive_timeout(original_timeout)
                        last_timeout = original_timeout
                    except (OSError, ValueError, RuntimeError):
                        # Keep watching through a temporary IPC failure; retry
                        # the restoration rather than leaving a dead watcher.
                        pass
            time.sleep(CURSOR_INTERVAL)
        return 0
    except Exception:
        log_cursor_watcher("watcher failed:\n" + traceback.format_exc())
        return 1
    finally:
        try:
            with control_lock():
                # A replacement may already have started after normal teardown.
                if cursor_watcher_pid() == os.getpid():
                    restore_cursor_timeout()
                    cursor_watcher_path().unlink(missing_ok=True)
        except Exception:
            log_cursor_watcher("cleanup failed:\n" + traceback.format_exc())
        log_cursor_watcher("stopped")


def focus_state() -> dict | None:
    path = runtime_dir() / "focus-state.json"
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    target = state.get("target") if isinstance(state, dict) else None
    previous = state.get("previous_active") if isinstance(state, dict) else None
    if not isinstance(target, str) or not NAME_RE.fullmatch(target) or not isinstance(previous, list):
        path.unlink(missing_ok=True)
        return None
    return {"target": target, "previous_active": [name for name in previous
            if isinstance(name, str) and NAME_RE.fullmatch(name)]}


def set_focus_state(target: str | None, previous_active: list[str] | None = None) -> None:
    path = runtime_dir() / "focus-state.json"
    if target is None:
        path.unlink(missing_ok=True)
    else:
        write_state(path, {"target": target, "previous_active": previous_active or []})


def launch(name: str, connected: set[str]) -> subprocess.Popen | None:
    if name not in connected:
        raise RuntimeError(f"Monitor {name} is not connected and active")
    if managed_pid(name) is not None:
        return None
    if not HELPER.is_file():
        raise RuntimeError(f"Blackout helper is missing; build it with {SCRIPT.with_name('build-helper.sh')}")
    with (runtime_dir() / f"{name}.log").open("ab") as log:
        process = subprocess.Popen(
            [str(HELPER), name], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=log, start_new_session=True, close_fds=True,
        )
    write_state(pid_path(name), process.pid)
    return process


def start_together(names: list[str], scope: str, connected: set[str]) -> None:
    pending = {}
    failures = []
    for name in names:
        try:
            process = launch(name, connected)
            if process is not None:
                pending[name] = process
        except Exception as exc:
            failures.append(f"{name}: {exc}")
    if pending:
        time.sleep(0.4)
    for name, process in pending.items():
        if process.poll() is not None:
            pid_path(name).unlink(missing_ok=True)
            details = (runtime_dir() / f"{name}.log").read_text(errors="replace")[-1200:]
            failures.append(f"{name}: {details.strip() or f'Blackout helper exited with status {process.returncode}'}")
    if failures:
        raise RuntimeError(f"Could not black out {scope}: " + "; ".join(failures))


def stop(name: str) -> None:
    pid = managed_pid(name)
    if pid is None:
        return
    try:
        descriptor = os.pidfd_open(pid)
    except ProcessLookupError:
        pid_path(name).unlink(missing_ok=True)
        return
    try:
        if managed_pid(name) != pid:
            return
        signal.pidfd_send_signal(descriptor, signal.SIGTERM)
        poller = select.poll()
        poller.register(descriptor, select.POLLIN)
        if not poller.poll(2000):
            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
            poller.poll(1000)
    except ProcessLookupError:
        pass
    finally:
        os.close(descriptor)
        pid_path(name).unlink(missing_ok=True)


def perform_action(action: str, name: str | None) -> int:
    if action == "restore-all":
        set_focus_state(None)
        # Recovery must not depend on a successful compositor/monitor query.
        for output in sorted(active_helpers()):
            stop(output)
        return 0
    if action == "restore":
        set_focus_state(None)
        stop(name)
        return 0
    if action == "toggle" and managed_pid(name) is not None:
        set_focus_state(None)
        stop(name)
        return 0
    if action == "blackout-others":
        state = focus_state()
        if state is not None and state["target"] == name:
            # Reverting a focus action clears all blackout layers. This also
            # restores screens that were already black when focus was chosen.
            for output in sorted(active_helpers()):
                stop(output)
            set_focus_state(None)
            return 0
    names = [monitor["name"] for monitor in monitored_outputs()
             if NAME_RE.fullmatch(monitor.get("name", ""))]
    connected = set(names)
    if action == "blackout-others":
        if name not in connected:
            raise RuntimeError(f"Monitor {name} is not connected and active")
        state = focus_state()
        previous = state["previous_active"] if state else sorted(active_helpers())
        stop(name)
        set_focus_state(name, previous)
        start_together([output for output in names if output != name], f"monitors other than {name}", connected)
    else:
        set_focus_state(None)
        start_together(names if action == "blackout-all" else [name], "every monitor" if action == "blackout-all" else name, connected)
    return 0


def main(argv: list[str]) -> int:
    if argv == ["cursor-watch"]:
        return cursor_watch()
    if argv == ["list"]:
        print(json.dumps(get_outputs()))
        return 0
    if not argv:
        raise ValueError(USAGE)
    action = argv[0]
    if action in {"blackout-all", "restore-all"} and len(argv) == 1:
        name = None
    elif action in {"blackout", "restore", "toggle", "blackout-others"} and len(argv) == 2:
        name = argv[1]
        if not NAME_RE.fullmatch(name):
            raise ValueError("Invalid monitor name")
    else:
        raise ValueError(USAGE)
    with control_lock():
        try:
            return perform_action(action, name)
        finally:
            sync_cursor_visibility()


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
