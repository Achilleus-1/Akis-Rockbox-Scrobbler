"""Capture only our own native window with synthetic data, using Windows GDI."""
import ctypes
from ctypes import wintypes as wt
from pathlib import Path
import struct
import sys
import tempfile
import time
import tkinter as tk
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop import Desktop
from scrobbler import App


def capture(root, destination):
    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    user.GetDC.argtypes = [wt.HWND]
    user.GetDC.restype = wt.HDC
    user.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    user.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
    gdi.CreateCompatibleDC.argtypes = [wt.HDC]
    gdi.CreateCompatibleDC.restype = wt.HDC
    gdi.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype = wt.HBITMAP
    gdi.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
    gdi.SelectObject.restype = wt.HANDLE
    gdi.DeleteObject.argtypes = [wt.HANDLE]
    gdi.DeleteDC.argtypes = [wt.HDC]
    gdi.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
    user.GetParent.argtypes = [wt.HWND]
    user.GetParent.restype = wt.HWND
    root.update()
    hwnd, w, h = user.GetParent(root.winfo_id()), root.winfo_width(), root.winfo_height()
    source = user.GetDC(hwnd)
    dc = gdi.CreateCompatibleDC(source)
    bitmap = gdi.CreateCompatibleBitmap(source, w, h)
    original = gdi.SelectObject(dc, bitmap)
    try:
        if not user.PrintWindow(hwnd, dc, 3):
            raise ctypes.WinError(ctypes.get_last_error())
        gdi.SelectObject(dc, original)
        info = ctypes.create_string_buffer(struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, w*h*4, 0, 0, 0, 0))
        pixels = ctypes.create_string_buffer(w*h*4)
        if gdi.GetDIBits(dc, bitmap, 0, h, pixels, info, 0) != h:
            raise ctypes.WinError(ctypes.get_last_error())
        rgba = pixels.raw
        raw = bytearray()
        for y in range(h):
            raw.append(0)
            for x in range(w):
                at = (y*w+x)*4
                raw.extend((rgba[at+2], rgba[at+1], rgba[at]))
        def chunk(name, data):
            return struct.pack("!I", len(data)) + name + data + struct.pack("!I", zlib.crc32(name + data) & 0xffffffff)
        destination.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    finally:
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(dc)
        user.ReleaseDC(hwnd, source)


def main():
    if sys.platform != "win32":
        raise SystemExit("Preview capture uses Windows GDI.")
    with tempfile.TemporaryDirectory() as directory:
        app = App(directory)
        root = tk.Tk()
        try:
            now = int(time.time())
            demo = [("Björk", "Homogenic", "Jóga"), ("Daft Punk", "Discovery", "Digital Love"),
                    ("Aphex Twin", "Selected Ambient Works 85–92", "Xtal"),
                    ("Massive Attack", "Mezzanine", "Teardrop"), ("Air", "Moon Safari", "La femme d'argent"),
                    ("Boards of Canada", "Music Has the Right to Children", "Roygbiv"),
                    ("Radiohead", "In Rainbows", "Reckoner"), ("Portishead", "Dummy", "Glory Box")]
            app.dispatch("/api/import", {"filename": ".scrobbler.log", "content": "\n".join(f"{artist}\t{album}\t{title}\t1\t240\tL\t{now-3600-i*300}" for i, (artist, album, title) in enumerate(demo))})
            ui = Desktop(root, app)
            ui.status.set("Preview with synthetic listening history · connect Last.fm to scrobble.")
            for key in list(ui.rows)[:3]:
                ui.toggle(key)
            for dark, filename in [(False, "preview.png"), (True, "preview-dark.png")]:
                ui.dark.set(dark)
                ui.toggle_theme()
                root.withdraw()
                root.deiconify()
                root.update()
                time.sleep(0.3)
                root.update()
                capture(root, ROOT / "docs" / "images" / filename)
        finally:
            root.destroy()
            app.db.close()


if __name__ == "__main__":
    main()
