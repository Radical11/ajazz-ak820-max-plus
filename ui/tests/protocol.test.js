// Tests for the AK820 vendor protocol builders. Mirrors tests/test_protocol.py
// (captured vectors must not change) using only node:test and node:assert/strict.
import { test, describe } from 'node:test'
import assert from 'node:assert/strict'
import * as P from '../src/lib/core/protocol.js'

const { hex } = P

function assertWellFormed(pkt) {
  assert.equal(pkt.length, 64, 'packet must be 64 bytes')
  assert.equal(hex(pkt.subarray(0, 4)), 'aa55cc33', 'packet must start with AA 55 CC 33')
}

function assertPrefix(pkt, prefix) {
  assertWellFormed(pkt)
  assert.equal(hex(pkt).slice(0, prefix.length), prefix)
}

function withZeros(bytes, len = 64) {
  const out = new Uint8Array(len)
  out.set(bytes)
  return out
}

const isZeroFrom = (pkt, start) => pkt.subarray(start).every(b => b === 0)

const MACRO_EVENTS = [
  [0x07, false, 30], [0x09, false, 30], [0x07, true, 130], [0x09, true, 30],
  [0x16, false, 50], [0x16, true, 30], [0x07, false, 60], [0x07, true, 40],
  [0x04, false, 30], [0x16, false, 30], [0x04, true, 30], [0x16, true, 30],
  [0x07, false, 40], [0x07, true, 0],
].map(([code, up, delay]) => ({ code, up, delay }))

describe('key packets', () => {
  test('remap 0x14 -> 0x04 on layer 1 matches captured vector', () => {
    assertPrefix(P.keyPacket(1, 0x14, 0x04), 'aa55cc3304011404')
  })

  test('disable key 0x3A (dst 0x01) matches captured vector', () => {
    assertPrefix(P.keyPacket(1, 0x3A, 0x01), 'aa55cc3304013a01')
  })

  test('default key 0x3A (dst 0x00) matches captured vector', () => {
    assertPrefix(P.keyPacket(1, 0x3A, 0x00), 'aa55cc3304013a00')
  })

  test('Fn layer (layer 2) remap matches captured vector', () => {
    assertPrefix(P.keyPacket(2, 0x17, 0xEE), 'aa55cc33040217ee')
  })

  test('actionPackets maps disabled and default to KEY_DISABLED / KEY_DEFAULT', () => {
    assertPrefix(P.actionPackets(1, 0x3A, { type: 'disabled' })[0], 'aa55cc3304013a01')
    assertPrefix(P.actionPackets(1, 0x3A, { type: 'default' })[0], 'aa55cc3304013a00')
  })
})

describe('macro packets', () => {
  test('14-event captured vector: first packet prefix', () => {
    const pkts = P.macroPackets(1, 0x3A, MACRO_EVENTS)
    assert.equal(pkts.length, 3)
    pkts.forEach(assertWellFormed)
    assertPrefix(pkts[0], 'aa55cc3300013a010e07030903078d09831605168307060784040316030483168307040781')
  })

  test('14-event vector: event count byte and repeat byte', () => {
    const [head] = P.macroPackets(1, 0x3A, MACRO_EVENTS)
    assert.equal(head[7], 1, 'repeat')
    assert.equal(head[8], 14, 'event count')
  })

  test('14-event vector: follow-up packets 01 and 02 are zero-padded', () => {
    const [, next, commit] = P.macroPackets(1, 0x3A, MACRO_EVENTS)
    assertPrefix(next, 'aa55cc3301')
    assertPrefix(commit, 'aa55cc3302')
    assert.ok(isZeroFrom(next, 5), 'MACRO_NEXT payload must be zero')
    assert.ok(isZeroFrom(commit, 5), 'MACRO_COMMIT payload must be zero')
  })

  test('Ctrl+A shortcut captured vector', () => {
    const pkts = P.macroPackets(1, 0x3A, P.shortcutEvents([0xE0, 0x04]))
    assertPrefix(pkts[0], 'aa55cc3300013a0104e00104010481e081')
  })

  test('shortcutEvents releases keys in reverse order', () => {
    assert.deepEqual(
      P.shortcutEvents([0xE0, 0x04]).map(e => [e.code, e.up]),
      [[0xE0, false], [0x04, false], [0x04, true], [0xE0, true]],
    )
  })

  test('actionPackets shortcut produces the same packets as the captured vector', () => {
    const pkts = P.actionPackets(1, 0x3A, { type: 'shortcut', codes: [0xE0, 0x04] })
    assert.equal(pkts.length, 3)
    assertPrefix(pkts[0], 'aa55cc3300013a0104e00104010481e081')
  })

  test('actionPackets macro uses macro.events and macro.repeat', () => {
    const pkts = P.actionPackets(1, 0x3A, { type: 'macro' }, { events: MACRO_EVENTS, repeat: 3 })
    assertPrefix(pkts[0], 'aa55cc3300013a030e07030903')
  })

  test('actionPackets macro defaults repeat to 1 when unset', () => {
    const pkts = P.actionPackets(1, 0x3A, { type: 'macro' }, { events: MACRO_EVENTS })
    assert.equal(pkts[0][7], 1)
  })

  test('actionPackets macro without a macro object throws', () => {
    assert.throws(() => P.actionPackets(1, 0x3A, { type: 'macro' }), /macro no longer exists/)
  })

  test('actionPackets rejects an unknown action type', () => {
    assert.throws(() => P.actionPackets(1, 0x3A, { type: 'bogus' }), /unknown action/)
  })

  test('zero events throws RangeError', () => {
    assert.throws(() => P.macroPackets(1, 0x3A, []), RangeError)
  })

  test('28 events throws RangeError', () => {
    const events = Array.from({ length: 28 }, () => ({ code: 4, up: false, delay: 10 }))
    assert.throws(() => P.macroPackets(1, 0x3A, events), RangeError)
  })

  test('27 events is the maximum and encodes to three packets', () => {
    const events = Array.from({ length: 27 }, () => ({ code: 4, up: false, delay: 10 }))
    const pkts = P.macroPackets(1, 0x3A, events)
    assert.equal(P.MAX_MACRO_EVENTS, 27)
    assert.equal(pkts.length, 3)
    assert.equal(pkts[0][8], 27)
    const expected = Array.from({ length: 27 }, () => [0x04, 0x01]).flat()
    assert.deepEqual(Array.from(pkts[0].subarray(9, 9 + 54)), expected)
  })
})

describe('simple packets', () => {
  for (const option of [1, 2, 3, 4]) {
    test(`sleep option ${option}`, () => {
      assertPrefix(P.sleepPacket(option), `aa55cc330c0${option}`)
    })
  }

  for (const gear of [1, 2, 3]) {
    test(`response gear ${gear}`, () => {
      assertPrefix(P.responsePacket(gear), `aa55cc330d0${gear}`)
    })
  }

  test('fn mode on and off', () => {
    assertPrefix(P.fnModePacket(true), 'aa55cc331001')
    assertPrefix(P.fnModePacket(false), 'aa55cc331000')
  })

  test('mode packet captured prefix', () => {
    assertPrefix(P.modePacket(7, 4, 3, 0, 2), 'aa55cc33070704030002')
  })

  test('reset and save packets', () => {
    assertPrefix(P.resetKeysPacket(), 'aa55cc330f')
    assertPrefix(P.savePacket(), 'aa55cc330a')
  })

  test('heartbeat request packet is well formed with opcode 0x0E', () => {
    const p = P.heartbeatPacket()
    assertWellFormed(p)
    assert.equal(p[4], P.OP.HEARTBEAT)
  })

  test('custom mode packets: three well-formed packets', () => {
    const pkts = P.customModePackets()
    assert.equal(pkts.length, 3)
    pkts.forEach(assertWellFormed)
  })
})

describe('clamping', () => {
  test('mode brightness 9 clamps to 4', () => {
    assert.equal(P.modePacket(7, 9, 3, 0, 2)[6], 4)
  })

  test('sleep 9 clamps to 4', () => {
    assert.equal(P.sleepPacket(9)[5], 4)
  })

  test('sleep 0 clamps to 1', () => {
    assert.equal(P.sleepPacket(0)[5], 1)
  })

  test('macro delay 0 ms maps to unit 1, key-up bit clear', () => {
    assert.deepEqual(P.encodeMacroEvents([{ code: 4, up: false, delay: 0 }]), [0x04, 0x01])
  })

  test('macro delay 5000 ms maps to 0x7F with key-up bit set', () => {
    assert.deepEqual(P.encodeMacroEvents([{ code: 4, up: true, delay: 5000 }]), [0x04, 0x80 | 0x7F])
  })
})

describe('frame packets', () => {
  test('six packets with opcodes F6..FB, all well formed', () => {
    const pkts = P.framePackets(new Uint8Array(P.FRAME_BYTES))
    assert.equal(pkts.length, 6)
    assert.deepEqual(pkts.map(p => p[4]), [0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFB])
    pkts.forEach(assertWellFormed)
  })

  test('LED values above 0xFE are capped to 0xFE', () => {
    const pkts = P.framePackets(new Uint8Array(P.FRAME_BYTES).fill(0xFF))
    for (const p of pkts) {
      const payload = p.subarray(5, 5 + 54)
      assert.equal(payload.length, 54)
      assert.ok(payload.every(b => b === 0xFE))
    }
  })

  test('values at or below 0xFE pass through unchanged', () => {
    const rgb = Uint8Array.from({ length: P.FRAME_BYTES }, (_, i) => i % 0xFE)
    const pkts = P.framePackets(rgb)
    const joined = new Uint8Array(P.FRAME_BYTES)
    pkts.forEach((p, i) => joined.set(p.subarray(5, 59), i * 54))
    assert.deepEqual(joined, rgb)
  })

  for (const n of [0, 1, P.FRAME_BYTES - 1, P.FRAME_BYTES + 1]) {
    test(`wrong frame length ${n} throws RangeError`, () => {
      assert.throws(() => P.framePackets(new Uint8Array(n)), RangeError)
    })
  }
})

describe('parseHeartbeat', () => {
  test('aa55cc330e3903 + zeros reads battery 57', () => {
    assert.equal(P.parseHeartbeat(withZeros([0xAA, 0x55, 0xCC, 0x33, 0x0E, 0x39, 0x03])), 57)
  })

  test('same reply preceded by a 0x00 report byte still reads 57', () => {
    assert.equal(P.parseHeartbeat(withZeros([0x00, 0xAA, 0x55, 0xCC, 0x33, 0x0E, 0x39, 0x03])), 57)
  })

  test('plain array input is accepted', () => {
    assert.equal(P.parseHeartbeat([0xAA, 0x55, 0xCC, 0x33, 0x0E, 0x39, 0x03, 0, 0]), 57)
  })

  test('garbage bytes return null', () => {
    assert.equal(P.parseHeartbeat(withZeros([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE])), null)
  })

  test('all-zero report returns null', () => {
    assert.equal(P.parseHeartbeat(new Uint8Array(64)), null)
  })

  test('battery value 0 or above 100 returns null', () => {
    assert.equal(P.parseHeartbeat(withZeros([0xAA, 0x55, 0xCC, 0x33, 0x0E, 0x00])), null)
    assert.equal(P.parseHeartbeat(withZeros([0xAA, 0x55, 0xCC, 0x33, 0x0E, 101])), null)
  })
})

describe('actionPackets', () => {
  test('key action emits one key packet with the code as destination', () => {
    const pkts = P.actionPackets(1, 0x14, { type: 'key', code: 0x04 })
    assert.equal(pkts.length, 1)
    assertPrefix(pkts[0], 'aa55cc3304011404')
  })

  test('media action emits one key packet with the code as destination', () => {
    const pkts = P.actionPackets(1, 0x14, { type: 'media', code: 0x04 })
    assert.equal(pkts.length, 1)
    assertPrefix(pkts[0], 'aa55cc3304011404')
  })

  test('disabled action emits KEY_DISABLED', () => {
    assert.equal(P.actionPackets(1, 0x3A, { type: 'disabled' })[0][7], P.KEY_DISABLED)
  })

  test('default action emits KEY_DEFAULT', () => {
    assert.equal(P.actionPackets(1, 0x3A, { type: 'default' })[0][7], P.KEY_DEFAULT)
  })
})
