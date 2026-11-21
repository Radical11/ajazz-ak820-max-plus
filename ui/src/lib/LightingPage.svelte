<script>
  import { onDestroy } from 'svelte'
  import { Paintbrush, PaintBucket, Eraser, Save, Play, Square, ArrowLeftRight } from 'lucide-svelte'
  import KeyboardStage from './KeyboardStage.svelte'
  import { profile, modes, leds, status, audioDevices, audioConfig, run, api, toast, NUM_LEDS } from './store.js'
  import { HID_NAMES } from './keycodes.js'
  import { KEYS } from './layout.js'

  const SWATCH = { red: '#F0404E', green: '#3BCB6B', blue: '#3D6BF0', yellow: '#F2C230', pink: '#EE5BC4',
                   cyan: '#33CFE0', white: '#FFFFFF', rgb: 'conic-gradient(#f44,#fd4,#4d6,#4cf,#64f,#f4c,#f44)' }
  const hexToRgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16))
  const rgbToHex = a => '#' + a.map(v => Math.max(0, Math.min(255, v | 0)).toString(16).padStart(2, '0')).join('')

  let L = $profile?.lighting ?? { kind: 'hardware', mode: 7 }
  let tab = L.kind === 'custom' ? 'paint' : L.kind === 'studio' && L.engine !== 'effect' ? 'live' : 'effects'

  // ── layers ──────────────────────────────────────────────────────────
  const LAYER_DEFAULTS = { caps: { on: true, color: '#ffffff' }, highlight: { on: false, color: '#f0404e', keys: [0x1A, 0x04, 0x16, 0x07] }, game: { on: true, color: '#f0404e' } }
  let layers = JSON.parse(JSON.stringify({ ...LAYER_DEFAULTS, ...($profile?.layers ?? {}) }))
  for (const k in LAYER_DEFAULTS) layers[k] = { ...LAYER_DEFAULTS[k], ...layers[k] }
  let pickHighlight = false
  let layerTimer
  function saveLayers() { layers = layers; clearTimeout(layerTimer); layerTimer = setTimeout(() => run('set_layers', [layers]).catch(() => {}), 120) }
  function toggleHighlightKey(e) {
    const h = e.detail.key.hid, ks = layers.highlight.keys
    layers.highlight.keys = ks.includes(h) ? ks.filter(x => x !== h) : [...ks, h]
    saveLayers()
  }

  // ── effects ─────────────────────────────────────────────────────────
  let fx = L.kind === 'hardware' ? { ...L }
         : L.kind === 'studio' && L.engine === 'effect' ? { kind: 'hardware', ...L.config }
         : { kind: 'hardware', mode: 7, brightness: 4, speed: 2, direction: 0, color: 'rgb', color2: 'rgb' }
  $: current = $modes.find(m => m.id === +fx.mode)
  $: ctl = current?.controls ?? ''
  let fxTimer
  function applyFx(patch = {}) {
    fx = { ...fx, ...patch, kind: 'hardware' }
    clearTimeout(fxTimer)
    fxTimer = setTimeout(() => run('set_lighting', [{ ...fx }]).catch(() => {}), 60)
  }

  // ── paint ───────────────────────────────────────────────────────────
  let brush = '#6D5BD0'
  let recent = ['#6D5BD0', '#33CFE0', '#F0404E', '#FFFFFF', '#F2C230', '#3BCB6B']
  let tool = 'brush'
  let paint = L.kind === 'custom' ? [...L.leds] : [...$leds]
  let sendTimer, dirty = false
  function push() {
    dirty = true
    clearTimeout(sendTimer)
    sendTimer = setTimeout(async () => {
      try { await run('set_custom_color', [paint], { quiet: true }); leds.set(paint) } catch (e) { toast(e.message, 'bad') }
    }, 45)
  }
  function onPaint(e) {
    const k = e.detail.key
    if (tool === 'fill') paint = paint.map((_, i) => KEYS.some(x => x.led === i) ? brush : paint[i])
    else paint[k.led] = tool === 'erase' ? '#000000' : brush
    paint = paint
    push()
    if (tool !== 'erase' && !recent.includes(brush)) recent = [brush, ...recent].slice(0, 8)
  }
  function fillAll(c) { paint = Array(NUM_LEDS).fill(c); push() }
  async function saveOnboard() {
    await run('set_custom_color', [paint])
    await run('save_to_hardware', [], { success: 'Saved to the keyboard — it keeps these colours without the app' })
    dirty = false
  }
  let brush2 = '#33CFE0'
  const lerpHex = (a, b, t) => rgbToHex(hexToRgb(a).map((v, i) => v + (hexToRgb(b)[i] - v) * t))
  function gradient(dir) {
    const xs = KEYS.map(k => dir === 'h' ? k.x + k.w / 2 : k.y + k.h / 2)
    const lo = Math.min(...xs), hi = Math.max(...xs)
    KEYS.forEach((k, i) => (paint[k.led] = lerpHex(brush, brush2, (xs[i] - lo) / (hi - lo))))
    paint = paint; push()
  }
  function rowPaint(row) { KEYS.filter(k => k.row === row).forEach(k => (paint[k.led] = brush)); paint = paint; push() }

  // ── live studio ─────────────────────────────────────────────────────
  let engine = L.kind === 'studio' && L.engine !== 'effect' ? L.engine : 'audio'
  let ac = { mode: 'spectrum', device_id: null, ...$audioConfig, ...(L.engine === 'audio' ? L.config : {}) }
  let hm = { decay_rate: 0.02, hot_color: [254, 60, 20], cold_color: [10, 10, 60], ...(L.engine === 'heatmap' ? L.config : {}) }
  let am = { saturation: 1.4, brightness: 1.0, fps: 20, ...(L.engine === 'ambient' ? L.config : {}) }
  let sm = { mode: 'cycle', interval: 1, color_low: [40, 220, 120], color_mid: [250, 200, 40], color_high: [240, 50, 70], ...(L.engine === 'sysmon' ? L.config : {}) }
  $: liveOn = $status.studio && $status.studio !== 'effect'
  $: cfgFor = { audio: ac, heatmap: hm, sysmon: sm, ambient: am }[engine]
  async function startLive() {
    await run('set_lighting', [{ kind: 'studio', engine, config: cfgFor }], { success: engineLabel[engine] + ' is live' })
  }
  async function stopLive() { await run('stop_studio') }
  const engineLabel = { audio: 'Music', ambient: 'Screen', heatmap: 'Typing heat', sysmon: 'System monitor' }

  let tuneTimer
  function tune() {
    if ($status.studio !== engine) return
    clearTimeout(tuneTimer)
    tuneTimer = setTimeout(() => {
      if (engine === 'audio') api('configure_audio', ac).catch(() => {})
      if (engine === 'heatmap') api('configure_heatmap', hm.decay_rate, hm.hot_color, hm.cold_color).catch(() => {})
      if (engine === 'ambient') run('set_lighting', [{ kind: 'studio', engine: 'ambient', config: am }], { quiet: true }).catch(() => {})
      if (engine === 'sysmon') api('configure_sysmon', sm.mode, sm.interval, sm.color_low, sm.color_mid, sm.color_high).catch(() => {})
    }, 80)
  }
  let stats = null
  const poll = setInterval(async () => {
    if ($status.studio === 'sysmon') { try { stats = (await api('get_sysmon_stats')).stats } catch {} }
  }, 1000)
  onDestroy(() => clearInterval(poll))

  const pct = (v, lo, hi) => `--pct:${((v - lo) / (hi - lo)) * 100}%`
</script>

<section class="px-7 pt-6 pb-10 max-w-[1180px]">
  <KeyboardStage
    colors={tab === 'paint' ? paint : null}
    mode={tab === 'paint' ? 'paint' : tab === 'layers' && pickHighlight ? 'select' : 'view'}
    selected={tab === 'layers' ? new Set(layers.highlight.keys) : new Set()}
    on:paint={onPaint}
    on:select={toggleHighlightKey}
  />

  <div class="flex items-center justify-between mt-6 mb-5">
    <div class="seg" role="tablist">
      <button aria-pressed={tab === 'effects'} on:click={() => (tab = 'effects')}>Effects</button>
      <button aria-pressed={tab === 'paint'} on:click={() => (tab = 'paint')}>Per-key colour</button>
      <button aria-pressed={tab === 'live'} on:click={() => (tab = 'live')}>Live</button>
      <button aria-pressed={tab === 'layers'} on:click={() => (tab = 'layers')}>Layers</button>
    </div>
    {#if tab === 'paint'}
      <button class="btn-primary" on:click={saveOnboard}><Save size={15} /> Save to keyboard</button>
    {/if}
  </div>

  {#if tab === 'effects'}
    <div class="grid grid-cols-[1fr_320px] gap-8">
      <div>
        <h2 class="text-[13px] font-semibold mb-3">Built into the keyboard</h2>
        <div class="grid grid-cols-4 gap-2 mb-6">
          {#each $modes.filter(m => !m.software) as m}
            <button class="h-11 rounded-lg border text-left px-3 text-[13px] transition-colors
                           {+fx.mode === m.id && $status.studio !== 'audio' ? 'border-lav bg-lav-wash text-lav-deep font-semibold' : 'border-rule bg-card hover:border-ink-faint'}"
                    on:click={() => applyFx({ mode: m.id })}>{m.name}</button>
          {/each}
        </div>
        <h2 class="text-[13px] font-semibold mb-1">Drawn by the app</h2>
        <p class="text-[12.5px] text-ink-mute mb-3">These run while AK820 Studio is open.</p>
        <div class="grid grid-cols-4 gap-2">
          {#each $modes.filter(m => m.software) as m}
            <button class="h-11 rounded-lg border text-left px-3 text-[13px] transition-colors
                           {+fx.mode === m.id ? 'border-lav bg-lav-wash text-lav-deep font-semibold' : 'border-rule bg-card hover:border-ink-faint'}"
                    on:click={() => applyFx({ mode: m.id })}>{m.name}</button>
          {/each}
        </div>
      </div>

      <aside class="flex flex-col gap-5">
        <h2 class="text-[15px] font-semibold">{current?.name ?? 'Effect'}</h2>
        {#if ctl.includes('B')}
          <label class="flex flex-col gap-2"><span class="label flex justify-between">Brightness <span class="text-ink">{+fx.brightness + 1} / 5</span></span>
            <input type="range" min="0" max="4" step="1" value={fx.brightness} style={pct(fx.brightness, 0, 4)}
                   on:input={e => applyFx({ brightness: +e.currentTarget.value })} /></label>
        {/if}
        {#if ctl.includes('S')}
          <label class="flex flex-col gap-2"><span class="label flex justify-between">Speed <span class="text-ink">{+fx.speed + 1} / 5</span></span>
            <input type="range" min="0" max="4" step="1" value={fx.speed} style={pct(fx.speed, 0, 4)}
                   on:input={e => applyFx({ speed: +e.currentTarget.value })} /></label>
        {/if}
        {#if ctl.includes('D')}
          <button class="btn-line self-start" on:click={() => applyFx({ direction: fx.direction ? 0 : 1 })}>
            <ArrowLeftRight size={15} /> {fx.direction ? 'Reversed' : 'Forward'}
          </button>
        {/if}
        {#if ctl.includes('C')}
          <div>
            <div class="label mb-2">Colour</div>
            <div class="flex flex-wrap gap-2">
              {#each Object.entries(SWATCH) as [name, bg]}
                <button class="w-8 h-8 rounded-full border border-ink/10 transition-transform hover:scale-110
                               {fx.color === name ? 'ring-2 ring-offset-2 ring-lav' : ''}"
                        style="background:{bg}" title={name === 'rgb' ? 'Rainbow' : name}
                        aria-label={name === 'rgb' ? 'Rainbow' : name}
                        on:click={() => applyFx({ color: name })}></button>
              {/each}
            </div>
          </div>
        {/if}
      </aside>
    </div>

  {:else if tab === 'paint'}
    <div class="flex flex-wrap items-center gap-6">
      <div class="seg">
        <button aria-pressed={tool === 'brush'} on:click={() => (tool = 'brush')} title="Paint keys (drag to paint several)"><Paintbrush size={14} class="inline -mt-0.5 mr-1" />Brush</button>
        <button aria-pressed={tool === 'fill'} on:click={() => (tool = 'fill')} title="Click any key to fill every key"><PaintBucket size={14} class="inline -mt-0.5 mr-1" />Fill</button>
        <button aria-pressed={tool === 'erase'} on:click={() => (tool = 'erase')}><Eraser size={14} class="inline -mt-0.5 mr-1" />Erase</button>
      </div>
      <label class="flex items-center gap-2.5"><input type="color" bind:value={brush} class="w-9 h-9" aria-label="Brush colour" />
        <span class="font-cap text-[13px] text-ink-soft uppercase">{brush}</span></label>
      <div class="flex items-center gap-2">
        <input type="color" bind:value={brush2} class="w-7 h-7" aria-label="Second gradient colour" />
        <button class="btn-quiet h-7 px-2 text-[12px]" title="Blend from the brush colour to this colour, left to right" on:click={() => gradient('h')}>Gradient across</button>
        <button class="btn-quiet h-7 px-2 text-[12px]" title="Blend top to bottom" on:click={() => gradient('v')}>Gradient down</button>
      </div>
      <div class="flex gap-1.5">
        {#each recent as c}<button class="w-7 h-7 rounded-md border border-ink/10 {brush === c ? 'ring-2 ring-lav ring-offset-1' : ''}" style="background:{c}" aria-label="Use {c}" on:click={() => (brush = c)}></button>{/each}
      </div>
      <div class="flex gap-1 ml-auto">
        {#each ['Function row', 'Numbers', 'Top letters', 'Home row', 'Bottom letters', 'Space row'] as r, i}
          <button class="btn-quiet h-7 px-2 text-[12px]" title="Paint the {r.toLowerCase()} with the brush colour" on:click={() => rowPaint(i)}>{r}</button>
        {/each}
        <button class="btn-quiet h-7 px-2 text-[12px]" on:click={() => fillAll('#000000')}>Clear</button>
      </div>
    </div>
    <p class="text-[12.5px] text-ink-mute mt-4">Changes show on the keyboard as you paint. {dirty ? 'Save to keyboard to keep them after the app closes.' : ''}</p>

  {:else if tab === 'live'}
    <div class="flex items-center gap-4 mb-6">
      <div class="seg">
        {#each Object.entries(engineLabel) as [id, name]}
          <button aria-pressed={engine === id} on:click={() => (engine = id)}>{name}</button>
        {/each}
      </div>
      {#if $status.studio === engine}
        <button class="btn-line" on:click={stopLive}><Square size={14} /> Stop</button>
        <span class="chip bg-ok/10 text-ok">Running</span>
      {:else}
        <button class="btn-primary" on:click={startLive}><Play size={14} /> Start {engineLabel[engine].toLowerCase()}</button>
        {#if liveOn}<span class="text-[12.5px] text-ink-mute">{engineLabel[$status.studio]} is running and will stop.</span>{/if}
      {/if}
    </div>

    <div class="grid grid-cols-3 gap-x-10 gap-y-5 max-w-[900px]">
      {#if engine === 'audio'}
        <label class="flex flex-col gap-2 col-span-2"><span class="label">Listen to</span>
          <select class="field" bind:value={ac.device_id} on:change={tune}>
            <option value="system">What's playing on this PC</option>
            <option value={null}>Default microphone</option>
            {#each $audioDevices as d}<option value={d.id}>{d.name}</option>{/each}
          </select>
          <span class="text-[12px] text-ink-mute">"What's playing on this PC" listens to your speakers directly, so you don't need Stereo Mix.</span>
        </label>
        <div class="flex flex-col gap-2"><span class="label">Style</span>
          <div class="seg self-start">
            <button aria-pressed={ac.mode === 'spectrum'} on:click={() => { ac.mode = 'spectrum'; tune() }}>Frequency bands</button>
            <button aria-pressed={ac.mode === 'volume'} on:click={() => { ac.mode = 'volume'; tune() }}>Volume</button>
          </div></div>
        <label class="flex flex-col gap-2"><span class="label">Sensitivity</span>
          <input type="range" min="1" max="20" step="0.5" bind:value={ac.sensitivity} style={pct(ac.sensitivity, 1, 20)} on:input={tune} /></label>
        <label class="flex flex-col gap-2"><span class="label">Fade</span>
          <input type="range" min="0.6" max="0.97" step="0.01" bind:value={ac.smoothing_falloff} style={pct(ac.smoothing_falloff, .6, .97)} on:input={tune} /></label>
        <div class="flex items-end gap-4">
          {#each [['bass_color', 'Bass'], ['mid_color', 'Mid'], ['treble_color', 'Treble']] as [k, n]}
            <label class="flex flex-col items-center gap-1.5"><input type="color" class="w-9 h-9" value={rgbToHex(ac[k])}
                   on:input={e => { ac[k] = hexToRgb(e.currentTarget.value); tune() }} /><span class="label">{n}</span></label>
          {/each}
        </div>
      {:else if engine === 'ambient'}
        <label class="flex flex-col gap-2"><span class="label">Colour boost</span>
          <input type="range" min="0.8" max="2.5" step="0.1" bind:value={am.saturation} style={pct(am.saturation, .8, 2.5)} on:change={tune} /></label>
        <label class="flex flex-col gap-2"><span class="label">Brightness</span>
          <input type="range" min="0.2" max="1.2" step="0.05" bind:value={am.brightness} style={pct(am.brightness, .2, 1.2)} on:change={tune} /></label>
        <label class="flex flex-col gap-2"><span class="label">Smoothness ({am.fps} updates a second)</span>
          <input type="range" min="5" max="30" step="1" bind:value={am.fps} style={pct(am.fps, 5, 30)} on:change={tune} /></label>
        <p class="col-span-3 text-[12px] text-ink-mute">Each key takes the colour of the part of your main screen above it, like an ambient TV light. The screen image never leaves this PC.</p>
      {:else if engine === 'heatmap'}
        <label class="flex flex-col gap-2 col-span-2"><span class="label">Cool-down</span>
          <input type="range" min="0.004" max="0.08" step="0.002" bind:value={hm.decay_rate} style={pct(hm.decay_rate, .004, .08)} on:input={tune} />
          <span class="text-[12px] text-ink-mute">Keys you press glow and fade. Nothing you type is stored.</span></label>
        <div class="flex items-end gap-4">
          <label class="flex flex-col items-center gap-1.5"><input type="color" class="w-9 h-9" value={rgbToHex(hm.hot_color)} on:input={e => { hm.hot_color = hexToRgb(e.currentTarget.value); tune() }} /><span class="label">Pressed</span></label>
          <label class="flex flex-col items-center gap-1.5"><input type="color" class="w-9 h-9" value={rgbToHex(hm.cold_color)} on:input={e => { hm.cold_color = hexToRgb(e.currentTarget.value); tune() }} /><span class="label">Resting</span></label>
        </div>
      {:else}
        <div class="flex flex-col gap-2"><span class="label">Show</span>
          <select class="field" bind:value={sm.mode} on:change={tune}>
            <option value="cycle">CPU, RAM and GPU in turn</option>
            <option value="highest">Whichever is busiest</option>
            <option value="split">All three side by side</option>
          </select></div>
        <label class="flex flex-col gap-2"><span class="label">Update every {sm.interval}s</span>
          <input type="range" min="0.5" max="5" step="0.5" bind:value={sm.interval} style={pct(sm.interval, .5, 5)} on:input={tune} /></label>
        <div class="flex items-end gap-4">
          {#each [['color_low', 'Idle'], ['color_mid', 'Busy'], ['color_high', 'Maxed']] as [k, n]}
            <label class="flex flex-col items-center gap-1.5"><input type="color" class="w-9 h-9" value={rgbToHex(sm[k])} on:input={e => { sm[k] = hexToRgb(e.currentTarget.value); tune() }} /><span class="label">{n}</span></label>
          {/each}
        </div>
        {#if stats && $status.studio === 'sysmon'}
          <div class="col-span-3 flex gap-8 font-cap text-[15px]">
            <span>CPU {stats.cpu}%</span><span>RAM {stats.mem}%</span><span>GPU {stats.gpu}%</span>
          </div>
        {/if}
      {/if}
    </div>
  {:else if tab === 'layers'}
    <p class="text-[12.5px] text-ink-mute mb-5 max-w-[640px]">Layers sit on top of per-key colour and live lighting, and are saved with the profile. The keyboard's built-in effects run on the keyboard itself, so layers don't show over them.</p>
    <div class="flex flex-col gap-3 max-w-[760px]">
      {#each [['caps', 'Caps Lock indicator', 'Caps Lock lights up while it is on.'], ['game', 'Game mode keys', 'Blocked keys (Win, Tab, F4) turn this colour while game mode blocks them.'], ['highlight', 'Highlight keys', 'Chosen keys always show this colour, for example WASD in a game profile.']] as [id, name, hint]}
        <div class="flex items-center gap-4 rounded-xl border border-rule bg-card px-4 py-3">
          <button class="w-9 h-5 rounded-full relative shrink-0 transition-colors {layers[id].on ? 'bg-lav' : 'bg-ink/15'}" aria-pressed={layers[id].on} aria-label="Toggle {name}"
                  on:click={() => { layers[id].on = !layers[id].on; saveLayers() }}>
            <span class="absolute top-[3px] w-[14px] h-[14px] rounded-full bg-white shadow transition-all {layers[id].on ? 'left-[19px]' : 'left-[3px]'}"></span>
          </button>
          <div class="flex-1">
            <div class="text-[13.5px] font-semibold">{name}</div>
            <div class="text-[12.5px] text-ink-mute">{hint}</div>
            {#if id === 'highlight'}
              <div class="flex flex-wrap items-center gap-1.5 mt-2">
                {#each layers.highlight.keys as h}<span class="chip bg-ink/[0.06] font-cap">{HID_NAMES[h] ?? h}</span>{/each}
                <button class="btn-quiet h-6 px-2 text-[12px] {pickHighlight ? 'text-lav' : ''}" on:click={() => (pickHighlight = !pickHighlight)}>
                  {pickHighlight ? 'Done choosing' : 'Choose keys on the keyboard'}</button>
              </div>
            {/if}
          </div>
          <input type="color" class="w-9 h-9" bind:value={layers[id].color} on:change={saveLayers} aria-label="{name} colour" />
        </div>
      {/each}
    </div>
  {/if}
</section>
