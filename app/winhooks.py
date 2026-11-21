"""
winhooks.py - One global low-level keyboard hook (WH_KEYBOARD_LL) via ctypes.

* Listeners receive (vk, scan, down, extended, injected) for every key event
  (heatmap, key tester, macro recorder).
* Game mode blocks the Windows keys, Alt+Tab and Alt+F4 while enabled.

The hook thread only runs while at least one listener is registered or game
mode is on, so the app costs nothing when idle. Replaces pynput.
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
from ctypes import wintypes

log = logging.getLogger(__name__)

AVAILABLE = os.name == "nt"

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_QUIT = 0x0012
LLKHF_EXTENDED, LLKHF_INJECTED, LLKHF_ALTDOWN = 0x01, 0x10, 0x20
VK_TAB, VK_F4, VK_LWIN, VK_RWIN, VK_ESCAPE = 0x09, 0x73, 0x5B, 0x5C, 0x1B

if AVAILABLE:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.CallNextHookEx.restype = LRESULT
    user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
    user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
    user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class KeyHook:
    def __init__(self):
        self._listeners: dict[str, callable] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._hook = None
        self._proc = None
        self._ready = threading.Event()
        self.game_mode = {"win": False, "alt_tab": False, "alt_f4": False}
        self._alt_down = False

    # ── public ─────────────────────────────────────────────────────────
    def add_listener(self, name: str, fn) -> bool:
        with self._lock:
            self._listeners[name] = fn
        return self._ensure()

    def remove_listener(self, name: str) -> None:
        with self._lock:
            self._listeners.pop(name, None)
        self._maybe_stop()

    def set_game_mode(self, win: bool, alt_tab: bool, alt_f4: bool) -> bool:
        self.game_mode = {"win": bool(win), "alt_tab": bool(alt_tab), "alt_f4": bool(alt_f4)}
        if any(self.game_mode.values()):
            return self._ensure()
        self._maybe_stop()
        return True

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── internals ──────────────────────────────────────────────────────
    def _needed(self) -> bool:
        return bool(self._listeners) or any(self.game_mode.values())

    def _ensure(self) -> bool:
        if not AVAILABLE:
            return False
        if self.active:
            return True
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="KeyHook", daemon=True)
        self._thread.start()
        self._ready.wait(2)
        return self._hook is not None

    def _maybe_stop(self) -> None:
        if self.active and not self._needed() and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(1)
            self._thread = None

    def _should_block(self, vk: int, down: bool, alt: bool) -> bool:
        gm = self.game_mode
        if gm["win"] and vk in (VK_LWIN, VK_RWIN):
            return True
        if down and alt and gm["alt_tab"] and vk == VK_TAB:
            return True
        if down and alt and gm["alt_f4"] and vk == VK_F4:
            return True
        return False

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()

        def proc(n_code, w_param, l_param):
            if n_code == 0:
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                alt = bool(kb.flags & LLKHF_ALTDOWN)
                injected = bool(kb.flags & LLKHF_INJECTED)
                ext = bool(kb.flags & LLKHF_EXTENDED)
                with self._lock:
                    listeners = list(self._listeners.values())
                for fn in listeners:
                    try:
                        fn(kb.vkCode, kb.scanCode, down, ext, injected)
                    except Exception:  # never let a listener break typing
                        log.exception("key listener failed")
                if not injected and self._should_block(kb.vkCode, down, alt):
                    return 1
            return user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

        self._proc = HOOKPROC(proc)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        self._ready.set()
        if not self._hook:
            log.warning("SetWindowsHookEx failed: %s", ctypes.get_last_error())
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None


# Windows virtual-key → USB HID usage (US layout; extended flag disambiguates numpad/nav)
VK_TO_HID = {
    **{0x41 + i: 0x04 + i for i in range(26)},                   # A-Z
    **{0x31 + i: 0x1E + i for i in range(9)}, 0x30: 0x27,         # 1-9, 0
    **{0x70 + i: 0x3A + i for i in range(12)},                    # F1-F12
    **{0x7C + i: 0x68 + i for i in range(12)},                    # F13-F24
    0x0D: 0x28, 0x1B: 0x29, 0x08: 0x2A, 0x09: 0x2B, 0x20: 0x2C,
    0xBD: 0x2D, 0xBB: 0x2E, 0xDB: 0x2F, 0xDD: 0x30, 0xDC: 0x31,
    0xBA: 0x33, 0xDE: 0x34, 0xC0: 0x35, 0xBC: 0x36, 0xBE: 0x37, 0xBF: 0x38,
    0x14: 0x39, 0x2C: 0x46, 0x91: 0x47, 0x13: 0x48, 0x2D: 0x49, 0x24: 0x4A,
    0x21: 0x4B, 0x2E: 0x4C, 0x23: 0x4D, 0x22: 0x4E, 0x27: 0x4F, 0x25: 0x50,
    0x28: 0x51, 0x26: 0x52, 0x90: 0x53, 0x6F: 0x54, 0x6A: 0x55, 0x6D: 0x56,
    0x6B: 0x57, **{0x61 + i: 0x59 + i for i in range(9)}, 0x60: 0x62, 0x6E: 0x63,
    0x5D: 0x65,
    0xA2: 0xE0, 0xA0: 0xE1, 0xA4: 0xE2, 0x5B: 0xE3,
    0xA3: 0xE4, 0xA1: 0xE5, 0xA5: 0xE6, 0x5C: 0xE7,
    0x11: 0xE0, 0x10: 0xE1, 0x12: 0xE2,
}


def vk_to_hid(vk: int, extended: bool = False) -> int | None:
    if vk == 0x0D and extended:
        return 0x58  # numpad Enter
    return VK_TO_HID.get(vk)


hook = KeyHook()
