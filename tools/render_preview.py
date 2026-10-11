"""Render our own native window with synthetic history; no desktop capture."""
from pathlib import Path
import sys
import tempfile
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from desktop import Desktop
from scrobbler import App

def main():
    application = QApplication(sys.argv[:1])
    with tempfile.TemporaryDirectory() as directory:
        app = App(directory)
        ui = Desktop(app)
        ui.resize(1440, 1170)
        try:
            ui.show_sample()
            ui.select_ready()
            ui.show()
            for dark, name in [(False, "preview.png"), (True, "preview-dark.png")]:
                ui.dark.setChecked(dark)
                ui.toggle_appearance()
                for _ in range(6):
                    application.processEvents()
                    time.sleep(.03)
                ui.scene.tick()
                application.processEvents()
                assert ui.scene.renderer.available, ui.scene.renderer.error
                assert ui.grab().save(str(ROOT / "docs/images" / name))
        finally:
            ui.close()
            application.processEvents()
            app.db.close()

if __name__ == "__main__":
    main()
