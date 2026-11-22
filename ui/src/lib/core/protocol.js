// AJAZZ AK820 Max Plus vendor HID protocol (JS port of app/protocol.py).
// Every packet is 64 bytes: AA 55 CC 33 <opcode> <payload> <zero padding>.
// Shared by the WebHID web app and (later) the desktop shell.

export const MAGIC = [0xAA, 0x55, 0xCC, 0x33]
export const REPORT_LEN = 64
export const VID = 0x1A2C
export const PID_WIRED = 0xA036
export const PID_DONGLE = 0x8FFF
export const VENDOR_USAGE_PAGE = 0xFF02
export const NUM_LEDS = 108
export const FRAME_BYTES = NUM_LEDS * 3
export const LED_MAX = 0xFE

export const OP = {
  MACRO: 0x00, MACRO_NEXT: 0x01, MACRO_COMMIT: 0x02, KEY: 0x04, MODE: 0x07, APPLY: 0x09,
  SAVE: 0x0A, BEGIN: 0x0B, SLEEP: 0x0C, RESPONSE: 0x0D, HEARTBEAT: 0x0E, RESET_KEYS: 0x0F, FN_MODE: 0x10,
}
export const FRAME_OPS = [0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFB]
export const CUSTOM_MODE = 0x17
export const KEY_DEFAULT = 0x00
export const KEY_DISABLED = 0x01
export const MAX_MACRO_EVENTS = Math.floor((REPORT_LEN - 5 - 4) / 2) // 27

export const COLORS = { red: 0, green: 1, blue: 2, yellow: 3, pink: 4, cyan: 5, white: 6, rgb: 7 }
export const SLEEP_OPTIONS = { 1: '5 minutes', 2: '15 minutes', 3: '30 minutes', 4: 'Never' }
export const RESPONSE_OPTIONS = { 1: 'Fastest (wired 2-3 ms)', 2: 'Balanced (wired 4-5 ms)', 3: 'Stable (wired 6-7 ms)' }

export const HARDWARE_MODES = {
  0x00: ['Ripple Wave', 'BSDC'], 0x01: ['Starry Dots', 'BSC'], 0x02: ['Vertical Ripple', 'BSDC'],
  0x03: ['Burst', 'BSDC'], 0x04: ['Spectrum Cycle', 'BS'], 0x05: ['Kaleidoscope', 'BSDC'],
  0x06: ['Static', 'BC'], 0x07: ['Breathing', 'BSC'], 0x08: ['Cross Waves', 'BSC'],
  0x09: ['Dual Wave', 'BSDC'], 0x0A: ['Reactive Breath', 'BSC'], 0x0B: ['Scroll', 'BSC'],
  0x0C: ['Snake', 'BSC'], 0x0D: ['Spiral', 'BSDC'], 0x0E: ['Split Rows', 'BSC'],
  0x0F: ['Rainfall', 'BSC'], 0x10: ['Windmill', 'BSC'], 0x11: ['Sine Wave', 'BSC'], 0x12: ['Gallop', 'BSDC'],
}

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v)

export function pkt(opcode, payload = []) {
  const out = new Uint8Array(REPORT_LEN)
  const body = [...MAGIC, opcode, ...payload]
  if (body.length > REPORT_LEN) throw new RangeError(`payload too long (${body.length} > ${REPORT_LEN})`)
  out.set(body)
  return out
}

export const modePacket = (mode, brightness, speed, direction, color, color2 = 7) =>
  pkt(OP.MODE, [mode & 0xFF, clamp(brightness, 0, 4), clamp(speed, 0, 4), clamp(direction, 0, 1), clamp(color, 0, 7), clamp(color2, 0, 7)])

export const customModePackets = () => [modePacket(CUSTOM_MODE, 4, 3, 0, 7, 0), pkt(OP.BEGIN), pkt(OP.APPLY)]

/** rgb: Uint8Array(324). Values are capped at 0xFE. */
export function framePackets(rgb) {
  if (rgb.length !== FRAME_BYTES) throw new RangeError(`expected ${FRAME_BYTES} bytes, got ${rgb.length}`)
  return FRAME_OPS.map((op, i) => pkt(op, Array.from(rgb.subarray(i * 54, (i + 1) * 54), b => Math.min(b, LED_MAX))))
}

export const keyPacket = (layer, src, dst) => pkt(OP.KEY, [layer, src, dst])

export function encodeMacroEvents(events) {
  const out = []
  for (const e of events) {
    const units = clamp(Math.floor((e.delay ?? 0) / 10), 1, 0x7F)
    out.push(e.code & 0xFF, (e.up ? 0x80 : 0) | units)
  }
  return out
}

export function macroPackets(layer, src, events, repeat = 1) {
  if (!events.length) throw new RangeError('macro has no events')
  if (events.length > MAX_MACRO_EVENTS) throw new RangeError(`macro too long: ${events.length} events (max ${MAX_MACRO_EVENTS})`)
  return [pkt(OP.MACRO, [layer, src, clamp(repeat, 1, 255), events.length, ...encodeMacroEvents(events)]),
          pkt(OP.MACRO_NEXT), pkt(OP.MACRO_COMMIT)]
}

export function shortcutEvents(codes) {
  return [...codes.map(c => ({ code: c, up: false, delay: 10 })), ...[...codes].reverse().map(c => ({ code: c, up: true, delay: 10 }))]
}

export const resetKeysPacket = () => pkt(OP.RESET_KEYS)
export const sleepPacket = o => pkt(OP.SLEEP, [clamp(o, 1, 4)])
export const responsePacket = g => pkt(OP.RESPONSE, [clamp(g, 1, 3)])
export const fnModePacket = swapped => pkt(OP.FN_MODE, [swapped ? 1 : 0])
export const heartbeatPacket = () => pkt(OP.HEARTBEAT)
export const savePacket = () => pkt(OP.SAVE)

/** Parse a 0x0E reply; returns battery % or null. */
export function parseHeartbeat(bytes) {
  const b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  for (let i = 0; i + 5 < b.length; i++) {
    if (b[i] === 0xAA && b[i + 1] === 0x55 && b[i + 2] === 0xCC && b[i + 3] === 0x33 && b[i + 4] === OP.HEARTBEAT) {
      const v = b[i + 5]
      return v > 0 && v <= 100 ? v : null
    }
  }
  return null
}

/** Turn a profile key action into packets (no macro library lookup: pass the macro). */
export function actionPackets(layer, src, action, macro) {
  switch (action.type) {
    case 'key': case 'media': return [keyPacket(layer, src, action.code)]
    case 'disabled': return [keyPacket(layer, src, KEY_DISABLED)]
    case 'default': return [keyPacket(layer, src, KEY_DEFAULT)]
    case 'shortcut': return macroPackets(layer, src, shortcutEvents(action.codes), 1)
    case 'macro':
      if (!macro) throw new Error('macro no longer exists')
      return macroPackets(layer, src, macro.events, macro.repeat ?? 1)
    default: throw new Error(`unknown action ${action.type}`)
  }
}

export const hex = u8 => Array.from(u8, b => b.toString(16).padStart(2, '0')).join('')
