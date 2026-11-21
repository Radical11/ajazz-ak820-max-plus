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
  // P = your own colours, R = reacts to typing
  108: { name: 'Gradient Wave', controls: 'BSDP' },
  109: { name: 'Colour Breathing', controls: 'BSP' },
  110: { name: 'Typing Ripples', controls: 'BSPR' },
  111: { name: 'Key Trails', controls: 'BSPR' },
  112: { name: 'Fireworks', controls: 'BSR' },
  113: { name: 'Heartbeat', controls: 'BSP' },
}

export const DEFAULT_PALETTE = ['#6d5bd0', '#33cfe0', '#f0404e']
const hex3 = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16))
const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t)
/** Smoothly sample a looping palette at position u (0..1). */
function paletteAt(pal, u) {
  const n = pal.length
  if (n === 1) return pal[0]
  const x = (((u % 1) + 1) % 1) * n, i = Math.floor(x)
  const f = x - i, e = f * f * (3 - 2 * f)
  return mix(pal[i % n], pal[(i + 1) % n], e)
}

/** Returns a stateful renderer for one effect. */
export function createEffect(id, { brightness = 4, speed = 2, direction = 0, color = 'rgb', colors = DEFAULT_PALETTE } = {}) {
  const gain = (Math.min(4, Math.max(0, brightness)) + 1) / 5
  const sp = 0.4 + Math.min(4, Math.max(0, speed)) * 0.4
  const base = BASE[color]
  const tint = (c, k) => (base ? base.map(v => v * k) : c)
  const heat = new Float32Array(108)
  let lastBolt = 0
  const pal = (colors?.length ? colors : DEFAULT_PALETTE).map(hex3)
  const posOf = Object.fromEntries(POS.map(p => [p.led, p]))
  let hits = [], now = 0
  const glow = new Float32Array(108), tint3 = Array.from({ length: 108 }, () => [0, 0, 0])
  function render(t) {
    now = t
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
      case 108: // gradient wave through your colours
        for (const p of POS) put(p.led, paletteAt(pal, (direction ? -1 : 1) * (p.x * 0.9 - T * 0.25) + p.y * 0.08))
        break
      case 109: { // breathe, moving to the next colour each breath
        const cyc = T * 0.35, k = Math.sin((cyc % 1) * Math.PI) ** 2, c = pal[Math.floor(cyc) % pal.length]
        for (const p of POS) put(p.led, c.map(v => v * (0.06 + 0.94 * k)))
        break }
      case 110: { // typing ripples: a ring spreads from every key you press
        hits = hits.filter(h => t - h.t < 1.6)
        for (const p of POS) {
          let c = pal[pal.length - 1].map(v => v * 0.05)
          for (const h of hits) {
            const r = (t - h.t) * 1.2 * sp, d = Math.hypot((p.x - h.p.x) * 2.4, p.y - h.p.y), k = Math.max(0, 1 - Math.abs(d - r) * 7) * (1 - (t - h.t) / 1.6)
            if (k > 0) c = mix(c, h.c, Math.min(1, k))
          }
          put(p.led, c)
        }
        break }
      case 111: // key trails: pressed keys flare, then cool through your colours
        for (const p of POS) {
          glow[p.led] = Math.max(0, glow[p.led] - 0.012 * sp)
          const g = glow[p.led]
          put(p.led, g > 0 ? paletteAt(pal, (1 - g) * 0.999).map(v => v * Math.min(1, g * 1.4)) : [0, 0, 0])
        }
        break
      case 112: { // fireworks: each key press bursts into colour around it
        hits = hits.filter(h => t - h.t < 1.2)
        for (const p of POS) {
          let c = [0, 0, 0]
          for (const h of hits) {
            const age = t - h.t, d = Math.hypot((p.x - h.p.x) * 2.4, p.y - h.p.y), k = Math.max(0, 1 - d / (0.05 + age * 0.5 * sp)) * (1 - age / 1.2)
            if (k > 0) c = c.map((v, i) => Math.min(254, v + h.burst[i] * k))
          }
          put(p.led, c)
        }
        break }
      case 113: { // heartbeat: double pulse from the centre
        const ph = (T * 0.6) % 1, beat = Math.exp(-((ph - 0.1) ** 2) / 0.002) + 0.7 * Math.exp(-((ph - 0.28) ** 2) / 0.002)
        for (const p of POS) { const d = Math.hypot((p.x - 0.5) * 2.4, p.y - 0.5); put(p.led, pal[0].map(v => v * Math.min(1, 0.05 + beat * (1.2 - d)))) }
        break }
    }
    return out
  }
  /** Feed a key press (LED index) to reactive effects. */
  render.hit = led => {
    const p = posOf[led]
    if (!p) return
    if (id === 111) glow[led] = 1
    else hits.push({ p, t: now, c: pal[Math.floor(Math.random() * pal.length)], burst: hsv(Math.random(), 0.8, 1) })
    if (hits.length > 40) hits.shift()
  }
  render.reactive = id === 110 || id === 111 || id === 112
  return render
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
