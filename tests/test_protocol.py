"""Tests for app.protocol packet builders.

The captured vectors below come from the official app and must not change.
"""

import pytest

from app import protocol as P


def hx(b: bytes) -> str:
    return b.hex()


def assert_well_formed(pkt: bytes) -> None:
    assert len(pkt) == 64
    assert pkt[:4] == bytes([0xAA, 0x55, 0xCC, 0x33])


# ── captured vectors ───────────────────────────────────────────────────

@pytest.mark.parametrize("layer, src, dst, expected", [
    (1, 0x14, 0x04, "aa55cc3304011404"),
    (1, 0x3A, 0x01, "aa55cc3304013a01"),  # disable
    (1, 0x3A, 0x00, "aa55cc3304013a00"),
    (2, 0x17, 0xEE, "aa55cc33040217ee"),
])
def test_key_packet_captured_vectors(layer, src, dst, expected):
    p = P.key_packet(layer, src, dst)
    assert_well_formed(p)
    assert hx(p).startswith(expected)


MACRO_EVENTS = [
    (0x07, False, 30), (0x09, False, 30), (0x07, True, 130), (0x09, True, 30),
    (0x16, False, 50), (0x16, True, 30), (0x07, False, 60), (0x07, True, 40),
    (0x04, False, 30), (0x16, False, 30), (0x04, True, 30), (0x16, True, 30),
    (0x07, False, 40), (0x07, True, 0),
]


def _events(seq):
    return [{"code": c, "up": u, "delay": d} for c, u, d in seq]


def test_macro_captured_vector_first_packet():
    pkts = P.macro_packets(1, 0x3A, _events(MACRO_EVENTS))
    assert len(pkts) == 3
    for p in pkts:
        assert_well_formed(p)
    assert hx(pkts[0]).startswith(
        "aa55cc3300013a010e07030903078d09831605168307060784040316030483168307040781"
    )
    assert hx(pkts[1]).startswith("aa55cc3301")
    assert hx(pkts[2]).startswith("aa55cc3302")
    # remainder of the packets is zero padding
    assert set(pkts[1][5:]) == {0}
    assert set(pkts[2][5:]) == {0}


def test_shortcut_macro_captured_vector():
    pkts = P.macro_packets(1, 0x3A, P.shortcut_events([0xE0, 0x04]))
    assert hx(pkts[0]).startswith("aa55cc3300013a0104e00104010481e081")


# ── simple packets ─────────────────────────────────────────────────────

@pytest.mark.parametrize("option, expected", [
    (1, "aa55cc330c01"), (2, "aa55cc330c02"), (3, "aa55cc330c03"), (4, "aa55cc330c04"),
])
def test_sleep_packet(option, expected):
    p = P.sleep_packet(option)
    assert_well_formed(p)
    assert hx(p).startswith(expected)


@pytest.mark.parametrize("gear", [1, 2, 3])
def test_response_packet(gear):
    p = P.response_packet(gear)
    assert_well_formed(p)
    assert hx(p).startswith(f"aa55cc330d0{gear}")


def test_fn_mode_packets():
    assert hx(P.fn_mode_packet(True)).startswith("aa55cc331001")
    assert hx(P.fn_mode_packet(False)).startswith("aa55cc331000")


def test_mode_packet_captured_prefix():
    p = P.mode_packet(7, 4, 3, 0, 2)
    assert_well_formed(p)
    assert hx(p).startswith("aa55cc33070704030002")


def test_reset_and_save_packets():
    assert hx(P.reset_keys_packet()).startswith("aa55cc330f")
    assert hx(P.save_packet()).startswith("aa55cc330a")
    assert_well_formed(P.reset_keys_packet())
    assert_well_formed(P.save_packet())


def test_heartbeat_packet_is_well_formed():
    p = P.heartbeat_packet()
    assert_well_formed(p)
    assert p[4] == P.OP_HEARTBEAT


def test_custom_mode_packets_are_all_64_bytes():
    pkts = P.custom_mode_packets()
    assert len(pkts) == 3
    for p in pkts:
        assert_well_formed(p)


# ── clamping ───────────────────────────────────────────────────────────

def test_mode_packet_clamps_brightness_to_4():
    p = P.mode_packet(7, 9, 3, 0, 2)
    # layout: header(4) opcode(1) mode(1) brightness(1) ...
    assert p[6] == 4


def test_sleep_packet_clamps_to_4():
    p = P.sleep_packet(9)
    assert p[5] == 4


def test_sleep_packet_clamps_low_to_1():
    assert P.sleep_packet(0)[5] == 1


def test_macro_delay_zero_maps_to_unit_1():
    # delay 0 -> units clamped to minimum 1, key-up bit clear
    assert P.encode_macro_events([{"code": 4, "up": False, "delay": 0}]) == bytes([0x04, 0x01])


def test_macro_delay_5000_maps_to_0x7f():
    assert P.encode_macro_events([{"code": 4, "up": True, "delay": 5000}]) == bytes([0x04, 0x80 | 0x7F])


# ── frames ─────────────────────────────────────────────────────────────

def test_frame_packets_shape_and_opcodes():
    pkts = P.frame_packets(bytes(P.FRAME_BYTES))
    assert len(pkts) == 6
    assert [p[4] for p in pkts] == [0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFB]
    for p in pkts:
        assert_well_formed(p)


def test_frame_packets_cap_led_values_to_0xfe():
    pkts = P.frame_packets(bytes([0xFF]) * P.FRAME_BYTES)
    for p in pkts:
        payload = p[5:5 + 54]
        assert len(payload) == 54
        assert set(payload) == {0xFE}


def test_frame_packets_leave_small_values_alone():
    rgb = bytes(i % 0xFE for i in range(P.FRAME_BYTES))
    pkts = P.frame_packets(rgb)
    joined = b"".join(p[5:59] for p in pkts)
    assert joined == rgb


@pytest.mark.parametrize("n", [0, 1, P.FRAME_BYTES - 1, P.FRAME_BYTES + 1])
def test_frame_packets_wrong_length_raises(n):
    with pytest.raises(ValueError):
        P.frame_packets(bytes(n))


# ── macro limits ───────────────────────────────────────────────────────

def test_macro_zero_events_raises():
    with pytest.raises(ValueError):
        P.macro_packets(1, 0x3A, [])


def test_macro_28_events_raises():
    events = [{"code": 4, "up": False, "delay": 10}] * 28
    with pytest.raises(ValueError):
        P.macro_packets(1, 0x3A, events)


def test_macro_27_events_is_the_maximum():
    events = [{"code": 4, "up": False, "delay": 10}] * 27
    pkts = P.macro_packets(1, 0x3A, events)
    assert len(pkts) == 3
    assert pkts[0][8] == 27  # event count byte (header 4 + opcode 1 + layer, src, repeat)
    assert pkts[0][9:9 + 54] == bytes([0x04, 0x01]) * 27
