import { writable, derived, get } from 'svelte/store'

// ── bridge: desktop (pywebview) or web (WebHID) ───────────────────────
import { webBackend } from './core/webBackend.js'
let backend = null          // 'desktop' (Python) | 'tauri' | 'web'
let jsBackend = null        // web or Tauri backend object
export const platform = writable('desktop')

export async function api(method, ...args) {
  let res
  if (jsBackend) {
    const fn = jsBackend[method]
    if (!fn) throw new Error(`${method} isn't available in this version`)
    res = await fn.apply(jsBackend, args)
  } else {
    if (!window.pywebview?.api?.[method]) throw new Error('The app backend is still starting')
    res = await window.pywebview.api[method](...args)
  }
  if (!res?.ok) throw new Error(res?.error ?? 'Something went wrong')
  return res
}

export function waitForBackend() {
  if (window.__TAURI_INTERNALS__) {
    return import('./core/desktopBackend.js').then(m => { jsBackend = m.desktopBackend(); backend = 'tauri'; platform.set('desktop'); return 'tauri' })
  }
  return new Promise(resolve => {
    const desktop = () => { backend = 'desktop'; platform.set('desktop'); resolve('desktop') }
    if (window.pywebview?.api?.get_state) return desktop()
    window.addEventListener('pywebviewready', desktop, { once: true })
    let n = 0
    const id = setInterval(() => {
      if (window.pywebview?.api?.get_state) { clearInterval(id); desktop() }
      else if (++n > 8 && !window.pywebview) { clearInterval(id); backend = 'web'; jsBackend = webBackend(); platform.set('web'); resolve('web') }
    }, 100)
  })
}

// ── app state ─────────────────────────────────────────────────────────
export const NUM_LEDS = 108
export const ready = writable(false)
export const page = writable('lighting')          // lighting | keys | macros | profiles | device
export const status = writable({ connected: false, connection: 'none', studio: null, error: '' })
export const settings = writable({})
export const profiles = writable([])
export const profile = writable(null)             // active profile object
export const macros = writable([])
export const modes = writable([])
export const meta = writable({ sleep_options: {}, response_options: {}, max_macro_events: 27, hook_available: true })
export const leds = writable(Array(NUM_LEDS).fill('#000000'))
export const audioDevices = writable([])
export const audioConfig = writable({})
export const pressed = writable(new Set())        // HID codes currently held (key tester)
export const paletteOpen = writable(false)
// what the app is sending to the keyboard right now (null when the keyboard runs its own effect)
export const liveFrame = writable(null)
window.addEventListener('ak:frame', e => {
  const f = e.detail
  if (!f) return liveFrame.set(null)
  const out = new Array(108)
  for (let i = 0; i < 108; i++) out[i] = '#' + ((1 << 24) | (f[i * 3] << 16) | (f[i * 3 + 1] << 8) | f[i * 3 + 2]).toString(16).slice(1)
  liveFrame.set(out)
})

export const activeName = derived(profile, p => p?.name ?? '—')

// ── theme: light / dark / follow Windows ──────────────────────────────
const darkQuery = window.matchMedia('(prefers-color-scheme: dark)')
function applyTheme(mode) {
  const dark = mode === 'dark' || ((!mode || mode === 'system') && darkQuery.matches)
  document.documentElement.classList.toggle('dark', dark)
}
settings.subscribe(s => applyTheme(s?.theme))
darkQuery.addEventListener('change', () => applyTheme(get(settings)?.theme))

export async function loadState() {
  const s = await api('get_state')
  status.set(s.status)
  settings.set(s.settings)
  profiles.set(s.profiles)
  profile.set(s.profile)
  macros.set(s.macros)
  modes.set(s.modes)
  meta.set({ sleep_options: s.sleep_options, response_options: s.response_options,
             max_macro_events: s.max_macro_events, hook_available: s.hook_available, colors: s.colors,
             web: s.platform === 'web', hid_supported: s.hid_supported ?? true, jsBackend: !!jsBackend })
  audioDevices.set(s.audio_devices)
  audioConfig.set(s.audio)
  if (s.profile?.lighting?.kind === 'custom') leds.set(s.profile.lighting.leds)
  else leds.set(s.leds)
  ready.set(true)
}

// events pushed from Python
window.addEventListener('ak:status', e => status.set(e.detail))
window.addEventListener('ak:profile', e => {
  profile.set(e.detail.profile)
  status.set(e.detail.status)
  const p = e.detail.profile
  if (p?.lighting?.kind === 'custom') leds.set(p.lighting.leds)
  toast(`Switched to ${p.name}`, 'info')
})
window.addEventListener('ak:key', e => {
  const { hid, down } = e.detail
  if (hid == null) return
  pressed.update(s => { const n = new Set(s); down ? n.add(hid) : n.delete(hid); return n })
})

// ── run an action with a toast on failure ─────────────────────────────
export async function run(method, args = [], { success, quiet } = {}) {
  try {
    const res = await api(method, ...args)
    if (res.profile) profile.set(res.profile)
    if (res.profiles) profiles.set(res.profiles)
    if (res.macros) macros.set(res.macros)
    if (res.status) status.set(res.status)
    if (res.warnings?.length) toast(`Some keys couldn't be applied: ${res.warnings.join(', ')}`, 'warn', 5000)
    if (success) toast(success, 'ok')
    return res
  } catch (e) {
    if (!quiet) toast(e.message, 'bad', 5000)
    throw e
  }
}

// ── toasts ────────────────────────────────────────────────────────────
export const toasts = writable([])
let tid = 0
export function toast(message, kind = 'info', ms = 2800) {
  const id = ++tid
  toasts.update(t => [...t.slice(-3), { id, message, kind }])
  setTimeout(() => toasts.update(t => t.filter(x => x.id !== id)), ms)
}

export function profileSnapshot() { return get(profile) }
