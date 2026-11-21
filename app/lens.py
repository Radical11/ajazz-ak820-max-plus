"""
lens.py - Shortcut lens: hold Ctrl, Alt, Win or Shift and the keys that do
something with that modifier in the app you're using light up.

Works over any lighting, including the keyboard's own effects: while the
modifier is held the app briefly shows its own frame, then hands the lighting
back when you let go.
"""

from __future__ import annotations

import threading

from .layout import HID_TO_LED
from .winhooks import hook, vk_to_hid

CTRL, SHIFT, ALT, WIN = 0xE0, 0xE1, 0xE2, 0xE3
_MOD_OF = {0xE0: CTRL, 0xE4: CTRL, 0xE1: SHIFT, 0xE5: SHIFT, 0xE2: ALT, 0xE6: ALT, 0xE3: WIN, 0xE7: WIN}


def _k(s: str) -> list[int]:
    """Letters/digits/F-keys by name -> HID codes."""
    out = []
    names = {"TAB": 0x2B, "ESC": 0x29, "ENTER": 0x28, "SPACE": 0x2C, "BKSP": 0x2A, "DEL": 0x4C, "HOME": 0x4A,
             "END": 0x4D, "PGUP": 0x4B, "PGDN": 0x4E, "LEFT": 0x50, "RIGHT": 0x4F, "UP": 0x52, "DOWN": 0x51,
             "/": 0x38, "\\": 0x31, "[": 0x2F, "]": 0x30, "-": 0x2D, "=": 0x2E, ",": 0x36, ".": 0x37,
             ";": 0x33, "'": 0x34, "`": 0x35}
    for tok in s.split():
        t = tok.upper()
        if len(t) == 1 and "A" <= t <= "Z":
            out.append(0x04 + ord(t) - ord("A"))
        elif len(t) == 1 and t.isdigit():
            out.append(0x27 if t == "0" else 0x1E + int(t) - 1)
        elif t.startswith("F") and t[1:].isdigit():
            out.append(0x3A + int(t[1:]) - 1)
        elif t in names:
            out.append(names[t])
    return out


# (modifier) -> keys, per app; "*" applies everywhere. Colours group by meaning.
EDIT, NAV, VIEW, APP = (60, 200, 254), (254, 190, 40), (180, 110, 254), (60, 230, 140)
SHORTCUTS = {
    "*": {
        CTRL: [(EDIT, "C V X Z Y A S"), (NAV, "F"), (APP, "N O P W T")],
        WIN: [(APP, "E D L R I S V"), (NAV, "TAB LEFT RIGHT UP DOWN"), (VIEW, ".")],
        ALT: [(NAV, "TAB F4")],
    },
    "code.exe": {
        CTRL: [(EDIT, "C V X Z Y A S D /"), (NAV, "P G F H TAB"), (VIEW, "B J ` K"), (APP, "N W")],
        SHIFT: [(NAV, "F12"), (EDIT, "F2")],
        ALT: [(NAV, "UP DOWN LEFT RIGHT"), (EDIT, "Z")],
    },
    "chrome.exe": {CTRL: [(APP, "T N W"), (NAV, "L F TAB 1 2 3 4 5 6 7 8 9"), (VIEW, "D H J R P - =")]},
    "msedge.exe": {CTRL: [(APP, "T N W"), (NAV, "L F TAB 1 2 3 4 5 6 7 8 9"), (VIEW, "D H J R P - =")]},
    "firefox.exe": {CTRL: [(APP, "T N W"), (NAV, "L F TAB 1 2 3 4 5 6 7 8 9"), (VIEW, "D H J R P - =")]},
    "photoshop.exe": {CTRL: [(EDIT, "Z C V X J T A D I"), (VIEW, "0 1 - = H R ;"), (APP, "N O S")]},
    "explorer.exe": {CTRL: [(EDIT, "C V X Z A"), (APP, "N W E"), (VIEW, "1 2 3 4 5 6")], ALT: [(NAV, "UP LEFT RIGHT ENTER")]},
    "discord.exe": {CTRL: [(NAV, "K / ,"), (VIEW, "I U")]},
    "obs64.exe": {CTRL: [(APP, "N O S")]},
}


class ShortcutLens:
    HOLD_S = 0.35

    def __init__(self, kb, foreground, show=None, hide=None, suppress=None):
        self._kb = kb
        self._fg = foreground          # callable -> current exe name
        self._show = show              # callable({led: rgb}) while the modifier is held
        self._hide = hide
        self._suppress = suppress      # callable -> True to stay quiet (e.g. game mode on)
        self.enabled = False
        self._held: set[int] = set()
        self._others = False
        self._timer: threading.Timer | None = None
        self._active = False

    def set_enabled(self, on: bool) -> bool:
        if on and not self.enabled:
            if not hook.add_listener("lens", self._on_key):
                return False
        elif not on and self.enabled:
            hook.remove_listener("lens")
            self._end()
        self.enabled = on
        return True

    def _on_key(self, vk, _scan, down, ext, injected):
        hid = vk_to_hid(vk, ext)
        if hid is None or injected:
            return
        mod = _MOD_OF.get(hid)
        if mod is None:
            if down and self._held:
                self._others = True       # a real shortcut is being typed: don't flash
            return
        if down and mod not in self._held:
            self._held.add(mod)
            self._others = False
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.HOLD_S, self._begin)
            self._timer.daemon = True
            self._timer.start()
        elif not down:
            self._held.discard(mod)
            if not self._held:
                if self._timer:
                    self._timer.cancel()
                self._end()

    def _keys_for(self, mods: set[int]) -> dict[int, tuple]:
        exe = (self._fg() or "").lower()
        result: dict[int, tuple] = {}
        for table in (SHORTCUTS["*"], SHORTCUTS.get(exe, {})):
            for mod in mods:
                for color, names in table.get(mod, []):
                    for hid in _k(names):
                        result[hid] = color
        return result

    def _begin(self):
        if not self._held or self._others or not self._kb.is_connected():
            return
        if self._held == {SHIFT} or (self._suppress and self._suppress()):
            return          # Shift alone is normal typing; games hold Ctrl to crouch
        keys = self._keys_for(set(self._held))
        if not keys:
            return
        for mod_hid, mod in _MOD_OF.items():
            if mod in self._held:
                keys[mod_hid] = (254, 254, 254)
        if self._show:
            self._active = True
            self._show({HID_TO_LED[h][0]: c for h, c in keys.items() if h in HID_TO_LED})

    def _end(self):
        if self._active:
            self._active = False
            if self._hide:
                try:
                    self._hide()
                except Exception:
                    pass
