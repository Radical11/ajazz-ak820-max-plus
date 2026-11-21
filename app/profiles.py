"""
profiles.py - Profiles (lighting + key layers + device settings + game mode + bound apps)
and the macro library. Stored as JSON under %APPDATA%\\AK820Studio.

The keyboard holds one active key map. Applying a profile = reset all keys (0x0F)
then replay every non-default assignment — exactly what the vendor app does.
"""

from __future__ import annotations

import copy
import os
import re
import threading
import time
import uuid

from . import protocol as P
from .storage import PROFILES_DIR, data_path, read_json, write_json

MACROS_FILE = data_path("macros.json")
SETTINGS_FILE = data_path("settings.json")

DEFAULT_PROFILE = {
    "id": "default",
    "name": "Default",
    "apps": [],
    "lighting": {"kind": "hardware", "mode": 7, "brightness": 4, "speed": 3,
                 "direction": 0, "color": "blue", "color2": "rgb"},
    "keymap": {"1": {}, "2": {}},
    "device": {"sleep": 3, "response": 1, "fn_swap": False},
    "game_mode": {"win": False, "alt_tab": False, "alt_f4": False},
    "layers": {},
}

DEFAULT_SETTINGS = {
    "active_profile": "default",
    "auto_switch": True,
    "start_minimized": False,
    "close_to_tray": True,
    "launch_at_login": False,
    "typing_stats": False,
    "memory_saver": True,
    "theme": "system",
    "shortcut_lens": True,
}


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "profile"


def _normalize(p: dict) -> dict:
    out = copy.deepcopy(DEFAULT_PROFILE)
    for k, v in (p or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    out["keymap"] = {str(l): dict(out["keymap"].get(str(l), {})) for l in (1, 2)}
    out["apps"] = sorted({a.lower() for a in out.get("apps", []) if a})
    return out


class Store:
    def __init__(self):
        self._lock = threading.RLock()
        self.settings = {**DEFAULT_SETTINGS, **read_json(SETTINGS_FILE, {})}
        self.macros: list[dict] = read_json(MACROS_FILE, [])
        if not self.list_profiles():
            self.save_profile(DEFAULT_PROFILE)

    # ── settings ───────────────────────────────────────────────────────
    def update_settings(self, **kw) -> dict:
        with self._lock:
            self.settings.update({k: v for k, v in kw.items() if k in DEFAULT_SETTINGS})
            write_json(SETTINGS_FILE, self.settings)
            return dict(self.settings)

    # ── profiles ───────────────────────────────────────────────────────
    def _path(self, pid: str) -> str:
        return os.path.join(PROFILES_DIR, f"{_slug(pid)}.json")

    def list_profiles(self) -> list[dict]:
        out = []
        for fn in sorted(os.listdir(PROFILES_DIR)):
            if fn.endswith(".json"):
                p = read_json(os.path.join(PROFILES_DIR, fn), None)
                if isinstance(p, dict) and p.get("id"):
                    out.append(_normalize(p))
        out.sort(key=lambda p: (p["id"] != "default", p["name"].lower()))
        return out

    def get_profile(self, pid: str) -> dict | None:
        p = read_json(self._path(pid), None)
        return _normalize(p) if isinstance(p, dict) else None

    def active_profile(self) -> dict:
        return self.get_profile(self.settings.get("active_profile", "default")) or self.list_profiles()[0]

    def save_profile(self, profile: dict) -> dict:
        with self._lock:
            p = _normalize(profile)
            p["id"] = _slug(p.get("id") or p["name"])
            write_json(self._path(p["id"]), p)
            return p

    def create_profile(self, name: str, base: str | None = None) -> dict:
        src = self.get_profile(base) if base else None
        p = copy.deepcopy(src or DEFAULT_PROFILE)
        existing = {x["id"] for x in self.list_profiles()}
        pid, n = _slug(name), 2
        while pid in existing:
            pid, n = f"{_slug(name)}-{n}", n + 1
        p.update({"id": pid, "name": name.strip() or "Profile", "apps": []})
        return self.save_profile(p)

    def delete_profile(self, pid: str) -> None:
        if pid == "default":
            raise ValueError("The default profile can't be deleted")
        try:
            os.remove(self._path(pid))
        except OSError:
            pass
        if self.settings.get("active_profile") == pid:
            self.update_settings(active_profile="default")

    def profile_for_app(self, exe: str) -> dict | None:
        exe = (exe or "").lower()
        for p in self.list_profiles():
            if exe in p["apps"]:
                return p
        return None

    # ── macros ─────────────────────────────────────────────────────────
    def save_macro(self, macro: dict) -> dict:
        with self._lock:
            m = {
                "id": macro.get("id") or uuid.uuid4().hex[:8],
                "name": (macro.get("name") or "Macro").strip(),
                "repeat": int(macro.get("repeat", 1)),
                "events": [{"code": int(e["code"]), "up": bool(e.get("up")),
                            "delay": max(0, int(e.get("delay", 10)))} for e in macro.get("events", [])],
            }
            if len(m["events"]) > P.MAX_MACRO_EVENTS:
                raise ValueError(f"A macro can hold at most {P.MAX_MACRO_EVENTS} events")
            self.macros = [x for x in self.macros if x["id"] != m["id"]] + [m]
            write_json(MACROS_FILE, self.macros)
            return m

    def delete_macro(self, mid: str) -> None:
        with self._lock:
            self.macros = [x for x in self.macros if x["id"] != mid]
            write_json(MACROS_FILE, self.macros)

    def macro(self, mid: str) -> dict | None:
        return next((m for m in self.macros if m["id"] == mid), None)


def apply_keymap(kb, profile: dict, store: Store) -> list[str]:
    """Reset the keyboard's key map and replay the profile. Returns warnings."""
    warnings = []
    kb.reset_keymap()
    time.sleep(0.02)
    for layer in ("1", "2"):
        for src, action in profile["keymap"].get(layer, {}).items():
            try:
                send_action(kb, int(layer), int(src, 16) if str(src).lower().startswith("0x") else int(src), action, store)
            except Exception as e:  # keep going, report at the end
                warnings.append(f"{src}: {e}")
    return warnings


def send_action(kb, layer: int, src: int, action: dict, store: Store) -> None:
    kind = action.get("type")
    if kind in ("key", "media"):
        kb.assign_key(layer, src, int(action["code"]))
    elif kind == "disabled":
        kb.assign_key(layer, src, P.KEY_DISABLED)
    elif kind == "default":
        kb.assign_key(layer, src, P.KEY_DEFAULT)
    elif kind == "shortcut":
        kb.assign_macro(layer, src, P.shortcut_events([int(c) for c in action["codes"]]), 1)
    elif kind == "macro":
        m = store.macro(action["macro_id"])
        if not m:
            raise ValueError("macro no longer exists")
        kb.assign_macro(layer, src, m["events"], m.get("repeat", 1))
    else:
        raise ValueError(f"unknown action {kind!r}")
