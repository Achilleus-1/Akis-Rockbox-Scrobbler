"""Native widget integration with temporary storage and fake Last.fm replies."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import socket
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from desktop import Desktop
from scrobbler import App, AppError, Lastfm

class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(self.temp.name)
        self.ui = Desktop(self.app)

    def tearDown(self):
        self.ui.close()
        self.ui.deleteLater()
        self.application.processEvents()
        self.app.db.close()
        self.temp.cleanup()

    def import_track(self, title="Track", age=3600):
        self.app.dispatch("/api/import", {"content": f"Artist\tAlbum\t{title}\t1\t240\tL\t{int(time.time())-age}"})
        self.ui.refresh()

    def wait_task(self):
        deadline = time.monotonic() + 5
        while self.ui.busy or self.app.job["running"]:
            self.application.processEvents()
            self.ui.poll()
            if time.monotonic() > deadline:
                self.fail("Worker did not finish")
            time.sleep(.01)
        self.ui.refresh()

    def test_select_ready_respects_filter_and_never_selects_expired(self):
        self.import_track("Recent")
        self.import_track("Old", age=30*86400)
        self.import_track("Other")
        self.ui.search.setText("Recent")
        self.ui.select_ready()
        self.assertEqual([self.ui.rows[k]["track"] for k in self.ui.selected], ["Recent"])
        self.ui.search.clear()
        self.ui.select_ready()
        self.assertEqual(len(self.ui.selected), 2)
        self.assertFalse(self.ui.submit_button.isEnabled())

    def test_appearance_persists_without_changing_history(self):
        self.import_track()
        self.ui.dark.setChecked(True)
        self.ui.live.setChecked(False)
        self.ui.toggle_appearance()
        other = App(self.temp.name)
        try:
            self.assertTrue(other.preferences()["dark_mode"])
            self.assertFalse(other.preferences()["live_glass"])
            self.assertFalse(other.preferences()["remap_outdated"])
            self.assertEqual(len(other.state()["tracks"]), 1)
            self.assertTrue(self.ui.scene.dark)
            self.assertFalse(self.ui.scene.timer.isActive())
        finally:
            other.db.close()
        with self.assertRaises(AppError):
            self.app.dispatch("/api/appearance", {"dark_mode": True, "live_glass": "yes"})
        self.assertFalse(self.app.preferences()["live_glass"])

    def test_auth_worker_opens_official_authorization(self):
        self.app.credentials = {"api_key": "a"*32, "secret": "b"*32}
        self.ui.refresh()
        with patch.object(Lastfm, "call", return_value={"token": "opaque-token"}), patch("desktop.webbrowser.open") as browser:
            self.ui.connect()
            self.wait_task()
            self.assertTrue(self.app.pending_token)
            self.assertTrue(browser.call_args.args[0].startswith("https://www.last.fm/api/auth/?"))
            self.assertEqual(self.ui.connect_button.text(), "Finish connecting")
        with patch.object(Lastfm, "call", return_value={"session": {"key": "session", "name": "TestUser"}}):
            self.ui.connect()
            self.wait_task()
        self.assertIn("TestUser", self.ui.account.text())

    def test_submission_requires_confirmation_and_selected_account(self):
        self.import_track()
        self.app.credentials = {"api_key": "a"*32, "secret": "b"*32, "session_key": "session", "username": "TestUser"}
        self.ui.refresh()
        self.ui.select_ready()
        with patch.object(self.ui, "confirm", return_value=False), patch.object(Lastfm, "call") as client:
            self.ui.submit()
            client.assert_not_called()
        row = next(iter(self.ui.rows.values()))
        response = {"scrobbles": {"scrobble": {"timestamp": str(row["timestamp"]), "ignoredMessage": {"code": "0"}}}}
        with patch.object(self.ui, "confirm", return_value=True) as confirm, patch.object(Lastfm, "call", return_value=response) as client:
            self.ui.submit()
            self.wait_task()
            self.assertIn("TestUser", confirm.call_args.args[1])
            self.assertEqual(client.call_count, 1)
        self.assertEqual(next(iter(self.ui.rows.values()))["status"], "accepted")
        self.assertFalse(self.ui.selected)

    def test_sample_cannot_be_saved_or_submitted_even_when_connected(self):
        self.import_track()
        self.app.credentials = {"api_key": "a"*32, "secret": "b"*32, "session_key": "session", "username": "TestUser"}
        self.ui.show_sample()
        self.ui.select_ready()
        self.assertFalse(self.ui.submit_button.isEnabled())
        with patch.object(Lastfm, "call") as client:
            self.ui.submit()
            client.assert_not_called()
        self.assertEqual(len(self.app.state()["tracks"]), 1)
        self.ui.show_sample()
        self.assertEqual(len(self.ui.rows), 1)
        self.assertFalse(self.ui.selected)

    def test_native_ui_never_opens_listening_socket(self):
        with patch.object(socket.socket, "bind", side_effect=AssertionError("Unexpected server")):
            self.import_track()
            self.ui.dark.setChecked(True)
            self.ui.toggle_appearance()
            self.application.processEvents()

    def test_checkbox_and_row_details(self):
        self.import_track()
        item = self.ui.table.item(0, 0)
        item.setCheckState(Qt.CheckState.Checked)
        self.assertEqual(len(self.ui.selected), 1)
        self.ui.table.selectRow(0)
        self.assertIn("Original:", self.ui.detail.text())
        item.setCheckState(Qt.CheckState.Unchecked)
        self.assertFalse(self.ui.selected)
        self.ui.toggle_focused()
        self.assertEqual(len(self.ui.selected), 1)

    def test_fallback_and_animation_lifecycle(self):
        self.assertFalse(self.ui.scene.renderer.available)
        self.ui.show()
        self.application.processEvents()
        self.assertFalse(self.ui.grab().isNull())
        self.ui.hide()
        self.ui.scene.sync_animation()
        self.assertFalse(self.ui.scene.timer.isActive())
        self.ui.scene.dispose()
        self.assertTrue(self.ui.scene.disposed)

    def test_close_waits_for_operation(self):
        self.app.job["running"] = True
        with patch("desktop.QMessageBox.information") as prompt:
            self.ui.close()
            prompt.assert_called_once()
        self.assertFalse(self.ui.closed)
        self.app.job["running"] = False

if __name__ == "__main__":
    unittest.main()
