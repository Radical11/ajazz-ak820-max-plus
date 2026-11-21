"""
keyboard.py - HID transport + high-level controller for the AJAZZ AK820 Max Plus.

  USB wired:      1A2C:A036
  2.4 GHz dongle: 1A2C:8FFF
The vendor channel is the HID collection with usage page 0xFF02 (interface 0).
All writes go through one lock, so effect threads, the UI and profile switching
can share a single controller safely.
"""

from __future__ import annotations

import json
import os
import threading
import time

import hid

from . import protocol as P
from .storage import data_path, legacy_path

# Re-exported for older modules
NUM_LEDS = P.NUM_LEDS
FRAME_BYTES = P.FRAME_BYTES
HARDWARE_MODES = P.HARDWARE_MODES
COLORS = P.COLORS


class DeviceNotFound(RuntimeError):
    pass


def find_device() -> dict:
    """Return the hidapi info dict of the vendor collection, preferring wired."""
    candidates = [d for d in hid.enumerate(P.VID) if d["product_id"] in P.KNOWN_PIDS]
    if not candidates:
        raise DeviceNotFound("AK820 Max Plus not found. Plug in the cable or the 2.4 GHz dongle.")

    def rank(d):
        vendor = d.get("usage_page") == P.VENDOR_USAGE_PAGE
        iface0 = d.get("interface_number") == 0
        wired = d["product_id"] == P.PID_WIRED
        return (not vendor, not iface0, not wired)

    best = sorted(candidates, key=rank)[0]
    if best.get("usage_page") != P.VENDOR_USAGE_PAGE and best.get("interface_number") != 0:
        raise DeviceNotFound("Keyboard found, but its control interface is unavailable.")
    return best


class KeyboardRGB:
    STATE_FILE = data_path("rgb_state.json")

    def __init__(self):
        self.device: hid.device | None = None
        self.info: dict | None = None
        self.leds: list[tuple[int, int, int]] = [(0, 0, 0)] * NUM_LEDS
        self._io = threading.RLock()
        self._last_frame: bytes | None = None
        self._custom_active = False

    # ── connection ─────────────────────────────────────────────────────
    def connect(self) -> None:
        with self._io:
            if self.device is not None:
                return
            info = find_device()
            dev = hid.device()
            try:
                dev.open_path(info["path"])
            except (OSError, IOError) as e:
                raise DeviceNotFound(f"Could not open the keyboard: {e}") from e
            self.device, self.info = dev, info
            self._last_frame = None
            self._custom_active = False

    def disconnect(self) -> None:
        with self._io:
            if self.device is not None:
                try:
                    self.device.close()
                except Exception:
                    pass
            self.device = None

    def is_connected(self) -> bool:
        return self.device is not None

    @property
    def connection_type(self) -> str:
        if not self.info:
            return "none"
        return "wired" if self.info["product_id"] == P.PID_WIRED else "wireless"

    # ── low level ──────────────────────────────────────────────────────
    def _write(self, packet: bytes) -> None:
        with self._io:
            if self.device is None:
                raise OSError("keyboard not connected")
            try:
                n = self.device.write(b"\x00" + packet if os.name == "nt" else packet)
            except (OSError, IOError, ValueError) as e:
                self.disconnect()
                raise OSError(str(e)) from e
            if n is not None and n < 0:
                self.disconnect()
                raise OSError("write failed (device unplugged?)")

    def write_all(self, packets) -> None:
        with self._io:
            for p in packets:
                self._write(p)

    def heartbeat(self) -> bytes | None:
        """Send 0x0E and return the reply payload (or None)."""
        with self._io:
            self._write(P.heartbeat_packet())
            try:
                r = self.device.read(65, 150)
            except Exception:
                return None
        return bytes(r) if r else None

    # ── lighting ───────────────────────────────────────────────────────
    def init_custom_mode(self, force: bool = False) -> None:
        if self._custom_active and not force:
            return
        self.write_all(P.custom_mode_packets())
        self._custom_active = True
        self._last_frame = None

    def set_hardware_mode(self, mode: int, brightness: int = 4, speed: int = 2,
                          direction: int = 0, color: int = 7, color2: int = 7) -> None:
        if mode not in HARDWARE_MODES:
            raise ValueError(f"invalid mode id {mode}")
        self._write(P.mode_packet(mode, brightness, speed, direction, color, color2))
        self._custom_active = False

    def frame_bytes(self) -> bytes:
        out = bytearray(FRAME_BYTES)
        for i, (r, g, b) in enumerate(self.leds):
            out[i * 3] = r & 0xFF
            out[i * 3 + 1] = g & 0xFF
            out[i * 3 + 2] = b & 0xFF
        return bytes(out)

    def push_frame(self, force: bool = False) -> bool:
        """Send self.leds. Skips identical frames unless force. Returns True if sent."""
        return self.send_frame(self.frame_bytes(), force=force)

    def send_frame(self, rgb: bytes, force: bool = False, packet_delay: float = 0.0) -> bool:
        if not force and rgb == self._last_frame:
            return False
        with self._io:
            for p in P.frame_packets(rgb):
                self._write(p)
                if packet_delay:
                    time.sleep(packet_delay)
            self._last_frame = rgb
        return True

    def set_all(self, rgb) -> None:
        self.leds = [tuple(rgb)] * NUM_LEDS

    def set_led(self, index: int, rgb) -> None:
        if 0 <= index < NUM_LEDS:
            self.leds[index] = tuple(rgb)

    def clear(self) -> None:
        self.set_all((0, 0, 0))

    def all_off(self) -> None:
        self.clear()
        self.push_frame(force=True)

    def save_to_hardware(self) -> None:
        self._write(P.save_packet())

    # ── keys / macros / settings ───────────────────────────────────────
    def assign_key(self, layer: int, src_hid: int, dst: int) -> None:
        self._write(P.key_packet(layer, src_hid, dst))

    def assign_macro(self, layer: int, src_hid: int, events: list[dict], repeat: int = 1) -> None:
        self.write_all(P.macro_packets(layer, src_hid, events, repeat))

    def reset_keymap(self) -> None:
        self._write(P.reset_keys_packet())

    def set_sleep(self, option: int) -> None:
        self._write(P.sleep_packet(option))

    def set_response(self, gear: int) -> None:
        self._write(P.response_packet(gear))

    def set_fn_mode(self, swapped: bool) -> None:
        self._write(P.fn_mode_packet(swapped))

    # ── persistence of the last custom frame ───────────────────────────
    def save_state(self) -> None:
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(self.leds, f)
        except OSError:
            pass

    def load_state(self) -> bool:
        for path in (self.STATE_FILE, legacy_path("rgb_state.json")):
            try:
                with open(path) as f:
                    leds = [tuple(c) for c in json.load(f)]
                if len(leds) == NUM_LEDS:
                    self.leds = leds
                    return True
            except (OSError, ValueError, TypeError):
                continue
        return False

    def get_leds_as_hex(self) -> list[str]:
        return [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in self.leds]
