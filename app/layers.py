"""
layers.py - Lighting layers drawn on top of per-key and live lighting.

  caps       Caps Lock key lights up while Caps Lock is on
  highlight  a set of keys always shows a fixed colour (e.g. WASD in game profiles)
  game       blocked keys (Win, Tab, F4) turn a warning colour while game mode is on

Layers apply to every frame the app sends. Built-in keyboard effects run on the
keyboard itself, so layers can't be drawn over them.
"""

from __future__ import annotations

import ctypes
import os
import threading

from .layout import HID_TO_LED

DEFAULT_LAYERS = {
    "caps": {"on": True, "color": "#ffffff"},
    "highlight": {"on": False, "color": "#f0404e", "keys": [0x1A, 0x04, 0x16, 0x07]},  # W A S D
    "game": {"on": True, "color": "#f0404e"},
}

VK_CAPITAL = 0x14
_GAME_KEYS = {"win": [0xE3], "alt_tab": [0x2B], "alt_f4": [0x3D]}


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(min(254, int(h[i:i + 2], 16)) for i in (0, 2, 4))


def caps_on() -> bool:
    if os.name != "nt":
        return False
    return bool(ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 1)


class Layers:
    def __init__(self):
        self.cfg = {k: dict(v) for k, v in DEFAULT_LAYERS.items()}
        self.game_mode = {"win": False, "alt_tab": False, "alt_f4": False}
        self._caps = caps_on()
        self._kb = None
        self._stop = threading.Event()
        self._thread = None

    def configure(self, cfg: dict | None, game_mode: dict | None = None):
        merged = {k: dict(v) for k, v in DEFAULT_LAYERS.items()}
        for k, v in (cfg or {}).items():
            if k in merged and isinstance(v, dict):
                merged[k].update(v)
        self.cfg = merged
        if game_mode is not None:
            self.game_mode = dict(game_mode)
        self._refresh()

    def attach(self, kb):
        self._kb = kb
        kb.overlay = self.apply
        if not self._thread:
            self._thread = threading.Thread(target=self._watch, daemon=True, name="Layers")
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _refresh(self):
        kb = self._kb
        if kb is not None and kb.is_connected():
            try:
                kb.refresh()
            except OSError:
                pass

    def _watch(self):
        while not self._stop.wait(0.12):
            c = caps_on()
            if c != self._caps:
                self._caps = c
                if self.cfg["caps"]["on"]:
                    self._refresh()

    def apply(self, rgb: bytes) -> bytes:
        cfg = self.cfg
        paints: dict[int, tuple] = {}
        if cfg["highlight"]["on"]:
            col = _rgb(cfg["highlight"]["color"])
            for hid in cfg["highlight"].get("keys", []):
                e = HID_TO_LED.get(int(hid))
                if e:
                    paints[e[0]] = col
        if cfg["game"]["on"]:
            col = _rgb(cfg["game"]["color"])
            for k, hids in _GAME_KEYS.items():
                if self.game_mode.get(k):
                    for hid in hids:
                        paints[HID_TO_LED[hid][0]] = col
        if cfg["caps"]["on"] and self._caps:
            paints[HID_TO_LED[0x39][0]] = _rgb(cfg["caps"]["color"])
        if not paints:
            return rgb
        out = bytearray(rgb)
        for led, (r, g, b) in paints.items():
            out[led * 3:led * 3 + 3] = bytes((r, g, b))
        return bytes(out)
