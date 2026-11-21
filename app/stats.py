"""
stats.py - Optional, local-only typing statistics.

Counts how often each key is pressed per day and keeps a rolling words-per-minute
figure. Only key counts are stored — never the order of keys or any text — in
%APPDATA%\\AK820Studio\\stats.json. Off unless the user turns it on.
"""

from __future__ import annotations

import collections
import datetime as dt
import threading
import time

from .storage import data_path, read_json, write_json
from .winhooks import hook, vk_to_hid

STATS_FILE = data_path("stats.json")
_CHAR_KEYS = set(range(0x04, 0x28)) | {0x2C, 0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38}


class TypingStats:
    def __init__(self):
        self.data = read_json(STATS_FILE, {"days": {}})
        self._recent = collections.deque()   # timestamps of character presses (last 60 s)
        self._lock = threading.Lock()
        self._dirty = False
        self.enabled = False
        self._saver = None

    def _on_key(self, vk, _scan, down, ext, injected):
        if not down or injected:
            return
        hid = vk_to_hid(vk, ext)
        if hid is None:
            return
        day = dt.date.today().isoformat()
        with self._lock:
            d = self.data["days"].setdefault(day, {"total": 0, "keys": {}})
            d["total"] += 1
            d["keys"][str(hid)] = d["keys"].get(str(hid), 0) + 1
            if hid in _CHAR_KEYS:
                self._recent.append(time.monotonic())
            self._dirty = True

    def _save_loop(self):
        while self.enabled:
            time.sleep(30)
            self.flush()

    def flush(self):
        with self._lock:
            if not self._dirty:
                return
            days = self.data["days"]
            for k in sorted(days)[:-90]:      # keep 90 days
                days.pop(k)
            snapshot = {"days": dict(days)}
            self._dirty = False
        write_json(STATS_FILE, snapshot)

    def set_enabled(self, on: bool) -> bool:
        if on and not self.enabled:
            if not hook.add_listener("stats", self._on_key):
                return False
            self.enabled = True
            self._saver = threading.Thread(target=self._save_loop, daemon=True, name="StatsSaver")
            self._saver.start()
        elif not on and self.enabled:
            hook.remove_listener("stats")
            self.enabled = False
            self.flush()
        return True

    def wpm(self) -> int:
        now = time.monotonic()
        with self._lock:
            while self._recent and now - self._recent[0] > 60:
                self._recent.popleft()
            return round(len(self._recent) / 5)

    def summary(self) -> dict:
        with self._lock:
            days = self.data["days"]
            today = days.get(dt.date.today().isoformat(), {"total": 0, "keys": {}})
            week = [k for k in sorted(days)[-7:]]
            totals = collections.Counter()
            for k in days:
                totals.update({int(h): n for h, n in days[k]["keys"].items()})
            return {
                "enabled": self.enabled,
                "wpm": self.wpm() if self.enabled else 0,
                "today": today["total"],
                "week": [{"day": k, "total": days[k]["total"]} for k in week],
                "heat": {str(h): n for h, n in totals.items()},
                "top": [[h, n] for h, n in totals.most_common(8)],
            }

    def clear(self):
        with self._lock:
            self.data = {"days": {}}
            self._dirty = True
        self.flush()
