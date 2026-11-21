"""
protocol.py - Packet builders for the AJAZZ AK820 Max Plus vendor HID protocol.

Every packet is 64 bytes: AA 55 CC 33 <opcode> <payload> <zero padding>.
On Windows hidapi needs a leading report-ID byte (0x00), added by the transport.
Recovered from the official DeviceDriver.exe v1.0.4.6 (see PROTOCOL.md).
"""

from __future__ import annotations

MAGIC = bytes([0xAA, 0x55, 0xCC, 0x33])
REPORT_LEN = 64

VID = 0x1A2C
PID_WIRED = 0xA036
PID_DONGLE = 0x8FFF
KNOWN_PIDS = (PID_WIRED, PID_DONGLE)
VENDOR_USAGE_PAGE = 0xFF02

NUM_LEDS = 108
FRAME_BYTES = NUM_LEDS * 3
LED_MAX = 0xFE  # 0xFF misbehaves on some firmware

# ── opcodes ────────────────────────────────────────────────────────────
OP_MACRO = 0x00
OP_MACRO_NEXT = 0x01
OP_MACRO_COMMIT = 0x02
OP_KEY = 0x04
OP_MODE = 0x07
OP_APPLY = 0x09
OP_SAVE = 0x0A
OP_BEGIN = 0x0B
OP_SLEEP = 0x0C
OP_RESPONSE = 0x0D
OP_HEARTBEAT = 0x0E
OP_RESET_KEYS = 0x0F
OP_FN_MODE = 0x10
FRAME_OPS = (0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFB)

CUSTOM_MODE = 0x17

LAYER_BASE = 1
LAYER_FN = 2

KEY_DEFAULT = 0x00
KEY_DISABLED = 0x01

MAX_MACRO_EVENTS = (REPORT_LEN - 5 - 4) // 2   # 27 events fit one packet
MACRO_DELAY_UNIT_MS = 10
MACRO_DELAY_MAX = 0x7F

SLEEP_OPTIONS = {1: "5 minutes", 2: "15 minutes", 3: "30 minutes", 4: "Never"}
RESPONSE_OPTIONS = {
    1: "Fastest (wired 2-3 ms)",
    2: "Balanced (wired 4-5 ms)",
    3: "Stable (wired 6-7 ms)",
}

COLORS = {
    "red": 0, "green": 1, "blue": 2, "yellow": 3,
    "pink": 4, "cyan": 5, "white": 6, "rgb": 7,
}

# Hardware effects. Names follow the official app where it was observed.
# controls: B brightness, S speed, D direction, C colour
HARDWARE_MODES = {
    0x00: {"name": "Ripple Wave",      "controls": "BSDC"},
    0x01: {"name": "Starry Dots",      "controls": "BSC"},
    0x02: {"name": "Vertical Ripple",  "controls": "BSDC"},
    0x03: {"name": "Burst",            "controls": "BSDC"},
    0x04: {"name": "Spectrum Cycle",   "controls": "BS"},
    0x05: {"name": "Kaleidoscope",     "controls": "BSDC"},
    0x06: {"name": "Static",           "controls": "BC"},
    0x07: {"name": "Breathing",        "controls": "BSC"},
    0x08: {"name": "Cross Waves",      "controls": "BSC"},
    0x09: {"name": "Dual Wave",        "controls": "BSDC"},
    0x0A: {"name": "Reactive Breath",  "controls": "BSC"},
    0x0B: {"name": "Scroll",           "controls": "BSC"},
    0x0C: {"name": "Snake",            "controls": "BSC"},
    0x0D: {"name": "Spiral",           "controls": "BSDC"},
    0x0E: {"name": "Split Rows",       "controls": "BSC"},
    0x0F: {"name": "Rainfall",         "controls": "BSC"},
    0x10: {"name": "Windmill",         "controls": "BSC"},
    0x11: {"name": "Sine Wave",        "controls": "BSC"},
    0x12: {"name": "Gallop",           "controls": "BSDC"},
}

# Vendor single-byte media/system codes usable as key targets.
MEDIA_CODES = {
    0xF9: "My Computer", 0xF2: "Calculator", 0xF0: "Mail", 0xE8: "Media Player",
    0xEE: "Play / Pause", 0xEC: "Stop", 0xED: "Previous Track", 0xEF: "Next Track",
    0xE9: "Volume Down", 0xEA: "Volume Up", 0xEB: "Mute", 0xF1: "Browser Home",
    0xF6: "Browser Refresh", 0xF5: "Browser Stop", 0xF3: "Browser Back",
    0xF4: "Browser Forward", 0xF8: "Favorites", 0xF7: "Browser Search",
}


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def pkt(opcode: int, payload: bytes | list[int] = b"") -> bytes:
    body = MAGIC + bytes([opcode]) + bytes(payload)
    if len(body) > REPORT_LEN:
        raise ValueError(f"payload too long ({len(body)} > {REPORT_LEN})")
    return body + bytes(REPORT_LEN - len(body))


# ── lighting ───────────────────────────────────────────────────────────

def mode_packet(mode: int, brightness: int, speed: int, direction: int, color: int, color2: int = 7) -> bytes:
    return pkt(OP_MODE, [mode & 0xFF, clamp(brightness, 0, 4), clamp(speed, 0, 4),
                         clamp(direction, 0, 1), clamp(color, 0, 7), clamp(color2, 0, 7)])


def custom_mode_packets() -> list[bytes]:
    return [mode_packet(CUSTOM_MODE, 4, 3, 0, 7, 0), pkt(OP_BEGIN), pkt(OP_APPLY)]


def frame_packets(rgb: bytes) -> list[bytes]:
    """rgb: 324 bytes (108 LEDs × R,G,B). Values are capped at LED_MAX."""
    if len(rgb) != FRAME_BYTES:
        raise ValueError(f"expected {FRAME_BYTES} bytes, got {len(rgb)}")
    capped = bytes(LED_MAX if b > LED_MAX else b for b in rgb)
    return [pkt(op, capped[i * 54:(i + 1) * 54]) for i, op in enumerate(FRAME_OPS)]


# ── keys / macros ──────────────────────────────────────────────────────

def key_packet(layer: int, src_hid: int, dst: int) -> bytes:
    """Assign a single target to a physical key. dst 0 = default, 1 = disabled."""
    return pkt(OP_KEY, [layer, src_hid, dst])


def encode_macro_events(events: list[dict]) -> bytes:
    """
    events: [{"code": hid, "up": bool, "delay": ms}]  (delay = pause AFTER the event)
    Each event is 2 bytes: code, (up << 7) | max(1, delay//10).
    """
    out = bytearray()
    for e in events:
        units = clamp(int(e.get("delay", 0)) // MACRO_DELAY_UNIT_MS, 1, MACRO_DELAY_MAX)
        out += bytes([int(e["code"]) & 0xFF, (0x80 if e.get("up") else 0) | units])
    return bytes(out)


def macro_packets(layer: int, src_hid: int, events: list[dict], repeat: int = 1) -> list[bytes]:
    if not events:
        raise ValueError("macro has no events")
    if len(events) > MAX_MACRO_EVENTS:
        raise ValueError(f"macro too long: {len(events)} events (max {MAX_MACRO_EVENTS})")
    body = bytes([layer, src_hid, clamp(repeat, 1, 255), len(events)]) + encode_macro_events(events)
    return [pkt(OP_MACRO, body), pkt(OP_MACRO_NEXT), pkt(OP_MACRO_COMMIT)]


def shortcut_events(codes: list[int]) -> list[dict]:
    """Chord such as Ctrl+Shift+Esc: press all in order, release in reverse."""
    downs = [{"code": c, "up": False, "delay": 10} for c in codes]
    ups = [{"code": c, "up": True, "delay": 10} for c in reversed(codes)]
    return downs + ups


def reset_keys_packet() -> bytes:
    return pkt(OP_RESET_KEYS)


# ── device settings ────────────────────────────────────────────────────

def sleep_packet(option: int) -> bytes:
    return pkt(OP_SLEEP, [clamp(option, 1, 4)])


def response_packet(gear: int) -> bytes:
    return pkt(OP_RESPONSE, [clamp(gear, 1, 3)])


def fn_mode_packet(swapped: bool) -> bytes:
    return pkt(OP_FN_MODE, [1 if swapped else 0])


def heartbeat_packet() -> bytes:
    return pkt(OP_HEARTBEAT)


def save_packet() -> bytes:
    return pkt(OP_SAVE)
