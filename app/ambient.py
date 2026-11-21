"""
ambient.py - Screen ambient lighting: keys take the colour of the screen above them.

Samples the screen with GDI StretchBlt into a tiny bitmap (no capture libraries,
a few milliseconds per frame), then maps each key to the matching screen region.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

from .keyboard import FRAME_BYTES
from .layout import HID_TO_LED

COLS, ROWS = 24, 6
_X0 = min(v[3] for v in HID_TO_LED.values())
_X1 = max(v[3] for v in HID_TO_LED.values()) + 34
# led -> (row, col) in the sample grid
_MAP = {v[0]: (min(ROWS - 1, v[2]), min(COLS - 1, int((v[3] + 17 - _X0) / (_X1 - _X0) * COLS)))
        for v in HID_TO_LED.values()}


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


_API = None


def _api():
    """Declare handle types so 64-bit handles aren't truncated."""
    global _API
    if _API:
        return _API
    u, g = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
    H = ctypes.c_void_p
    u.GetDC.restype = H; u.GetDC.argtypes = (H,)
    u.ReleaseDC.argtypes = (H, H)
    g.CreateCompatibleDC.restype = H; g.CreateCompatibleDC.argtypes = (H,)
    g.CreateCompatibleBitmap.restype = H; g.CreateCompatibleBitmap.argtypes = (H, ctypes.c_int, ctypes.c_int)
    g.SelectObject.restype = H; g.SelectObject.argtypes = (H, H)
    g.SetStretchBltMode.argtypes = (H, ctypes.c_int)
    g.StretchBlt.argtypes = (H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.DWORD)
    g.GetDIBits.argtypes = (H, H, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT)
    g.DeleteObject.argtypes = (H,)
    g.DeleteDC.argtypes = (H,)
    _API = (u, g)
    return _API


def grab(cols=COLS, rows=ROWS) -> bytes | None:
    """Return cols*rows*4 bytes (BGRA, top-down) of the downscaled primary screen."""
    u, g = _api()
    sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    sdc = u.GetDC(0)
    mdc = g.CreateCompatibleDC(sdc)
    bmp = g.CreateCompatibleBitmap(sdc, cols, rows)
    old = g.SelectObject(mdc, bmp)
    try:
        g.SetStretchBltMode(mdc, 4)  # HALFTONE averages pixels
        g.StretchBlt(mdc, 0, 0, cols, rows, sdc, 0, 0, sw, sh, 0x00CC0020)
        bi = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), cols, -rows, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(cols * rows * 4)
        if not g.GetDIBits(mdc, bmp, 0, rows, buf, ctypes.byref(bi), 0):
            return None
        return buf.raw
    finally:
        g.SelectObject(mdc, old)
        g.DeleteObject(bmp)
        g.DeleteDC(mdc)
        u.ReleaseDC(0, sdc)


class AmbientEngine:
    def __init__(self):
        self.running = False
        self._stop = threading.Event()
        self._thread = None
        self.saturation = 1.4
        self.brightness = 1.0
        self.fps = 20
        self.last_error = ""

    def configure(self, saturation=1.4, brightness=1.0, fps=20):
        self.saturation = max(0.5, min(3.0, float(saturation)))
        self.brightness = max(0.1, min(1.5, float(brightness)))
        self.fps = max(5, min(30, int(fps)))

    def _frame(self, px: bytes, prev: list[float]) -> bytes:
        out = bytearray(FRAME_BYTES)
        s, br = self.saturation, self.brightness
        for led, (r_, c_) in _MAP.items():
            i = (r_ * COLS + c_) * 4
            b, g, r = px[i], px[i + 1], px[i + 2]
            m = (r + g + b) / 3
            rgb = [m + (v - m) * s for v in (r, g, b)]
            for k in range(3):
                v = max(0.0, min(254.0, rgb[k] * br))
                j = led * 3 + k
                prev[j] = prev[j] * 0.55 + v * 0.45        # smooth flicker
                out[j] = int(prev[j])
        return bytes(out)

    def _loop(self, kb):
        prev = [0.0] * FRAME_BYTES
        while not self._stop.is_set():
            t0 = time.perf_counter()
            px = grab()
            if px:
                try:
                    kb.send_frame(self._frame(px, prev))
                except OSError:
                    break
            self._stop.wait(max(0.0, 1 / self.fps - (time.perf_counter() - t0)))
        self.running = False

    def start(self, kb) -> bool:
        if self.running:
            return True
        if grab() is None:
            self.last_error = "Screen capture isn't available"
            return False
        self._stop.clear()
        self.running = True
        self._thread = threading.Thread(target=self._loop, args=(kb,), daemon=True, name="Ambient")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(1.0)
            self._thread = None
        self.running = False
