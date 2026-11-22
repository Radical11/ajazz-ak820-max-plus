// Web backend: talks to the keyboard through WebHID (Chrome / Edge), keeps profiles,
// macros and settings in localStorage, and runs live lighting in the page.
// The desktop (Tauri) backend extends this class.
import * as P from './protocol.js'
import { SOFTWARE_EFFECTS, createEffect, createHeat, ambientFrame, spectrumFrame } from './effects.js'
import { KEY_BY_HID, KEYS } from '../layout.js'
import { DOM_CODE_TO_HID } from '../keycodes.js'

const LS = 'ak820studio:'
const load = (k, d) => { try { return JSON.parse(localStorage.getItem(LS + k)) ?? d } catch { return d } }
const save = (k, v) => localStorage.setItem(LS + k, JSON.stringify(v))
const ok = (o = {}) => ({ ok: true, ...o })
const err = e => ({ ok: false, error: String(e?.message ?? e) })
const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }))
const slug = s => (s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'profile')
const hexToRgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16))
const DESKTOP_ONLY = 'This needs the AK820 Studio desktop app: browsers can\'t see keys pressed in other apps.'

const DEFAULT_PROFILE = {
  id: 'default', name: 'Default', apps: [],
  lighting: { kind: 'hardware', mode: 7, brightness: 4, speed: 3, direction: 0, color: 'blue', color2: 'rgb' },
  keymap: { 1: {}, 2: {} }, device: { sleep: 3, response: 1, fn_swap: false },
  game_mode: { win: false, alt_tab: false, alt_f4: false }, layers: {},
}
const DEFAULT_SETTINGS = { active_profile: 'default', auto_switch: false, theme: 'system', typing_stats: false }
const norm = p => ({ ...structuredClone(DEFAULT_PROFILE), ...p, keymap: { 1: { ...(p.keymap?.[1] ?? {}) }, 2: { ...(p.keymap?.[2] ?? {}) } },
  device: { ...DEFAULT_PROFILE.device, ...(p.device ?? {}) }, game_mode: { ...DEFAULT_PROFILE.game_mode, ...(p.game_mode ?? {}) } })

export class WebBackend {
  constructor() {
    this.device = null
    this.battery = null
    this.queue = Promise.resolve()
    this.lastFrame = null
    this.custom = false
    this.studio = null
    this.loop = null
    this.media = null
    this.error = ''
    this.leds = Array(108).fill('#000000')
    this.profiles = load('profiles', null) ?? { default: structuredClone(DEFAULT_PROFILE) }
    this.macros = load('macros', [])
    this.settings = { ...DEFAULT_SETTINGS, ...load('settings', {}) }
    this.caps = false
    this.dim = 1
    this.asleep = false
    this.lastActivity = Date.now()
    window.addEventListener('pointermove', () => (this.lastActivity = Date.now()), { passive: true })
    setInterval(() => this._scheduleTick(), 5000)
    setTimeout(() => this._scheduleTick(), 0)
    setInterval(() => {   // keep the focus timer bar moving over static lighting
      const t = this._active().layers?.timer
      if (t?.on && t.ends_at && this.custom && this.base && !this.loop && !this.asleep) this._frame(this.base).catch(() => {})
    }, 1000)
    this.inPageKeys = new Set()
    window.addEventListener('keydown', e => this._pageKey(e, true), true)
    window.addEventListener('keyup', e => this._pageKey(e, false), true)
    if ('hid' in navigator) {
      navigator.hid.addEventListener('disconnect', e => { if (e.device === this.device) { this.device = null; this.error = 'Keyboard disconnected'; emit('ak:status', this._status()) } })
      navigator.hid.addEventListener('connect', () => this._autoConnect())
    }
  }

  get supported() { return 'hid' in navigator }

  // ── lighting schedule: dim at night, lights off when you step away ──
  _scheduleTick() {
    const sc = this.settings.schedule ?? {}
    const n = sc.night ?? {}, mins = s => { const [h, m] = (s || '0:0').split(':').map(Number); return h * 60 + m }
    const d = new Date(), cur = d.getHours() * 60 + d.getMinutes(), a = mins(n.from ?? '22:00'), b = mins(n.to ?? '07:00')
    const night = !!n.on && (a <= b ? cur >= a && cur < b : cur >= a || cur < b)
    const dim = night ? Math.max(0.05, Math.min(1, n.level ?? 0.3)) : 1
    if (dim !== this.dim) { this.dim = dim; if (this.device && !this.asleep) this._applyLighting(this._active().lighting).catch(() => {}) }
    return this._idleSeconds().then(idle => {
      const limit = (sc.idle?.minutes ?? 10) * 60
      if (sc.idle?.on && this.idleSupported && idle >= limit && !this.asleep && this.device) this._lightsOut()
      else if (this.asleep && (idle < 5 || !sc.idle?.on)) this._wake()
    })
  }
  get idleSupported() { return false }   // a browser tab can't see input in other apps
  async _idleSeconds() { return (Date.now() - (this.lastActivity ?? Date.now())) / 1000 }
  async _lightsOut() {
    this._stopStudio(); await this._custom().catch(() => {})
    await this._send(P.framePackets(new Uint8Array(324))).catch(() => {})
    this.asleep = true; emit('ak:status', this._status())
  }
  async _wake() { this.asleep = false; this.lastFrame = null; await this._applyLighting(this._active().lighting).catch(() => {}); emit('ak:status', this._status()) }
  _persist() { save('profiles', this.profiles); save('macros', this.macros); save('settings', this.settings) }
  _active() { return norm(this.profiles[this.settings.active_profile] ?? this.profiles.default) }
  _list() { return Object.values(this.profiles).map(norm).sort((a, b) => (a.id !== 'default') - (b.id !== 'default') || a.name.localeCompare(b.name)) }
  _status() {
    return { connected: !!this.device, connection: this.device ? (this.device.productId === P.PID_WIRED ? 'wired' : 'wireless') : 'none',
      studio: this.studio, error: this.error, active_profile: this.settings.active_profile, auto_profile: null, foreground: '',
      battery: this.device ? this.battery : null, firmware: null, platform: 'web', asleep: this.asleep, dimmed: this.dim < 1, idle_supported: this.idleSupported }
  }

  // ── transport ──────────────────────────────────────────────────────
  _send(packets) {
    const dev = this.device
    if (!dev) return Promise.reject(new Error('Connect the keyboard first'))
    const task = async () => { for (const p of packets) await dev.sendReport(0, p) }
    const run = this.queue.then(task, task)
    this.queue = run.catch(() => {})
    return run
  }
  async _open(dev) {
    if (!dev.opened) await dev.open()
    this.device = dev; this.error = ''; this.custom = false; this.lastFrame = null
    dev.addEventListener('inputreport', e => { const b = P.parseHeartbeat(new Uint8Array(e.data.buffer)); if (b != null && b !== this.battery) { this.battery = b; emit('ak:status', this._status()) } })
    clearInterval(this.hb)
    this.hb = setInterval(() => this.device && this._send([P.heartbeatPacket()]).catch(() => {}), 2500)
    this._send([P.heartbeatPacket()]).catch(() => {})
    try { await this._applyLighting(this._active().lighting) } catch {}
    emit('ak:status', this._status())
  }
  _pickVendor(devs) { return devs.find(d => d.vendorId === P.VID && d.collections.some(c => c.usagePage === P.VENDOR_USAGE_PAGE)) }
  async _autoConnect() {
    if (!this.supported || this.device) return
    const dev = this._pickVendor(await navigator.hid.getDevices())
    if (dev) try { await this._open(dev) } catch (e) { this.error = String(e.message ?? e) }
  }
  async connect_device() {
    if (!this.supported) return err('This browser can\'t talk to keyboards. Use Chrome or Edge.')
    try {
      const filters = [P.PID_WIRED, P.PID_DONGLE].map(productId => ({ vendorId: P.VID, productId, usagePage: P.VENDOR_USAGE_PAGE }))
      const devs = await navigator.hid.requestDevice({ filters })
      const dev = this._pickVendor(devs)
      if (!dev) return err('No keyboard was chosen')
      await this._open(dev)
      return ok({ status: this._status() })
    } catch (e) { return err(e) }
  }

  // ── lighting ───────────────────────────────────────────────────────
  async _frame(rgb, force = false) {
    if (this.asleep) return
    let out = this._overlay(rgb)
    if (this.dim < 1) out = out.map(v => v * this.dim)
    const now = performance.now()
    if (now - (this.mirrorAt ?? 0) > 50) { this.mirrorAt = now; emit('ak:frame', out) }
    const key = out.join(',')
    if (!force && key === this.lastFrame) return
    this.lastFrame = key
    await this._send(P.framePackets(out))
  }
  _overlay(rgb) {
    const L = this._active().layers ?? {}
    const out = new Uint8Array(rgb)
    const paint = (led, hexc) => out.set(hexToRgb(hexc), led * 3)
    if (L.highlight?.on) for (const h of L.highlight.keys ?? []) { const k = KEY_BY_HID[h]; if (k) paint(k.led, L.highlight.color) }
    const gm = this._active().game_mode ?? {}
    if (L.game?.on ?? true) for (const [k, h] of [['win', 0xE3], ['alt_tab', 0x2B], ['alt_f4', 0x3D]]) if (gm[k]) paint(KEY_BY_HID[h].led, L.game?.color ?? '#f0404e')
    if ((L.caps?.on ?? true) && this.caps) paint(KEY_BY_HID[0x39].led, L.caps?.color ?? '#ffffff')
    if (L.timer?.on && L.timer.ends_at) {
      const left = Math.max(0, (L.timer.ends_at - Date.now()) / 1000), total = (L.timer.minutes ?? 25) * 60
      const row = KEYS.filter(k => k.row === 1).sort((a, b) => a.x - b.x)
      const n = Math.ceil((left / total) * row.length)
      row.forEach((k, i) => i < n ? paint(k.led, L.timer.color ?? '#6d5bd0') : left === 0 && (Date.now() / 500 | 0) % 2 && paint(k.led, '#f0404e'))
    }
    if (this.lensKeys) { const o = new Uint8Array(rgb.length); for (const [led, c] of this.lensKeys) o.set(c, led * 3); return o }
    return out
  }
  async _custom() { if (!this.custom) { await this._send(P.customModePackets()); this.custom = true; this.lastFrame = null } }
  _stopStudio() {
    clearInterval(this.loop); this.loop = null
    if (this.media) { this.media.getTracks().forEach(t => t.stop()); this.media = null }
    this.audioCtx?.close?.(); this.audioCtx = null
    this.studio = null; this.heat = null; this.effect = null
    emit('ak:frame', null)
  }
  async _applyLighting(L) {
    this._stopStudio()
    this.base = null
    if (this.asleep) return          // applied when you come back (_wake)
    if (L.kind === 'hardware') {
      if (SOFTWARE_EFFECTS[L.mode]) return this._startEffect(L)
      this.custom = false
      emit('ak:frame', null)
      return this._send([P.modePacket(+L.mode, this.dim < 1 ? Math.min(+L.brightness, Math.round(4 * this.dim)) : +L.brightness, +L.speed, +L.direction, P.COLORS[L.color] ?? 7, P.COLORS[L.color2] ?? 7)])
    }
    if (L.kind === 'custom') {
      this.leds = L.leds
      await this._custom()
      const rgb = new Uint8Array(324); L.leds.forEach((h, i) => rgb.set(hexToRgb(h), i * 3))
      this.base = rgb
      return this._frame(rgb, true)
    }
    if (L.kind === 'studio') return this._startStudio(L.engine, L.config ?? {})
  }
  async _startEffect(cfg) {
    await this._custom()
    const render = createEffect(+cfg.mode, cfg), t0 = performance.now()
    this.effect = render
    this.studio = 'effect'
    this.loop = setInterval(() => this._frame(render((performance.now() - t0) / 1000)).catch(() => {}), 40)
  }
  async _startStudio(engine, cfg) {
    await this._custom()
    if (engine === 'effect') return this._startEffect(cfg)
    if (engine === 'heatmap') {
      this.heat = createHeat(); this.heat.configure(cfg)
      this.loop = setInterval(() => this._frame(this.heat()).catch(() => {}), 33)
    } else if (engine === 'audio') {
      const stream = cfg.device_id === 'system'
        ? await navigator.mediaDevices.getDisplayMedia({ audio: true, video: true })
        : await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!stream.getAudioTracks().length) { stream.getTracks().forEach(t => t.stop()); throw new Error('No audio was shared. Tick "Share system audio" in the picker.') }
      this.media = stream
      this.audioCtx = new AudioContext()
      const an = this.audioCtx.createAnalyser(); an.fftSize = 1024
      this.audioCtx.createMediaStreamSource(stream).connect(an)
      const bins = new Uint8Array(an.frequencyBinCount), sm = [0, 0, 0]
      this.audioCfg = { ...cfg }
      this.loop = setInterval(() => { an.getByteFrequencyData(bins); this._frame(spectrumFrame(bins, sm, this.audioCfg)).catch(() => {}) }, 33)
    } else if (engine === 'ambient') {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 20 }, audio: false })
      this.media = stream
      const video = Object.assign(document.createElement('video'), { srcObject: stream, muted: true }); await video.play()
      const cv = new OffscreenCanvas(24, 6), cx = cv.getContext('2d', { willReadFrequently: true }), prev = new Float32Array(324)
      this.loop = setInterval(() => { cx.drawImage(video, 0, 0, 24, 6); this._frame(ambientFrame(cx.getImageData(0, 0, 24, 6), prev, cfg)).catch(() => {}) }, 1000 / (cfg.fps ?? 20))
      stream.getVideoTracks()[0].addEventListener('ended', () => { this._stopStudio(); emit('ak:status', this._status()) })
    } else if (engine === 'sysmon') {
      throw new Error('System monitor lighting needs the desktop app')
    }
    this.studio = engine
  }
  _pageKey(e, down) {
    this.caps = e.getModifierState?.('CapsLock') ?? this.caps
    const hid = DOM_CODE_TO_HID[e.code]
    if (hid == null) return
    if (down && (this.heat || this.effect?.reactive)) { const k = KEY_BY_HID[hid]; if (k) { this.heat?.hit(k.led); this.effect?.hit?.(k.led) } }
    if (down) this.lastActivity = Date.now()
    if (this.tester) emit('ak:key', { hid, down, t: performance.now() / 1000 })
    if (this.recording && !(down && this.inPageKeys.has(hid))) {
      const now = performance.now(), rec = this.recording
      if (rec.length) rec[rec.length - 1].delay = Math.round(now - this.recLast)
      this.recLast = now
      rec.push({ code: hid, up: !down, delay: 10 })
      emit('ak:record', rec.slice(-P.MAX_MACRO_EVENTS))
      e.preventDefault()
    }
    down ? this.inPageKeys.add(hid) : this.inPageKeys.delete(hid)
    if (this.custom && this.base && !this.loop) this._frame(this.base).catch(() => {})
  }
  _saveProfile(p) { this.profiles[p.id] = norm(p); this._persist(); return norm(p) }
  _mutate(fn) { const p = this._active(); fn(p); return this._saveProfile(p) }
  async _wrap(fn) { try { return await fn() } catch (e) { return err(e) } }

  // ── API surface (same names as the desktop bridge) ─────────────────
  async get_state() {
    await this._autoConnect()
    const modes = [...Object.entries(P.HARDWARE_MODES).map(([id, [name, controls]]) => ({ id: +id, name, controls, software: false })),
                   ...Object.entries(SOFTWARE_EFFECTS).map(([id, m]) => ({ id: +id, ...m, software: true }))]
    let devices = []
    try { devices = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'audioinput').map(d => ({ id: d.deviceId, name: d.label || 'Microphone' })) } catch {}
    return ok({ status: this._status(), settings: this.settings, profiles: this._list(), profile: this._active(), macros: this.macros,
      modes, colors: Object.keys(P.COLORS), sleep_options: P.SLEEP_OPTIONS, response_options: P.RESPONSE_OPTIONS,
      max_macro_events: P.MAX_MACRO_EVENTS, hook_available: false, leds: this.leds, audio: { sensitivity: 5, smoothing_falloff: 0.82, bass_color: [254, 30, 30], mid_color: [30, 220, 30], treble_color: [30, 80, 254] },
      audio_devices: devices, platform: 'web', hid_supported: this.supported })
  }
  get_status() { return ok({ status: this._status() }) }
  async reconnect() { await this._autoConnect(); return this.device ? ok({ status: this._status() }) : this.connect_device() }
  set_lighting(L) { return this._wrap(async () => { await this._applyLighting(L); return ok({ profile: this._mutate(p => (p.lighting = L)), status: this._status() }) }) }
  set_custom_color(leds) { return this.set_lighting({ kind: 'custom', leds }) }
  async set_all_color(c) { const r = await this.set_custom_color(Array(108).fill(c)); return r.ok ? { ...r, leds: Array(108).fill(c) } : r }
  turn_off() { return this.set_all_color('#000000') }
  save_to_hardware() { return this._wrap(async () => { await this._send([P.savePacket()]); return ok() }) }
  stop_studio() { this._stopStudio(); return ok({ status: this._status() }) }
  preview_frame(leds) {
    return this._wrap(async () => {
      this._stopStudio(); await this._custom()
      const rgb = new Uint8Array(324); leds.forEach((h, i) => rgb.set(hexToRgb(h), i * 3))
      this.base = rgb
      await this._frame(rgb); return ok()
    })
  }
  restore_lighting() { return this._wrap(async () => { await this._applyLighting(this._active().lighting); return ok({ status: this._status() }) }) }
  set_shortcut_lens() { return err(DESKTOP_ONLY) }
  configure_audio(cfg) { this.audioCfg = { ...this.audioCfg, ...cfg }; return ok() }
  configure_heatmap(decay_rate, hot_color, cold_color) { this.heat?.configure({ decay_rate, hot_color, cold_color }); return ok() }
  configure_sysmon() { return ok() }
  get_sysmon_stats() { return ok({ stats: null }) }
  get_audio_devices() { return ok({ devices: [] }) }

  assign_key(layer, src, action) {
    return this._wrap(async () => {
      const macro = action.type === 'macro' ? this.macros.find(m => m.id === action.macro_id) : null
      await this._send(P.actionPackets(+layer, +src, action, macro))
      return ok({ profile: this._mutate(p => { action.type === 'default' ? delete p.keymap[layer][src] : (p.keymap[layer][src] = action) }) })
    })
  }
  async _replayKeys(p) {
    const warnings = []
    await this._send([P.resetKeysPacket()])
    for (const layer of ['1', '2']) for (const [src, a] of Object.entries(p.keymap[layer])) {
      try { await this._send(P.actionPackets(+layer, +src, a, this.macros.find(m => m.id === a.macro_id))) } catch (e) { warnings.push(`${src}: ${e.message}`) }
    }
    return warnings
  }
  reset_keys(layer = null) {
    return this._wrap(async () => {
      const p = this._mutate(p => { for (const l of layer ? [String(layer)] : ['1', '2']) p.keymap[l] = {} })
      return ok({ profile: p, warnings: await this._replayKeys(p) })
    })
  }
  factory_reset_keys() { return this._wrap(async () => { await this._send([P.resetKeysPacket()]); return ok() }) }

  save_macro(m) {
    if ((m.events?.length ?? 0) > P.MAX_MACRO_EVENTS) return err(`A macro can hold at most ${P.MAX_MACRO_EVENTS} events`)
    const macro = { id: m.id || Math.random().toString(16).slice(2, 10), name: (m.name || 'Macro').trim(), repeat: +m.repeat || 1, events: m.events.map(e => ({ code: +e.code, up: !!e.up, delay: Math.max(0, +e.delay || 10) })) }
    this.macros = [...this.macros.filter(x => x.id !== macro.id), macro]; this._persist()
    const p = this._active()
    for (const l of ['1', '2']) for (const [s, a] of Object.entries(p.keymap[l])) if (a.type === 'macro' && a.macro_id === macro.id) this._send(P.actionPackets(+l, +s, a, macro)).catch(() => {})
    return ok({ macro, macros: this.macros })
  }
  async delete_macro(id) {
    const p = this._active()
    for (const l of ['1', '2']) for (const [s, a] of Object.entries(p.keymap[l])) if (a.type === 'macro' && a.macro_id === id) await this.assign_key(+l, +s, { type: 'default' })
    this.macros = this.macros.filter(x => x.id !== id); this._persist()
    return ok({ macros: this.macros, profile: this._active() })
  }
  record_start() { this.recording = []; this.recLast = performance.now(); return ok({ page_only: true }) }
  record_stop() { const ev = this.recording ?? []; this.recording = null; return ok({ events: ev.slice(0, P.MAX_MACRO_EVENTS), truncated: ev.length > P.MAX_MACRO_EVENTS }) }

  activate_profile(id) {
    return this._wrap(async () => {
      if (!this.profiles[id]) return err('Profile not found')
      this.settings.active_profile = id; this._persist()
      const p = this._active(); let warnings = []
      if (this.device) {
        warnings = await this._replayKeys(p)
        await this._send([P.sleepPacket(p.device.sleep), P.responsePacket(p.device.response), P.fnModePacket(p.device.fn_swap)])
        await this._applyLighting(p.lighting)
      }
      emit('ak:profile', { profile: p, status: this._status() })
      return ok({ profile: p, warnings, status: this._status() })
    })
  }
  create_profile(name, base) {
    const src = norm(this.profiles[base] ?? DEFAULT_PROFILE)
    let id = slug(name), n = 2; while (this.profiles[id]) id = `${slug(name)}-${n++}`
    const p = this._saveProfile({ ...structuredClone(src), id, name: name.trim() || 'Profile', apps: [] })
    return ok({ profile: p, profiles: this._list() })
  }
  update_profile_meta(id, name, apps) {
    const p = this.profiles[id]; if (!p) return err('Profile not found')
    if (name != null) p.name = name.trim() || p.name
    if (apps != null) p.apps = apps
    this._persist(); return ok({ profiles: this._list() })
  }
  async delete_profile(id) {
    if (id === 'default') return err('The default profile can\'t be deleted')
    delete this.profiles[id]; this._persist()
    if (this.settings.active_profile === id) await this.activate_profile('default')
    return ok({ profiles: this._list() })
  }
  export_profile_file(id) {
    const p = this.profiles[id]; if (!p) return err('Profile not found')
    const used = new Set(['1', '2'].flatMap(l => Object.values(p.keymap[l]).filter(a => a.type === 'macro').map(a => a.macro_id)))
    const blob = new Blob([JSON.stringify({ format: 'ak820studio-profile', version: 1, profile: p, macros: this.macros.filter(m => used.has(m.id)) }, null, 2)], { type: 'application/json' })
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `${p.id}.ak820.json` }); a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 2000)
    return ok({ path: a.download })
  }
  import_profile_file() {
    return new Promise(resolve => {
      const input = Object.assign(document.createElement('input'), { type: 'file', accept: '.json' })
      input.onchange = async () => {
        try {
          const data = JSON.parse(await input.files[0].text())
          const prof = data.format === 'ak820studio-profile' ? data.profile : data
          if (!prof || typeof prof !== 'object' || !prof.keymap) throw new Error('no profile inside')
          prof.id = slug(prof.id || prof.name || 'imported'); prof.name = prof.name || 'Imported'
          for (const m of data.macros ?? []) this.save_macro(m)
          if (this.profiles[prof.id]) { prof.id += '-imported'; prof.name = `${prof.name} (imported)` }
          const p = this._saveProfile(prof)
          resolve(ok({ profile: p, profiles: this._list(), macros: this.macros }))
        } catch (e) { resolve(err(`Not a valid profile file: ${e.message}`)) }
      }
      input.click()
    })
  }
  running_apps() { return ok({ apps: [] }) }

  set_device(sleep, response, fn_swap) {
    return this._wrap(async () => {
      const pk = []
      if (sleep != null) pk.push(P.sleepPacket(sleep))
      if (response != null) pk.push(P.responsePacket(response))
      if (fn_swap != null) pk.push(P.fnModePacket(fn_swap))
      await this._send(pk)
      return ok({ profile: this._mutate(p => { if (sleep != null) p.device.sleep = +sleep; if (response != null) p.device.response = +response; if (fn_swap != null) p.device.fn_swap = !!fn_swap }) })
    })
  }
  set_game_mode() { return err(DESKTOP_ONLY) }
  set_layers(layers) { const p = this._mutate(p => (p.layers = layers)); if (this.custom && this.base && !this.loop) this._frame(this.base, true).catch(() => {}); return ok({ profile: p }) }
  key_tester(on) { this.tester = !!on; return ok({ page_only: true }) }
  update_settings(s) { Object.assign(this.settings, s); this._persist(); this._scheduleTick(); return ok({ settings: this.settings }) }
  get_typing_stats() { return ok({ stats: { enabled: false, wpm: 0, today: 0, week: [], heat: {}, top: [] } }) }
  set_typing_stats() { return err(DESKTOP_ONLY) }
  clear_typing_stats() { return this.get_typing_stats() }
}

let instance = null
export function webBackend() { return (instance ??= new WebBackend()) }
