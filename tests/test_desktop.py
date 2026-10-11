"""Exercise the native UI with temporary storage and fake Last.fm replies."""
import socket
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from desktop import Desktop, THEMES
from scrobbler import App, AppError, Lastfm


class DesktopTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No graphical display: {exc}")
        self.root.withdraw()
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(self.temp.name)
        self.ui = Desktop(self.root, self.app)

    def tearDown(self):
        if hasattr(self, "ui"):
            self.root.after_cancel(self.ui.timer)
        if hasattr(self, "app"):
            self.root.destroy()
            self.app.db.close()
            self.temp.cleanup()

    def import_track(self, title="Track", age=3600):
        self.app.dispatch("/api/import", {"content": f"Artist\tAlbum\t{title}\t1\t240\tL\t{int(time.time())-age}"})
        self.ui.refresh()

    def wait_task(self):
        deadline = time.monotonic() + 5
        while self.ui.busy or self.app.job["running"]:
            self.root.update()
            if time.monotonic() > deadline:
                self.fail("Worker did not finish")
            time.sleep(0.01)
        self.ui.refresh()

    def test_select_ready_respects_filter_and_never_selects_expired(self):
        self.import_track("Recent")
        self.import_track("Old", age=30 * 86400)
        self.import_track("Other")
        self.ui.search.set("Recent")
        self.ui.select_ready()
        self.assertEqual([self.ui.rows[key]["track"] for key in self.ui.selected], ["Recent"])
        self.ui.search.set("")
        self.ui.select_ready()
        self.assertEqual(len(self.ui.selected), 2)
        self.assertEqual(str(self.ui.submit_button["state"]), "disabled")

    def test_theme_persists_across_restart_without_changing_history(self):
        self.import_track()
        self.ui.dark.set(True)
        self.ui.toggle_theme()
        other = App(self.temp.name)
        try:
            self.assertTrue(other.preferences()["dark_mode"])
            self.assertFalse(other.preferences()["remap_outdated"])
            self.assertEqual(len(other.state()["tracks"]), 1)
            self.assertEqual(self.ui.style.lookup("Treeview", "background"), THEMES[True]["panel"])
        finally:
            other.db.close()
        with self.assertRaises(AppError):
            self.app.dispatch("/api/appearance", {"dark_mode": "yes"})

    def test_auth_worker_returns_to_ui_and_opens_official_authorization(self):
        self.app.credentials = {"api_key": "a"*32, "secret": "b"*32}
        with patch.object(Lastfm, "call", return_value={"token": "opaque-token"}), patch("desktop.webbrowser.open") as browser:
            self.ui.connect()
            self.wait_task()
            self.assertTrue(self.app.pending_token)
            self.assertTrue(browser.call_args.args[0].startswith("https://www.last.fm/api/auth/?"))
            self.assertEqual(self.ui.connect_button["text"], "Finish connecting")
        with patch.object(Lastfm, "call", return_value={"session": {"key": "session", "name": "TestUser"}}):
            self.ui.connect()
            self.wait_task()
        self.assertIn("TestUser", self.ui.account.get())

    def test_submission_requires_confirmation_and_uses_selected_account(self):
        self.import_track()
        self.app.credentials = {"api_key": "a"*32, "secret": "b"*32, "session_key": "session", "username": "TestUser"}
        self.ui.refresh()
        self.ui.select_ready()
        with patch("desktop.messagebox.askyesno", return_value=False), patch.object(Lastfm, "call") as client:
            self.ui.submit()
            client.assert_not_called()
        row = next(iter(self.ui.rows.values()))
        response = {"scrobbles": {"scrobble": {"timestamp": str(row["timestamp"]), "ignoredMessage": {"code": "0"}}}}
        with patch("desktop.messagebox.askyesno", return_value=True) as confirm, patch.object(Lastfm, "call", return_value=response) as client:
            self.ui.submit()
            self.wait_task()
            self.assertIn("TestUser", confirm.call_args.args[1])
            self.assertEqual(client.call_count, 1)
        self.assertEqual(next(iter(self.ui.rows.values()))["status"], "accepted")
        self.assertFalse(self.ui.selected)

    def test_native_ui_never_opens_a_listening_socket(self):
        with patch.object(socket.socket, "bind", side_effect=AssertionError("Unexpected server")):
            self.import_track()
            self.ui.dark.set(True)
            self.ui.toggle_theme()
            self.root.update()

    def test_close_is_held_until_operation_finishes(self):
        self.app.job["running"] = True
        with patch("desktop.messagebox.showinfo") as prompt:
            self.ui.close()
            prompt.assert_called_once()
        self.assertFalse(self.ui.closed)
        self.app.job["running"] = False


if __name__ == "__main__":
    unittest.main()
