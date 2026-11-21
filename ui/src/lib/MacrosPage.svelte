<script>
  import { onDestroy } from 'svelte'
  import { Plus, Circle, Square, Trash2, ArrowUp, ArrowDown } from 'lucide-svelte'
  import { macros, meta, run, api, toast } from './store.js'
  import { HID_NAMES, DOM_CODE_TO_HID } from './keycodes.js'

  let current = null       // macro being edited (copy)
  let recording = false
  let addCapture = false

  function select(m) { stopRec(); current = JSON.parse(JSON.stringify(m)) }
  function blank() { stopRec(); current = { id: null, name: `Macro ${$macros.length + 1}`, repeat: 1, events: [] } }
  if ($macros.length) select($macros[0])

  $: max = $meta.max_macro_events ?? 27
  $: full = current && current.events.length >= max
  $: total = current ? current.events.reduce((s, e) => s + Math.max(10, e.delay), 0) : 0
  $: unsaved = current && JSON.stringify(current) !== JSON.stringify($macros.find(m => m.id === current.id) ?? null)

  const onRec = e => { if (recording && current) current.events = e.detail.map(x => ({ ...x })) }
  window.addEventListener('ak:record', onRec)
  onDestroy(() => { window.removeEventListener('ak:record', onRec); stopRec() })

  async function startRec() {
    try { await api('record_start'); recording = true; current.events = [] }
    catch (e) { toast(e.message, 'bad') }
  }
  async function stopRec() {
    if (!recording) return
    recording = false
    const r = await api('record_stop')
    if (current) current.events = r.events
    if (r.truncated) toast(`Only the first ${max} steps fit on the keyboard`, 'warn')
  }

  async function save() {
    if (!current.events.length) return toast('Add at least one step first', 'warn')
    const r = await run('save_macro', [current], { success: `Saved “${current.name}”` })
    current = JSON.parse(JSON.stringify(r.macro))
  }
  async function remove() {
    if (current.id) await run('delete_macro', [current.id], { success: 'Macro deleted' })
    current = null
  }
  function move(i, d) { const ev = current.events; [ev[i], ev[i + d]] = [ev[i + d], ev[i]]; current = current }
  function del(i) { current.events.splice(i, 1); current = current }

  function onKey(e) {
    if (!addCapture || !current) return
    e.preventDefault(); e.stopPropagation()
    const hid = DOM_CODE_TO_HID[e.code]
    if (hid == null) return
    addCapture = false
    if (current.events.length + 2 > max) return toast(`A macro holds up to ${max} steps`, 'warn')
    current.events = [...current.events, { code: hid, up: false, delay: 20 }, { code: hid, up: true, delay: 20 }]
  }
</script>

<svelte:window on:keydown|capture={onKey} />

<section class="px-7 pt-6 pb-10 grid grid-cols-[240px_1fr] gap-8 max-w-[1100px]">
  <div class="flex flex-col gap-1">
    <button class="btn-primary mb-3 self-start" on:click={blank}><Plus size={15} /> New macro</button>
    {#each $macros as m}
      <button class="h-10 rounded-lg px-3 text-left text-[13.5px] flex items-center justify-between
                     {current?.id === m.id ? 'bg-card shadow-sm font-semibold' : 'hover:bg-ink/[0.05] text-ink-soft'}"
              on:click={() => select(m)}>{m.name}<span class="text-[12px] text-ink-faint font-normal">{m.events.length}</span></button>
    {:else}
      <p class="text-[13px] text-ink-mute px-1">Macros replay a sequence of key presses from a single key — the keyboard runs them itself, even without the app.</p>
    {/each}
  </div>

  {#if current}
    <div>
      <div class="flex items-center gap-3 mb-5">
        <input class="field text-[15px] font-semibold w-[280px]" bind:value={current.name} aria-label="Macro name" />
        <label class="flex items-center gap-2 text-[12.5px] text-ink-mute">Repeat
          <input class="field w-16" type="number" min="1" max="255" bind:value={current.repeat} /> times</label>
        <div class="ml-auto flex gap-2">
          {#if current.id}<button class="btn-danger" on:click={remove}><Trash2 size={14} /> Delete</button>{/if}
          <button class="btn-primary" disabled={!unsaved || recording} on:click={save}>Save macro</button>
        </div>
      </div>

      <div class="flex items-center gap-3 mb-4">
        {#if recording}
          <button class="btn h-9 bg-bad text-white hover:bg-bad/90" on:click={stopRec}><Square size={13} fill="currentColor" /> Stop recording</button>
          <span class="text-[13px] text-ink-mute">Type the sequence now{$meta.web ? ' (in this window)' : ''}. Timing is recorded too.</span>
        {:else}
          <button class="btn-line h-9" on:click={startRec} disabled={!$meta.hook_available && !$meta.web}><Circle size={13} class="text-bad" fill="currentColor" /> Record</button>
          <button class="btn-line h-9 {addCapture ? 'border-lav text-lav' : ''}" disabled={full} on:click={() => (addCapture = !addCapture)}>
            <Plus size={14} /> {addCapture ? 'Press a key…' : 'Add a key press'}</button>
          <span class="ml-auto text-[12.5px] text-ink-mute">{current.events.length} / {max} steps — about {(total / 1000).toFixed(2)} s</span>
        {/if}
      </div>

      {#if current.events.length}
        <ol class="rounded-xl border border-rule bg-card divide-y divide-rule max-h-[460px] overflow-y-auto">
          {#each current.events as ev, i}
            <li class="flex items-center gap-4 h-11 px-4 text-[13px]">
              <span class="w-6 text-ink-faint text-right">{i + 1}</span>
              <span class="w-16 chip {ev.up ? 'bg-ink/[0.05] text-ink-mute' : 'bg-lav-wash text-lav-deep'}">{ev.up ? 'Release' : 'Press'}</span>
              <span class="font-cap text-[14px] w-32">{HID_NAMES[ev.code] ?? '0x' + ev.code.toString(16)}</span>
              <label class="flex items-center gap-1.5 text-ink-mute">then wait
                <input class="field h-7 w-20" type="number" min="0" max="1270" step="10" bind:value={ev.delay} /> ms</label>
              <span class="ml-auto flex gap-0.5">
                <button class="btn-quiet h-7 w-7 px-0" aria-label="Move up" disabled={i === 0} on:click={() => move(i, -1)}><ArrowUp size={14} /></button>
                <button class="btn-quiet h-7 w-7 px-0" aria-label="Move down" disabled={i === current.events.length - 1} on:click={() => move(i, 1)}><ArrowDown size={14} /></button>
                <button class="btn-quiet h-7 w-7 px-0 hover:text-bad" aria-label="Remove step" on:click={() => del(i)}><Trash2 size={14} /></button>
              </span>
            </li>
          {/each}
        </ol>
        <p class="text-[12px] text-ink-mute mt-3">Waits are stored in 10 ms steps, up to 1.27 s each. Assign the macro to a key on the Keys page.</p>
      {:else if !recording}
        <div class="rounded-xl border border-dashed border-rule p-8 text-center text-[13px] text-ink-mute">
          Press Record and type, or add key presses one at a time.
        </div>
      {/if}
    </div>
  {/if}
</section>
