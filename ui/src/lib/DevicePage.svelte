<script>
  import { onDestroy } from 'svelte'
  import { Gamepad2, Timer, Zap, Activity, Power, BarChart3, Cpu, ScanEye, Moon } from 'lucide-svelte'
  import KeyboardStage from './KeyboardStage.svelte'
  import { profile, settings, meta, pressed, status, platform, run, api, toast } from './store.js'
  import { KEY_BY_HID, KEYS } from './layout.js'
  import { HID_NAMES } from './keycodes.js'

  $: d = $profile?.device ?? { sleep: 3, response: 1, fn_swap: false }
  $: gm = $profile?.game_mode ?? { win: false, alt_tab: false, alt_f4: false }

  const set = patch => run('set_device', [patch.sleep ?? null, patch.response ?? null, patch.fn_swap ?? null])
  const setGame = patch => run('set_game_mode', [ { ...gm, ...patch }.win, { ...gm, ...patch }.alt_tab, { ...gm, ...patch }.alt_f4 ])
  const setApp = patch => run('update_settings', [patch]).then(r => settings.set(r.settings))

  // ── key tester ───────────────────────────────────────────────────────
  let testing = false
  let tested = new Set()
  let log = []           // recent events
  let chatter = {}       // hid -> count of suspicious repeats
  const lastUp = {}
  function onKey(e) {
    const { hid, down, t } = e.detail
    if (!testing || hid == null) return
    if (down) {
      if (lastUp[hid] && (t - lastUp[hid]) * 1000 < 30) chatter[hid] = (chatter[hid] ?? 0) + 1
      tested.add(hid); tested = tested
      log = [{ hid, t }, ...log].slice(0, 14)
    } else lastUp[hid] = t
  }
  window.addEventListener('ak:key', onKey)
  async function toggleTest() {
    try {
      await api('key_tester', !testing)
      testing = !testing
      if (testing) { tested = new Set(); log = []; chatter = {} }
      pressed.set(new Set())
    } catch (e) { toast(e.message, 'bad') }
  }
  onDestroy(() => { window.removeEventListener('ak:key', onKey); if (testing) api('key_tester', false) })
  $: testedOnBoard = [...tested].filter(h => KEY_BY_HID[h]).length
  $: chatterKeys = Object.entries(chatter).filter(([, n]) => n > 0)

  // ── typing stats ─────────────────────────────────────────────────────
  let ts = null
  async function loadStats() { try { ts = (await api('get_typing_stats')).stats } catch {} }
  loadStats()
  const statsPoll = setInterval(() => { if (ts?.enabled) loadStats() }, 3000)
  onDestroy(() => clearInterval(statsPoll))
  async function toggleStats() {
    const r = await run('set_typing_stats', [!ts?.enabled])
    settings.set(r.settings); ts = r.stats
  }
  $: heatColors = (() => {
    if (!ts?.heat) return null
    const vals = Object.values(ts.heat), max = Math.max(1, ...vals)
    const out = Array(108).fill('#000000')
    for (const k of KEYS) {
      const t = Math.sqrt((ts.heat[k.hid] ?? 0) / max)
      const r = Math.round(40 + 214 * t), g = Math.round(30 + 60 * t * (1 - t) * 4 * 0.5), b = Math.round(110 * (1 - t))
      out[k.led] = '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')
    }
    return out
  })()
  $: weekMax = Math.max(1, ...(ts?.week ?? []).map(w => w.total))

  $: sched = $settings.schedule ?? {}
  function setSched(part, patch) {
    const next = { ...sched, [part]: { ...(sched[part] ?? {}), ...patch } }
    setApp({ schedule: next })
  }

  async function resetKeyboardKeys() {
    if (!confirm('Restore every key on the keyboard to its factory function? Your saved profiles are kept and you can re-apply one any time.')) return
    await run('factory_reset_keys', [], { success: 'Keys restored to factory functions' })
  }
</script>

<section class="px-7 pt-6 pb-12 max-w-[1100px] flex flex-col gap-10">
  <div class="grid grid-cols-2 gap-10">
    <div>
      <h2 class="text-[14px] font-semibold flex items-center gap-2 mb-1"><Zap size={16} class="text-lav" /> Response time</h2>
      <p class="text-[12.5px] text-ink-mute mb-3">How quickly key presses are reported. Faster is better for games; slower filters accidental double presses.</p>
      <div class="flex flex-col gap-1.5">
        {#each Object.entries($meta.response_options ?? {}) as [v, label]}
          <label class="flex items-center gap-3 h-10 px-3 rounded-lg border cursor-pointer
                        {+d.response === +v ? 'border-lav bg-lav-wash' : 'border-rule bg-card hover:border-ink-faint'}">
            <input type="radio" class="accent-lav" name="resp" checked={+d.response === +v} on:change={() => set({ response: +v })} />
            <span class="text-[13px]">{label}</span>
          </label>
        {/each}
      </div>
    </div>

    <div>
      <h2 class="text-[14px] font-semibold flex items-center gap-2 mb-1"><Timer size={16} class="text-lav" /> Sleep</h2>
      <p class="text-[12.5px] text-ink-mute mb-3">Lights turn off after this long without typing. Shorter saves battery on wireless.</p>
      <div class="seg">
        {#each Object.entries($meta.sleep_options ?? {}) as [v, label]}
          <button aria-pressed={+d.sleep === +v} on:click={() => set({ sleep: +v })}>{label}</button>
        {/each}
      </div>

      <h2 class="text-[14px] font-semibold mt-7 mb-1">Top row</h2>
      <p class="text-[12.5px] text-ink-mute mb-3">Swap what the top row does with and without Fn.</p>
      <div class="seg">
        <button aria-pressed={!d.fn_swap} on:click={() => set({ fn_swap: false })}>Standard</button>
        <button aria-pressed={d.fn_swap} on:click={() => set({ fn_swap: true })}>Swapped</button>
      </div>
    </div>
  </div>

  {#if !$meta.web}
  <div>
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-[14px] font-semibold flex items-center gap-2 mb-1"><ScanEye size={16} class="text-lav" /> Shortcut lens</h2>
        <p class="text-[12.5px] text-ink-mute max-w-[640px]">Hold Ctrl, Alt or Win for a moment and the keys that do something in the app you're using light up. Works in VS Code, browsers, Explorer, Photoshop, Discord and everywhere else for the common shortcuts. It stays off while game mode is on.</p>
      </div>
      <button class="{$settings.shortcut_lens !== false ? 'btn-line' : 'btn-primary'}"
              on:click={() => run('set_shortcut_lens', [$settings.shortcut_lens === false]).then(r => settings.set(r.settings))}>
        {$settings.shortcut_lens !== false ? 'Turn off' : 'Turn on'}</button>
    </div>
  </div>

  <div>
    <h2 class="text-[14px] font-semibold flex items-center gap-2 mb-1"><Gamepad2 size={16} class="text-lav" /> Game mode</h2>
    <p class="text-[12.5px] text-ink-mute mb-3">Block keys that throw you out of a game. Saved with the profile, so link a game to it on the Profiles page to turn this on automatically.</p>
    <div class="flex gap-3">
      {#each [['win', 'Windows key'], ['alt_tab', 'Alt + Tab'], ['alt_f4', 'Alt + F4']] as [k, n]}
        <button class="h-10 px-4 rounded-lg border text-[13px] flex items-center gap-2.5
                       {gm[k] ? 'border-lav bg-lav-wash text-lav-deep font-semibold' : 'border-rule bg-card hover:border-ink-faint'}"
                aria-pressed={gm[k]} on:click={() => setGame({ [k]: !gm[k] })}>
          <span class="w-8 h-[18px] rounded-full relative transition-colors {gm[k] ? 'bg-lav' : 'bg-ink/15'}">
            <span class="absolute top-[2px] w-[14px] h-[14px] rounded-full bg-card shadow transition-all {gm[k] ? 'left-[16px]' : 'left-[2px]'}"></span>
          </span>
          Block {n}
        </button>
      {/each}
    </div>
  </div>
  {/if}

  <div>
    <div class="flex items-center justify-between mb-3">
      <div>
        <h2 class="text-[14px] font-semibold flex items-center gap-2 mb-1"><Activity size={16} class="text-lav" /> Key test</h2>
        <p class="text-[12.5px] text-ink-mute">Press every key to check it registers. Keys that fire twice within 30 ms are flagged as chattering.</p>
      </div>
      <button class="{testing ? 'btn-line' : 'btn-primary'}" on:click={toggleTest}>{testing ? 'Stop test' : 'Start key test'}</button>
    </div>
    {#if testing}
      <KeyboardStage compact selected={tested} pressed={$pressed} />
      <div class="flex gap-10 mt-4 text-[13px]">
        <span><span class="font-cap text-[20px]">{testedOnBoard}</span> <span class="text-ink-mute">/ 82 keys tested</span></span>
        {#if chatterKeys.length}
          <span class="text-bad">Chatter on {chatterKeys.map(([h, n]) => `${HID_NAMES[h] ?? h} (${n}×)`).join(', ')}</span>
        {:else}
          <span class="text-ink-mute">No chatter detected</span>
        {/if}
        <span class="ml-auto font-cap text-ink-mute">{log.map(l => HID_NAMES[l.hid] ?? '?').join('  ')}</span>
      </div>
    {/if}
  </div>

  {#if !$meta.web}
  <div>
    <div class="flex items-center justify-between mb-3">
      <div>
        <h2 class="text-[14px] font-semibold flex items-center gap-2 mb-1"><BarChart3 size={16} class="text-lav" /> Typing stats</h2>
        <p class="text-[12.5px] text-ink-mute max-w-[620px]">Counts how often you press each key and your typing speed. Only counts are kept, never what you type, and they stay on this PC.</p>
      </div>
      <button class="{ts?.enabled ? 'btn-line' : 'btn-primary'}" on:click={toggleStats}>{ts?.enabled ? 'Turn off' : 'Turn on'}</button>
    </div>
    {#if ts && (ts.enabled || ts.today || ts.top.length)}
      <div class="grid grid-cols-[1fr_300px] gap-8 items-start">
        <KeyboardStage compact colors={heatColors} />
        <div class="flex flex-col gap-5">
          <div class="flex gap-8">
            <div><div class="font-cap text-[30px] leading-none">{ts.wpm}</div><div class="label mt-1">words a minute now</div></div>
            <div><div class="font-cap text-[30px] leading-none">{ts.today.toLocaleString()}</div><div class="label mt-1">keys today</div></div>
          </div>
          {#if ts.week.length}
            <div>
              <div class="label mb-2">Last 7 days</div>
              <div class="flex items-end gap-1.5 h-16">
                {#each ts.week as w}
                  <div class="flex-1 rounded-t bg-lav/70" style="height:{Math.max(4, (w.total / weekMax) * 100)}%" title="{w.day}: {w.total} keys"></div>
                {/each}
              </div>
            </div>
          {/if}
          {#if ts.top.length}
            <div>
              <div class="label mb-2">Most pressed</div>
              <div class="flex flex-wrap gap-1.5">
                {#each ts.top as [h, n]}<span class="chip bg-ink/[0.06]"><span class="font-cap">{HID_NAMES[h] ?? h}</span><span class="text-ink-mute">{n.toLocaleString()}</span></span>{/each}
              </div>
            </div>
          {/if}
          <button class="btn-quiet self-start -ml-3 text-[12px]" on:click={() => run('clear_typing_stats').then(r => (ts = r.stats))}>Clear stats</button>
        </div>
      </div>
    {/if}
  </div>
  {/if}

  {#if $platform !== 'desktop' || $meta.jsBackend}
  <div>
    <h2 class="text-[14px] font-semibold flex items-center gap-2 mb-1"><Moon size={16} class="text-lav" /> Lighting schedule</h2>
    <p class="text-[12.5px] text-ink-mute mb-4">Dim the lights at night and turn them off when you step away. They come back as soon as you touch the keyboard or mouse.</p>
    <div class="flex flex-col gap-3 max-w-[760px]">
      <div class="flex flex-wrap items-center gap-4 rounded-xl border border-rule bg-card px-4 py-3">
        <label class="flex items-center gap-2.5 text-[13.5px] font-semibold min-w-[150px]">
          <input type="checkbox" class="accent-lav w-4 h-4" checked={sched.night?.on} on:change={e => setSched('night', { on: e.currentTarget.checked })} /> Night dimming</label>
        <label class="flex items-center gap-2 text-[12.5px] text-ink-mute">from
          <input type="time" class="field h-8" value={sched.night?.from ?? '22:00'} on:change={e => setSched('night', { from: e.currentTarget.value })} /></label>
        <label class="flex items-center gap-2 text-[12.5px] text-ink-mute">to
          <input type="time" class="field h-8" value={sched.night?.to ?? '07:00'} on:change={e => setSched('night', { to: e.currentTarget.value })} /></label>
        <label class="flex items-center gap-2 text-[12.5px] text-ink-mute flex-1 min-w-[180px]">brightness
          <input type="range" min="0.05" max="0.8" step="0.05" value={sched.night?.level ?? 0.3} style="--pct:{((sched.night?.level ?? 0.3) - 0.05) / 0.75 * 100}%"
                 on:change={e => setSched('night', { level: +e.currentTarget.value })} />
          <span class="w-9 text-right text-ink">{Math.round((sched.night?.level ?? 0.3) * 100)}%</span></label>
      </div>
      <div class="flex flex-wrap items-center gap-4 rounded-xl border border-rule bg-card px-4 py-3">
        <label class="flex items-center gap-2.5 text-[13.5px] font-semibold min-w-[150px]">
          <input type="checkbox" class="accent-lav w-4 h-4" checked={sched.idle?.on} disabled={$status.idle_supported === false} on:change={e => setSched('idle', { on: e.currentTarget.checked })} /> Lights off when away</label>
        {#if $status.idle_supported === false}<span class="text-[12px] text-ink-mute">Needs the desktop app: a browser tab can't tell when you're using other apps.</span>{/if}
        <label class="flex items-center gap-2 text-[12.5px] text-ink-mute">after
          <input type="number" min="1" max="240" class="field w-16" value={sched.idle?.minutes ?? 10} on:change={e => setSched('idle', { minutes: +e.currentTarget.value })} /> minutes without input</label>
        {#if $status.asleep}<span class="chip bg-ink/[0.06] text-ink-mute">Lights are off now</span>{/if}
        {#if $status.dimmed}<span class="chip bg-lav-wash text-lav-deep">Night dimming is on</span>{/if}
      </div>
    </div>
  </div>
  {/if}

  <div class="grid grid-cols-2 gap-10">
    <div>
      <h2 class="text-[14px] font-semibold flex items-center gap-2 mb-3"><Power size={16} class="text-lav" /> App</h2>
      <div class="flex flex-col gap-2.5 text-[13px] {$meta.web ? 'hidden' : ''}">
        <label class="flex items-center gap-2.5"><input type="checkbox" class="accent-lav w-4 h-4" checked={$settings.launch_at_login} on:change={e => setApp({ launch_at_login: e.currentTarget.checked })} /> Start with Windows</label>
        <label class="flex items-center gap-2.5"><input type="checkbox" class="accent-lav w-4 h-4" checked={$settings.start_minimized} on:change={e => setApp({ start_minimized: e.currentTarget.checked })} /> Start hidden in the tray</label>
        <label class="flex items-center gap-2.5"><input type="checkbox" class="accent-lav w-4 h-4" checked={$settings.close_to_tray} on:change={e => setApp({ close_to_tray: e.currentTarget.checked })} /> Keep running in the tray when the window closes</label>
        <label class="flex items-center gap-2.5"><input type="checkbox" class="accent-lav w-4 h-4" checked={$settings.memory_saver} on:change={e => setApp({ memory_saver: e.currentTarget.checked })} /> Free memory while hidden in the tray</label>
      </div>
      <div class="flex items-center gap-3 mt-4">
        <span class="label">Theme</span>
        <div class="seg">
          {#each [['system', 'Match Windows'], ['light', 'Light'], ['dark', 'Dark']] as [v, n]}
            <button aria-pressed={($settings.theme ?? 'system') === v} on:click={() => setApp({ theme: v })}>{n}</button>
          {/each}
        </div>
      </div>
      <p class="text-[12px] text-ink-mute mt-3">Close the official AJAZZ app and turn off its Auto Run so the two don't fight over the keyboard.</p>
    </div>
    <div>
      <h2 class="text-[14px] font-semibold flex items-center gap-2 mb-1"><Cpu size={16} class="text-lav" /> Firmware</h2>
      <p class="text-[12.5px] text-ink-mute mb-1">{$status.firmware ? `Your keyboard runs firmware ${$status.firmware}.` : 'Connect the keyboard to see its firmware.'}</p>
      <p class="text-[12.5px] text-ink-mute mb-6">AK820 Studio never writes firmware. Only update with AJAZZ's own tool when they publish a version for the AK820 Max Plus: a wrong or interrupted update can stop the keyboard working.</p>
      <h2 class="text-[14px] font-semibold mb-1">Restore keys</h2>
      <p class="text-[12.5px] text-ink-mute mb-3">Puts every key back to its factory function on the keyboard. Lighting and your saved profiles aren't touched.</p>
      <button class="btn-danger border border-bad/30" on:click={resetKeyboardKeys}>Restore factory key functions</button>
    </div>
  </div>
</section>
