"""
heatmap.py - Typing heatmap / reactive lighting.

Keys glow with the hot colour when pressed and fade to the cold colour.
Uses the shared low-level hook (winhooks) — keystrokes are never stored,
only an LED index is marked hot.
"""

from __future__ import annotations

import threading
import time

from .keyboard import KeyboardRGB, NUM_LEDS
from .layout import HID_TO_LED
from .winhooks import hook, vk_to_hid


class HeatmapEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.heat = [0.0] * NUM_LEDS
        self.decay_rate = 0.02
        self.hot_color = (254, 40, 0)
        self.cold_color = (0, 0, 60)

    def configure(self, decay_rate=0.02, hot_color=(254, 40, 0), cold_color=(0, 0, 60)):
        with self._lock:
            self.decay_rate = max(0.001, float(decay_rate))
            self.hot_color = tuple(hot_color)
            self.cold_color = tuple(cold_color)

    def _on_key(self, vk, _scan, down, ext, _inj):
        if not down:
            return
        hid = vk_to_hid(vk, ext)
        entry = HID_TO_LED.get(hid) if hid is not None else None
        if entry:
            self.heat[entry[0]] = 1.0

    @staticmethod
    def _lerp(c1, c2, t):
        return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

    def _loop(self, kb: KeyboardRGB):
        interval = 1 / 30
        while not self._stop.is_set():
            t0 = time.perf_counter()
            with self._lock:
                d, hot, cold = self.decay_rate, self.hot_color, self.cold_color
            heat = self.heat
            frame = []
            for i in range(NUM_LEDS):
                h = heat[i]
                if h > 0:
                    heat[i] = h = max(0.0, h - d)
                frame.append(self._lerp(cold, hot, h))
            try:
                kb.leds = frame
                kb.push_frame()   # identical frames are skipped automatically
            except OSError:
                break
            self._stop.wait(max(0.0, interval - (time.perf_counter() - t0)))
        self.running = False

    def start(self, kb: KeyboardRGB) -> bool:
        if self.running:
            return True
        self.heat = [0.0] * NUM_LEDS
        if not hook.add_listener("heatmap", self._on_key):
            hook.remove_listener("heatmap")
            return False
        self._stop.clear()
        self.running = True
        self._thread = threading.Thread(target=self._loop, args=(kb,), daemon=True, name="Heatmap")
        self._thread.start()
        return True

    def stop(self):
        hook.remove_listener("heatmap")
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.running = False
