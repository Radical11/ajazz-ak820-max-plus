// App-drawn lighting effects, rendered from real key positions.
// render(t seconds, opts) -> Uint8Array(324). Shared by the web app and the desktop shell.
import { KEYS, BOUNDS } from '../layout.js'
import { FRAME_BYTES } from './protocol.js'

const SPAN_X = BOUNDS.width - BOUNDS.minX, SPAN_Y = BOUNDS.height - BOUNDS.minY
const POS = KEYS.map(k => ({ led: k.led, x: (k.x + k.w / 2 - BOUNDS.minX) / SPAN_X, y: (k.y + k.h / 2 - BOUNDS.minY) / SPAN_Y, row: k.row }))
const BASE = { red: [254, 40, 50], green: [40, 220, 90], blue: [50, 100, 254], yellow: [254, 200, 40], pink: [254, 80, 200], cyan: [40, 220, 240], white: [240, 240, 240] }

const hsv = (h, s, v) => {
  h = ((h % 1) + 1) % 1
  const i = Math.floor(h * 6), f = h * 6 - i, p = v * (1 - s), q = v * (1 - f * s), u = v * (1 - (1 - f) * s)
  const [r, g, b] = [[v, u, p], [q, v, p], [p, v, u], [p, q, v], [u, p, v], [v, p, q]][i % 6]
  return [r * 254, g * 254, b * 254]
}
const rand = seed => { const x = Math.sin(seed * 12.9898) * 43758.5453; return x - Math.floor(x) }

export const SOFTWARE_EFFECTS = {
  100: { name: 'Lightning Storm', controls: 'BSC' },
  101: { name: 'Matrix Rain', controls: 'BSC' },
  102: { name: 'Campfire', controls: 'BSC' },
  103: { name: 'Starlight', controls: 'BSC' },
  104: { name: 'Radar', controls: 'BSDC' },
  105: { name: 'Ripple', controls: 'BSC' },
  106: { name: 'Aurora', controls: 'BS' },
  107: { name: 'Plasma', controls: 'BS' },
}

/** Returns a stateful renderer for one effect. */
export function createEffect(id, { brightness = 4, speed = 2, direction = 0, color = 'rgb' } = {}) {
  const gain = (Math.min(4, Math.max(0, brightness)) + 1) / 5
  const sp = 0.4 + Math.min(4, Math.max(0, speed)) * 0.4
  const base = BASE[color]
  const tint = (c, k) => (base ? base.map(v => v * k) : c)
  const heat = new Float32Array(108)
  let lastBolt = 0
  return function render(t) {
    const T = t * sp
    const out = new Uint8Array(FRAME_BYTES)
    const put = (led, c) => { out[led * 3] = Math.min(254, c[0] * gain); out[led * 3 + 1] = Math.min(254, c[1] * gain); out[led * 3 + 2] = Math.min(254, c[2] * gain) }
    switch (id) {
      case 100: { // lightning: dim sky, random strikes along a column
        if (T - lastBolt > 0.6 + rand(Math.floor(T)) * 1.6) { lastBolt = T; const cx = rand(T * 7); for (const p of POS) if (Math.abs(p.x - cx) < 0.08 + rand(p.y + T) * 0.05) heat[p.led] = 1 }
        for (const p of POS) { heat[p.led] *= 0.86; const h = heat[p.led]; put(p.led, tint([20 + 234 * h, 10 + 230 * h, 40 + 214 * h], 0.15 + 0.85 * h)) }
        break }
      case 101: // matrix: falling green streaks per column
        for (const p of POS) { const col = Math.floor(p.x * 18), off = rand(col) * 10, v = ((T * 1.4 + off - p.y * 1.2) % 2 + 2) % 2, k = v < 0.35 ? 1 - v / 0.35 : 0; put(p.led, tint([10 * k, 254 * k, 40 * k], k)) }
        break
      case 102: // campfire: warm flicker, hotter at the bottom
        for (const p of POS) { const f = 0.55 + 0.45 * Math.sin(T * 9 + rand(p.led) * 20) * Math.sin(T * 3.3 + p.x * 9), k = Math.max(0, Math.min(1, f * (0.4 + p.y * 0.8))); put(p.led, tint([254 * k, 90 * k * k, 10 * k], k)) }
        break
      case 103: // starlight: random twinkles
        for (const p of POS) { const ph = rand(p.led * 3.1) * 6.28, k = Math.max(0, Math.sin(T * (0.8 + rand(p.led) * 1.5) + ph)) ** 6; put(p.led, base ? base.map(v => v * k) : hsv(rand(p.led), 0.5, k)) }
        break
      case 104: { // radar: rotating beam around the board centre
        const ang = (direction ? -1 : 1) * T * 1.6
        for (const p of POS) { const a = Math.atan2(p.y - 0.5, (p.x - 0.5) * 2.4), d = ((ang - a) % 6.283 + 6.283) % 6.283, k = Math.max(0, 1 - d / 1.6); put(p.led, tint([20 * k, 254 * k, 160 * k], k)) }
        break }
      case 105: // ripple: rings expanding from the centre
        for (const p of POS) { const d = Math.hypot((p.x - 0.5) * 2.4, p.y - 0.5), k = Math.max(0, Math.sin((d * 9 - T * 4))) ** 4; put(p.led, base ? base.map(v => v * k) : hsv(d - T * 0.1, 0.9, k)) }
        break
      case 106: // aurora: slow green/violet curtains
        for (const p of POS) { const w = Math.sin(p.x * 5 + T * 0.9) * 0.5 + Math.sin(p.x * 11 - T * 0.6) * 0.3, k = Math.max(0, 1 - Math.abs(p.y - 0.5 - w * 0.35) * 2.2); put(p.led, hsv(0.38 + 0.4 * Math.sin(p.x * 2 + T * 0.2) * 0.5 + 0.2 * k, 0.8, 0.12 + 0.88 * k)) }
        break
      case 107: // plasma: classic sine plasma in full colour
        for (const p of POS) { const v = Math.sin(p.x * 9 + T) + Math.sin(p.y * 7 - T * 1.3) + Math.sin((p.x + p.y) * 6 + T * 0.7); put(p.led, hsv(v / 6 + T * 0.05, 0.85, 1)) }
        break
    }
    return out
  }
}

/** Typing heat renderer: call hit(led) on key presses. */
export function createHeat({ decay = 0.02, hot = [254, 60, 20], cold = [10, 10, 60] } = {}) {
  const h = new Float32Array(108)
  const render = () => {
    const out = new Uint8Array(FRAME_BYTES)
    for (const p of POS) { h[p.led] = Math.max(0, h[p.led] - decay); const t = h[p.led]; for (let i = 0; i < 3; i++) out[p.led * 3 + i] = cold[i] + (hot[i] - cold[i]) * t }
    return out
  }
  render.hit = led => (h[led] = 1)
  render.configure = o => { decay = o.decay_rate ?? decay; hot = o.hot_color ?? hot; cold = o.cold_color ?? cold }
  return render
}

/** Ambient: sample an image/video into key colours (call with a 24x6 RGBA ImageData). */
export function ambientFrame(img, prev, { saturation = 1.4, brightness = 1 } = {}) {
  const out = new Uint8Array(FRAME_BYTES), W = img.width, H = img.height
  for (const p of POS) {
    const cx = Math.min(W - 1, Math.floor(p.x * W)), cy = Math.min(H - 1, Math.floor((p.row / 5) * (H - 1)))
    const i = (cy * W + cx) * 4, r = img.data[i], g = img.data[i + 1], b = img.data[i + 2], m = (r + g + b) / 3
    ;[r, g, b].forEach((v, k) => { const j = p.led * 3 + k; const val = Math.max(0, Math.min(254, (m + (v - m) * saturation) * brightness)); prev[j] = prev[j] * 0.55 + val * 0.45; out[j] = prev[j] })
  }
  return out
}

/** Spectrum (bass/mid/treble) frame from an AnalyserNode byte spectrum. */
export function spectrumFrame(bins, smoothed, cfg) {
  const out = new Uint8Array(FRAME_BYTES)
  const avg = (a, b) => { let s = 0; for (let i = a; i < b; i++) s += bins[i]; return s / (b - a) / 255 }
  const levels = [avg(1, 4), avg(4, 24), avg(24, 120)].map((v, i) => v * (cfg.sensitivity ?? 5) / 5)
  levels.forEach((v, i) => (smoothed[i] = v > smoothed[i] ? v : smoothed[i] * (cfg.smoothing_falloff ?? 0.82)))
  const cols = [cfg.bass_color ?? [254, 30, 30], cfg.mid_color ?? [30, 220, 30], cfg.treble_color ?? [30, 80, 254]]
  if (cfg.mode === 'volume') {
    const k = Math.min(1, (smoothed[0] + smoothed[1] + smoothed[2]) / 1.5)
    for (const p of POS) for (let i = 0; i < 3; i++) out[p.led * 3 + i] = 254 * k
    return out
  }
  for (const p of POS) {
    const band = p.x < 1 / 3 ? 0 : p.x < 2 / 3 ? 1 : 2, k = Math.min(1, smoothed[band]), lit = (1 - p.y) <= k + 0.05
    for (let i = 0; i < 3; i++) out[p.led * 3 + i] = lit ? cols[band][i] * (0.35 + 0.65 * k) : 0
  }
  return out
}
