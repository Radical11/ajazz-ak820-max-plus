"""
appwatch.py - Watches the foreground application (Windows) so profiles can follow
the app you're using. Polls once per second via ctypes; no extra dependencies.
"""

from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

AVAILABLE = os.name == "nt"

if AVAILABLE:
    user32 = ctypes.WinDLL("user32")
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                                    wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def foreground_exe() -> str:
    if not AVAILABLE:
        return ""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(h)
    return ""


class AppWatcher:
    def __init__(self, on_change, interval: float = 1.0, ignore: tuple[str, ...] = ()):
        self._on_change = on_change
        self._interval = interval
        self._ignore = {i.lower() for i in ignore}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.current = ""

    def start(self):
        if not AVAILABLE or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="AppWatcher")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.wait(self._interval):
            exe = foreground_exe()
            if exe and exe != self.current and exe not in self._ignore:
                self.current = exe
                try:
                    self._on_change(exe)
                except Exception:
                    pass
