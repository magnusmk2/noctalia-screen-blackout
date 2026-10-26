"""Regression checks without changing the live desktop or pointer."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, call, patch

SPEC = importlib.util.spec_from_file_location("blackout", Path(__file__).resolve().parents[1] / "blackout.py")
blackout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(blackout)


class BlackoutChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="blackout-check-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {
            "XDG_RUNTIME_DIR": str(self.directory),
            "HYPRLAND_INSTANCE_SIGNATURE": "test-instance",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        blackout.runtime_dir.cache_clear()
        self.addCleanup(blackout.runtime_dir.cache_clear)

    def test_ipc_reads_chunked_reply_and_closes_connection(self):
        address = self.directory / "hypr/test-instance/.socket.sock"
        address.parent.mkdir(parents=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(server.close)
        server.bind(str(address))
        server.listen(1)
        received = []

        def respond():
            with server.accept()[0] as connection:
                received.append(connection.recv(1024))
                connection.sendall(b'{"float":')
                connection.sendall(b' 0.5}')

        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        self.assertEqual(blackout.hypr_request("getoption cursor:inactive_timeout", as_json=True), {"float": 0.5})
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(received, [b"j/getoption cursor:inactive_timeout"])

    def test_config_error_is_not_accepted_as_success(self):
        with patch.object(blackout, "hypr_request", return_value="keyword can't work with non-legacy parsers"):
            with self.assertRaises(RuntimeError):
                blackout.set_cursor_inactive_timeout(1)

    def test_invalid_cursor_values_never_reach_compositor(self):
        with patch.object(blackout, "hypr_request") as request:
            for value in [float("nan"), float("inf"), -1, 21]:
                with self.assertRaises(ValueError):
                    blackout.set_cursor_inactive_timeout(value)
            request.assert_not_called()

    def test_scaled_rotated_monitor_uses_logical_bounds(self):
        outputs = blackout.output_layout([{
            "name": "DP-2", "width": 2560, "height": 1440,
            "scale": 2, "transform": 1, "x": -720, "y": -80,
        }])
        self.assertEqual((outputs[0]["width"], outputs[0]["height"]), (720, 1280))
        with patch.object(blackout, "hypr_request", return_value="-1, 1199"):
            self.assertTrue(blackout.cursor_is_over_blackout(outputs, {"DP-2"}))
        with patch.object(blackout, "hypr_request", return_value="0, 1199"):
            self.assertFalse(blackout.cursor_is_over_blackout(outputs, {"DP-2"}))
        with patch.object(blackout, "hypr_request", return_value="-1, 1199"):
            self.assertFalse(blackout.cursor_is_over_blackout(outputs, set()))

    def test_previous_session_cursor_state_is_discarded(self):
        blackout.write_state(blackout.cursor_state_path(), {"instance": "old", "inactive_timeout": 1})
        with patch.object(blackout, "set_cursor_inactive_timeout") as setter:
            blackout.restore_cursor_timeout()
            setter.assert_not_called()
        self.assertFalse(blackout.cursor_state_path().exists())

    def test_corrupt_cursor_state_does_not_apply_invalid_lua(self):
        blackout.write_state(blackout.cursor_state_path(), {"instance": "test-instance", "inactive_timeout": "NaN"})
        with patch.object(blackout, "set_cursor_inactive_timeout") as setter:
            blackout.restore_cursor_timeout()
            setter.assert_not_called()

    def test_running_helper_remains_recognised_after_atomic_rebuild(self):
        blackout.write_state(blackout.pid_path("DP-1"), 123)
        original = Path.read_bytes
        def commandline(path):
            if str(path) == "/proc/123/cmdline":
                return f"{blackout.HELPER}\0DP-1\0".encode()
            return original(path)
        with patch.object(blackout.os, "readlink", return_value=str(blackout.HELPER) + " (deleted)"), patch.object(Path, "read_bytes", commandline):
            self.assertEqual(blackout.managed_pid("DP-1"), 123)

    def test_active_helper_scan_never_removes_watcher_marker(self):
        blackout.write_state(blackout.cursor_watcher_path(), 123)
        blackout.write_state(blackout.pid_path("DP-1"), 456)
        with patch.object(blackout, "managed_pid", return_value=456) as managed:
            self.assertEqual(blackout.active_helpers(), {"DP-1"})
            managed.assert_called_once_with("DP-1")
        self.assertTrue(blackout.cursor_watcher_path().exists())

    def test_restore_all_handles_disconnected_output_without_querying_hyprland(self):
        with patch.object(blackout, "active_helpers", return_value={"DP-1", "DP-99"}), patch.object(blackout, "stop") as stop, patch.object(blackout, "hypr_request") as request:
            blackout.perform_action("restore-all", None)
            self.assertEqual(stop.call_args_list, [call("DP-1"), call("DP-99")])
            request.assert_not_called()

    def test_blackout_all_queries_monitors_once_and_syncs_once(self):
        with patch.object(blackout, "monitored_outputs", return_value=[{"name": "DP-1"}, {"name": "DP-2"}]) as monitors, patch.object(blackout, "start_together") as start, patch.object(blackout, "sync_cursor_visibility") as sync:
            self.assertEqual(blackout.main(["blackout-all"]), 0)
            monitors.assert_called_once()
            start.assert_called_once_with(["DP-1", "DP-2"], "every monitor", {"DP-1", "DP-2"})
            sync.assert_called_once()

    def test_failed_batch_still_starts_watcher_for_successful_helpers(self):
        with patch.object(blackout, "perform_action", side_effect=RuntimeError("one output failed")), patch.object(blackout, "sync_cursor_visibility") as sync:
            with self.assertRaises(RuntimeError):
                blackout.main(["blackout-all"])
            sync.assert_called_once()

    def test_right_click_same_output_restores_previous_state(self):
        blackout.set_focus_state("DP-1", ["DP-3"])
        with patch.object(blackout, "monitored_outputs", return_value=[{"name": name} for name in ["DP-1", "DP-2", "DP-3"]]), patch.object(blackout, "stop") as stop, patch.object(blackout, "start_together") as start:
            blackout.perform_action("blackout-others", "DP-1")
            self.assertEqual(stop.call_args_list, [call("DP-1"), call("DP-2")])
            start.assert_called_once_with(["DP-3"], "the previous monitor state", {"DP-1", "DP-2", "DP-3"})
            self.assertIsNone(blackout.focus_state())

    def test_shutdown_uses_pidfd_and_does_not_wait_for_zombie_reaping(self):
        poller = Mock()
        poller.poll.return_value = [(88, 1)]
        with patch.object(blackout, "managed_pid", return_value=123), patch.object(blackout.os, "pidfd_open", return_value=88), patch.object(blackout.signal, "pidfd_send_signal") as send, patch.object(blackout.select, "poll", return_value=poller), patch.object(blackout.os, "close") as close:
            blackout.stop("DP-1")
            send.assert_called_once_with(88, signal.SIGTERM)
            poller.poll.assert_called_once_with(2000)
            close.assert_called_once_with(88)

    def watcher_patches(self, active_states, positions, *, current_timeout=0):
        def add(target, **kwargs):
            manager = patch.object(blackout, target, **kwargs)
            value = manager.start()
            self.addCleanup(manager.stop)
            return value
        add("cursor_watcher_pid", side_effect=lambda: os.getpid() if blackout.cursor_watcher_path().exists() else None)
        add("active_helpers", side_effect=active_states)
        add("get_cursor_timeout", return_value=current_timeout)
        add("monitored_outputs", return_value=[{"name": "DP-1", "width": 500, "height": 500}])
        add("hypr_request", side_effect=positions)
        add("log_cursor_watcher")
        sleep = patch.object(blackout.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        monotonic = patch.object(blackout.time, "monotonic", side_effect=[0, 0.2, 0.4, 0.6])
        monotonic.start()
        self.addCleanup(monotonic.stop)
        return add("set_cursor_inactive_timeout")

    def test_cursor_crossing_to_visible_screen_restores_timeout_and_stops_when_empty(self):
        setter = self.watcher_patches([{"DP-1"}, {"DP-1"}, set(), set()], ["20, 20", "600, 20"])
        self.assertEqual(blackout.cursor_watch(), 0)
        self.assertEqual(setter.call_args_list, [call(1), call(0), call(0)])
        self.assertFalse(blackout.cursor_state_path().exists())
        self.assertFalse(blackout.cursor_watcher_path().exists())

    def test_restarted_watcher_repairs_hidden_cursor_over_visible_screen(self):
        blackout.save_cursor_timeout(0)
        setter = self.watcher_patches([{"DP-1"}, set(), set()], ["600, 20"], current_timeout=1)
        self.assertEqual(blackout.cursor_watch(), 0)
        self.assertEqual(setter.call_args_list, [call(0), call(0)])

    def test_last_helper_disappearing_then_new_helper_starting_keeps_watcher_alive(self):
        setter = self.watcher_patches([set(), {"DP-1"}, {"DP-1"}, set(), set()], ["20, 20"])
        self.assertEqual(blackout.cursor_watch(), 0)
        self.assertEqual(setter.call_args_list, [call(1), call(0)])

    def test_cursor_query_failure_restores_user_timeout(self):
        setter = self.watcher_patches([{"DP-1"}, {"DP-1"}, set(), set()], ["20, 20", OSError("lost cursor query")])
        self.assertEqual(blackout.cursor_watch(), 0)
        self.assertEqual(setter.call_args_list, [call(1), call(0), call(0)])

    def test_temporary_restore_failure_does_not_kill_watcher(self):
        setter = self.watcher_patches(
            [{"DP-1"}, {"DP-1"}, {"DP-1"}, set(), set()],
            ["20, 20", OSError("lost cursor query"), "600, 20"],
        )
        setter.side_effect = [None, OSError("temporary IPC failure"), None, None]
        self.assertEqual(blackout.cursor_watch(), 0)
        self.assertEqual(setter.call_args_list, [call(1), call(0), call(0), call(0)])

    def test_user_timeout_change_is_preserved_on_exit(self):
        setter = self.watcher_patches(
            [{"DP-1"}, {"DP-1"}, set(), set()], ["20, 20", "600, 20"],
        )
        with patch.object(blackout, "get_cursor_timeout", side_effect=[0, 0, 3]), patch.object(blackout.time, "monotonic", side_effect=[0, 1.1]):
            self.assertEqual(blackout.cursor_watch(), 0)
        self.assertEqual(setter.call_args_list, [call(1), call(3)])

    def test_invalid_monitor_names_cannot_start_or_stop_anything(self):
        with patch.object(blackout, "perform_action") as action:
            for value in ["../DP-1", "DP-1;shutdown", "DP-1\nDP-2"]:
                with self.assertRaises(ValueError):
                    blackout.main(["blackout", value])
            action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
