// Desktop backend (Tauri): the web backend's logic, but HID goes through Rust and the
// system-wide features (game mode, per-app profiles, shortcut lens, typing stats,
// system audio, screen ambient, CPU/RAM lighting, tray, autostart) are switched on.
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { WebBackend } from './webBackend.js'
import * as P from './protocol.js'
import { KEYS, KEY_BY_HID } from '../layout.js'
import { createHeat, ambientFrame, spectrumFrame } from './effects.js'
import { lensKeys } from './lens.js'

const ok = (o = {}) => ({ ok: true, ...o })
const err = e => ({ ok: false, error: String(e?.message ?? e) })
const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }))

// Windows virtual-key -> USB HID usage
const VK = { 0x0D: 0x28, 0x1B: 0x29, 0x08: 0x2A, 0x09: 0x2B, 0x20: 0x2C, 0xBD: 0x2D, 0xBB: 0x2E, 0xDB: 0x2F, 0xDD: 0x30, 0xDC: 0x31,
  0xBA: 0x33, 0xDE: 0x34, 0xC0: 0x35, 0xBC: 0x36, 0xBE: 0x37, 0xBF: 0x38, 0x14: 0x39, 0x2C: 0x46, 0x91: 0x47, 0x13: 0x48, 0x2D: 0x49,
  0x24: 0x4A, 0x21: 0x4B, 0x2E: 0x4C, 0x23: 0x4D, 0x22: 0x4E, 0x27: 0x4F, 0x25: 0x50, 0x28: 0x51, 0x26: 0x52, 0x90: 0x53, 0x6F: 0x54,
  0x6A: 0x55, 0x6D: 0x56, 0x6B: 0x57, 0x60: 0x62, 0x6E: 0x63, 0x5D: 0x65, 0xA2: 0xE0, 0xA0: 0xE1, 0xA4: 0xE2, 0x5B: 0xE3, 0xA3: 0xE4,
  0xA1: 0xE5, 0xA5: 0xE6, 0x5C: 0xE7, 0x11: 0xE0, 0x10: 0xE1, 0x12: 0xE2 }
for (let i = 0; i < 26; i++) VK[0x41 + i] = 0x04 + i
for (let i = 0; i < 9; i++) { VK[0x31 + i] = 0x1E + i; VK[0x61 + i] = 0x59 + i }
VK[0x30] = 0x27
for (let i = 0; i < 12; i++) { VK[0x70 + i] = 0x3A + i; VK[0x7C + i] = 0x68 + i }
const vkToHid = (vk, ext) => (vk === 0x0D && ext ? 0x58 : VK[vk])
const MODS = { 0xE0: 'ctrl', 0xE4: 'ctrl', 0xE1: 'shift', 0xE5: 'shift', 0xE2: 'alt', 0xE6: 'alt', 0xE3: 'win', 0xE7: 'win' }
const CHAR_KEYS = new Set([...Array(0x24).keys()].map(i => i + 0x04).concat([0x2C, 0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38]))
const today = () => new Date().toISOString().slice(0, 10)

class DesktopBackend extends WebBackend {
  constructor() {
    super()
    this.firmware = null
    this.foreground = ''
    this.seenApps = new Set(JSON.parse(localStorage.getItem('ak820studio:seenApps') ?? '[]'))
    this.manualProfile = this.settings.active_profile
    this.autoProfile = null
    this.held = new Set()
    this.typing = JSON.parse(localStorage.getItem('ak820studio:stats') ?? '{"days":{}}')
    this.recent = []
    this.sysStats = null
    listen('hid-input', e => { const b = P.parseHeartbeat(new Uint8Array(e.payload)); if (b != null && b !== this.battery) { this.battery = b; emit('ak:status', this._status()) } })
    listen('hid-disconnect', () => { this.device = null; this.error = 'Keyboard disconnected'; emit('ak:status', this._status()) })
    listen('key', e => this._globalKey(e.payload))
    listen('foreground', e => this._onForeground(e.payload))
    listen('audio-bins', e => this._onBins(e.payload))
    listen('tray', e => e.payload === 'lights-off' && this.turn_off())
    setInterval(() => { if (!this.device) this._autoConnect() }, 2000)
    setInterval(() => this._flushStats(), 30000)
    const gm = this._active().game_mode
    invoke('set_game_mode', { win: gm.win, altTab: gm.alt_tab, altF4: gm.alt_f4 })
    invoke('set_close_to_tray', { on: this.settings.close_to_tray !== false })
    this._syncKeyEvents()
    this._syncCaps()
  }

  get supported() { return true }
  get idleSupported() { return true }
  async _syncCaps() {
    try {
      const on = await invoke('caps_lock_on')
      if (on !== this.caps) { this.caps = on; if (this.custom && this.base && !this.loop) this._frame(this.base).catch(() => {}) }
    } catch {}
  }
  _status() { return { ...super._status(), firmware: this.firmware, platform: 'desktop', auto_profile: this.autoProfile, foreground: this.foreground } }

  // ── transport over Rust ────────────────────────────────────────────
  _send(packets) {
    if (!this.device) return Promise.reject(new Error('Connect the keyboard first'))
    const task = () => invoke('hid_write', { packets: packets.map(p => Array.from(p)) })
    const run = this.queue.then(task, task).catch(e => { throw new Error(String(e)) })
    this.queue = run.catch(() => {})
    return run
  }
  async _autoConnect() {
    if (this.device || this.connecting) return
    this.connecting = true
    await this._importLegacy()
    try {
      const info = await invoke('hid_open')
      this.device = { productId: info.pid }
      this.firmware = `${(info.release >> 8).toString(16)}.${(info.release & 0xFF).toString(16).padStart(2, '0')}`
      this.error = ''; this.custom = false; this.lastFrame = null
      clearInterval(this.hb)
      this.hb = setInterval(() => this.device && this._send([P.heartbeatPacket()]).catch(() => {}), 2500)
      this._send([P.heartbeatPacket()]).catch(() => {})
      const p = this._active()
      await this._send([P.sleepPacket(p.device.sleep), P.responsePacket(p.device.response), P.fnModePacket(p.device.fn_swap)]).catch(() => {})
      await this._applyLighting(p.lighting).catch(() => {})
      emit('ak:status', this._status())
    } catch (e) {
      if (this.error !== String(e)) { this.error = String(e); emit('ak:status', this._status()) }
    } finally { this.connecting = false }
  }
  async connect_device() { await this._autoConnect(); return this.device ? ok({ status: this._status() }) : err(this.error) }

  // ── live engines that need the OS ──────────────────────────────────
  _stopStudio() { super._stopStudio(); invoke('audio_stop'); this.bins = null }
  async _startStudio(engine, cfg) {
    if (engine === 'audio') {
      await this._custom()
      await invoke('audio_start', { source: cfg.device_id === 'system' || cfg.device_id == null ? 'system' : 'mic' })
      this.audioCfg = { ...cfg }; this.sm = [0, 0, 0]
      this.loop = setInterval(() => { if (this.bins) this._frame(spectrumFrame(this.bins, this.sm, this.audioCfg)).catch(() => {}) }, 33)
      this.studio = 'audio'; return
    }
    if (engine === 'ambient') {
      await this._custom()
      const prev = new Float32Array(324)
      this.loop = setInterval(async () => {
        try { const px = new Uint8Array(await invoke('grab_screen', { cols: 24, rows: 6 })); this._frame(ambientFrame({ width: 24, height: 6, data: px }, prev, cfg)).catch(() => {}) } catch {}
      }, 1000 / (cfg.fps ?? 20))
      this.studio = 'ambient'; return
    }
    if (engine === 'sysmon') {
      await this._custom()
      this.sysCfg = { mode: 'cycle', interval: 1, color_low: [40, 220, 120], color_mid: [250, 200, 40], color_high: [240, 50, 70], ...cfg }
      let tick = 0
      const order = [...KEYS].sort((a, b) => a.row - b.row || a.x - b.x)
      const lerp = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t)
      const colorFor = u => (u <= 50 ? lerp(this.sysCfg.color_low, this.sysCfg.color_mid, u / 50) : lerp(this.sysCfg.color_mid, this.sysCfg.color_high, (u - 50) / 50))
      const run = async () => {
        const s = await invoke('sysmon')
        const out = new Uint8Array(324), m = this.sysCfg.mode
        const fill = (keys, u) => keys.slice(0, Math.round(u / 100 * keys.length)).forEach(k => out.set(colorFor(u), k.led * 3))
        let focus
        if (m === 'split') { const h = Math.floor(order.length / 2); fill(order.slice(0, h), s.cpu); fill(order.slice(h), s.mem); focus = 'CPU / RAM' }
        else if (m === 'highest') { const [n, u] = [['CPU', s.cpu], ['RAM', s.mem]].sort((a, b) => b[1] - a[1])[0]; fill(order, u); focus = n }
        else { const i = Math.floor(tick++ / 3) % 2; const [n, u] = [['CPU', s.cpu], ['RAM', s.mem]][i]; fill(order, u); focus = n }
        this.sysStats = { ...s, current_focus: focus }
        this._frame(out).catch(() => {})
      }
      run(); this.loop = setInterval(run, (this.sysCfg.interval ?? 1) * 1000)
      this.studio = 'sysmon'; return
    }
    return super._startStudio(engine, cfg)
  }
  _onBins(b) { this.bins = b }
  configure_sysmon(mode, interval, color_low, color_mid, color_high) { this.sysCfg = { ...this.sysCfg, mode, interval, color_low, color_mid, color_high }; return ok() }
  get_sysmon_stats() { return ok({ stats: this.sysStats }) }

  // ── global keys: heatmap, tester, recorder, stats, lens ────────────
  _needKeys() { return !!(this.heat || this.effect?.reactive || this.tester || this.recording || this.settings.typing_stats || this.settings.shortcut_lens !== false) }
  _syncKeyEvents() { invoke('set_key_events', { on: this._needKeys() }) }
  _pageKey() {}  // the global hook already covers this window
  _globalKey({ vk, ext, down, injected }) {
    const hid = vkToHid(vk, ext)
    if (hid == null) return
    if (hid === 0x39 && !down) this._syncCaps()
    if (down && (this.heat || this.effect?.reactive)) { const k = KEY_BY_HID[hid]; if (k) { this.heat?.hit(k.led); this.effect?.hit?.(k.led) } }
    if (this.tester) emit('ak:key', { hid, down, t: performance.now() / 1000 })
    if (this.recording && !injected) {
      const rec = this.recording, last = rec[rec.length - 1]
      if (!(last && last.code === hid && last.up === !down)) {
        const now = performance.now()
        if (last) last.delay = Math.round(now - this.recLast)
        this.recLast = now; rec.push({ code: hid, up: !down, delay: 10 })
        emit('ak:record', rec.slice(-P.MAX_MACRO_EVENTS))
      }
    }
    if (down && !injected && this.settings.typing_stats) this._count(hid)
    if (!injected) this._lens(hid, down)
  }
  _lens(hid, down) {
    if (this.settings.shortcut_lens === false) return
    const mod = MODS[hid]
    if (!mod) { if (down && this.held.size) this.lensBlocked = true; return }
    if (down && !this.held.has(mod)) {
      this.held.add(mod); this.lensBlocked = false
      clearTimeout(this.lensTimer)
      this.lensTimer = setTimeout(() => this._lensShow(), 350)
    } else if (!down) {
      this.held.delete(mod)
      if (!this.held.size) { clearTimeout(this.lensTimer); this._lensHide() }
    }
  }
  async _lensShow() {
    const gm = this._active().game_mode
    if (!this.held.size || this.lensBlocked || !this.device || (this.held.size === 1 && this.held.has('shift')) || gm.win || gm.alt_tab || gm.alt_f4) return
    const keys = lensKeys(this.foreground, this.held)
    if (!keys.size) return
    for (const [m, h] of [['ctrl', 0xE0], ['ctrl', 0xE4], ['shift', 0xE1], ['shift', 0xE5], ['alt', 0xE2], ['alt', 0xE6], ['win', 0xE3]]) if (this.held.has(m)) keys.set(h, [254, 254, 254])
    this.lensKeys = new Map([...keys].filter(([h]) => KEY_BY_HID[h]).map(([h, c]) => [KEY_BY_HID[h].led, c]))
    this.lensTookOver = !this.custom
    await this._custom()
    await this._frame(this.base ?? new Uint8Array(324), true).catch(() => {})
  }
  async _lensHide() {
    if (!this.lensKeys) return
    this.lensKeys = null
    if (this.lensTookOver) { this.lensTookOver = false; await this._applyLighting(this._active().lighting).catch(() => {}) }
    else if (this.base && !this.loop) await this._frame(this.base, true).catch(() => {})
  }
  set_shortcut_lens(on) { this.settings.shortcut_lens = !!on; this._persist(); this._syncKeyEvents(); return ok({ settings: this.settings }) }
  key_tester(on) { this.tester = !!on; this._syncKeyEvents(); return ok() }
  record_start() { const r = super.record_start(); this._syncKeyEvents(); return { ...r, page_only: false } }
  record_stop() { const r = super.record_stop(); this._syncKeyEvents(); return r }
  async _applyLighting(L) { const r = await super._applyLighting(L); this._syncKeyEvents(); return r }

  // ── typing stats (counts only) ─────────────────────────────────────
  _count(hid) {
    const d = (this.typing.days[today()] ??= { total: 0, keys: {} })
    d.total++; d.keys[hid] = (d.keys[hid] ?? 0) + 1; this.statsDirty = true
    if (CHAR_KEYS.has(hid)) this.recent.push(performance.now())
  }
  _flushStats() {
    if (!this.statsDirty) return
    const days = Object.keys(this.typing.days).sort()
    for (const k of days.slice(0, -90)) delete this.typing.days[k]
    localStorage.setItem('ak820studio:stats', JSON.stringify(this.typing)); this.statsDirty = false
  }
  get_typing_stats() {
    const now = performance.now(); this.recent = this.recent.filter(t => now - t < 60000)
    const days = this.typing.days, totals = {}
    for (const d of Object.values(days)) for (const [h, n] of Object.entries(d.keys)) totals[h] = (totals[h] ?? 0) + n
    const top = Object.entries(totals).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([h, n]) => [+h, n])
    return ok({ stats: { enabled: !!this.settings.typing_stats, wpm: Math.round(this.recent.length / 5), today: days[today()]?.total ?? 0,
      week: Object.keys(days).sort().slice(-7).map(day => ({ day, total: days[day].total })), heat: totals, top } })
  }
  set_typing_stats(on) { this.settings.typing_stats = !!on; this._persist(); this._syncKeyEvents(); return ok({ settings: this.settings, stats: this.get_typing_stats().stats }) }
  clear_typing_stats() { this.typing = { days: {} }; this.statsDirty = true; this._flushStats(); return this.get_typing_stats() }

  // ── apps, game mode, settings, files ───────────────────────────────
  _onForeground(exe) {
    this.foreground = exe
    if (!this.seenApps.has(exe)) { this.seenApps.add(exe); localStorage.setItem('ak820studio:seenApps', JSON.stringify([...this.seenApps].slice(-200))) }
    if (this.settings.auto_switch === false) return emit('ak:status', this._status())
    const target = this._list().find(p => p.apps.includes(exe))
    const want = target ? target.id : this.manualProfile
    this.autoProfile = target ? target.id : null
    if (want !== this.settings.active_profile) this._activate(want)
    else emit('ak:status', this._status())
  }
  async _activate(id) {
    const r = await super.activate_profile(id)
    const gm = this._active().game_mode
    invoke('set_game_mode', { win: gm.win, altTab: gm.alt_tab, altF4: gm.alt_f4 })
    return r
  }
  activate_profile(id) { this.manualProfile = id; this.autoProfile = null; return this._activate(id) }
  running_apps() { return ok({ apps: [...this.seenApps].sort() }) }
  async set_game_mode(win, alt_tab, alt_f4) {
    await invoke('set_game_mode', { win, altTab: alt_tab, altF4: alt_f4 })
    const p = this._mutate(p => (p.game_mode = { win: !!win, alt_tab: !!alt_tab, alt_f4: !!alt_f4 }))
    if (this.custom && this.base && !this.loop) this._frame(this.base, true).catch(() => {})
    return ok({ profile: p })
  }
  async _idleSeconds() { try { return await invoke('idle_seconds') } catch { return 0 } }
  async update_settings(s) {
    Object.assign(this.settings, s); this._persist(); this._scheduleTick()
    if ('close_to_tray' in s) invoke('set_close_to_tray', { on: !!s.close_to_tray })
    if ('launch_at_login' in s) { try { await invoke('set_autostart', { on: !!s.launch_at_login }) } catch (e) { return err(e) } }
    return ok({ settings: this.settings })
  }
  async export_profile_file(id) {
    const p = this.profiles[id]; if (!p) return err('Profile not found')
    const used = new Set(['1', '2'].flatMap(l => Object.values(p.keymap[l]).filter(a => a.type === 'macro').map(a => a.macro_id)))
    const content = JSON.stringify({ format: 'ak820studio-profile', version: 1, profile: p, macros: this.macros.filter(m => used.has(m.id)) }, null, 2)
    try { const path = await invoke('export_file', { name: `${p.id}.ak820.json`, content }); return ok(path ? { path } : { cancelled: true }) } catch (e) { return err(e) }
  }
  async import_profile_file() {
    try {
      const text = await invoke('import_file'); if (!text) return ok({ cancelled: true })
      const data = JSON.parse(text), prof = data.format === 'ak820studio-profile' ? data.profile : data
      if (!prof || typeof prof !== 'object' || !prof.keymap) throw new Error('no profile inside')
      prof.id = (prof.id || prof.name || 'imported').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'imported'
      prof.name = prof.name || 'Imported'
      for (const m of data.macros ?? []) this.save_macro(m)
      if (this.profiles[prof.id]) { prof.id += '-imported'; prof.name = `${prof.name} (imported)` }
      return ok({ profile: this._saveProfile(prof), profiles: this._list(), macros: this.macros })
    } catch (e) { return err(`Not a valid profile file: ${e.message ?? e}`) }
  }
  async _importLegacy() {
    if (localStorage.getItem('ak820studio:imported')) return
    localStorage.setItem('ak820studio:imported', '1')
    if (localStorage.getItem('ak820studio:profiles')) return
    try {
      const d = await invoke('legacy_data')
      if (!d?.profiles?.length) return
      this.profiles = Object.fromEntries(d.profiles.filter(p => p?.id).map(p => [p.id, p]))
      if (Array.isArray(d.macros)) this.macros = d.macros
      if (d.settings) Object.assign(this.settings, d.settings)
      this.manualProfile = this.settings.active_profile
      this._persist()
    } catch {}
  }
  async get_state() {
    await this._importLegacy()
    const s = await super.get_state()
    return { ...s, status: this._status(), hook_available: true, platform: 'desktop', hid_supported: true,
      audio_devices: [{ id: 'mic', name: 'Default microphone' }] }
  }
}

let instance = null
export function desktopBackend() { return (instance ??= new DesktopBackend()) }
