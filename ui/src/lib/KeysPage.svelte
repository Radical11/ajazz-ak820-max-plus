<script>
  import { RotateCcw, Ban, Keyboard as KbIcon, Music, Command, Repeat, Undo2, History } from 'lucide-svelte'
  import KeyboardStage from './KeyboardStage.svelte'
  import { profile, macros, run, page } from './store.js'
  import { KEYS, KEY_BY_HID } from './layout.js'
  import { HID_NAMES, MEDIA, KEY_GROUPS, codeName, DOM_CODE_TO_HID } from './keycodes.js'

  let layer = '1'
  let selected = null        // layout key object
  let kind = 'key'
  let capture = false
  let combo = new Set()      // shortcut builder (hid codes)

  $: keymap = $profile?.keymap?.[layer] ?? {}
  $: fnLocked = new Set(layer === '2' ? KEYS.filter(k => k.fnLock).map(k => k.hid) : [])
  $: action = selected ? keymap[String(selected.hid)] : null
  $: badges = Object.fromEntries(Object.entries(keymap).map(([src, a]) => [src, short(a)]))
  $: if (selected && fnLocked.has(selected.hid)) selected = null
  $: changedCount = Object.keys(keymap).length

  function short(a) {
    if (!a) return ''
    if (a.type === 'disabled') return 'Off'
    if (a.type === 'macro') return $macros.find(m => m.id === a.macro_id)?.name ?? 'Macro'
    if (a.type === 'shortcut') return a.codes.map(c => (HID_NAMES[c] ?? '').replace(/^[LR]-/, '')).join('+')
    return codeName(a.code)
  }
  function describe(a) {
    if (!a) return 'Default — types its printed key'
    if (a.type === 'disabled') return 'Disabled'
    if (a.type === 'macro') return `Plays macro “${short(a)}”`
    if (a.type === 'shortcut') return `Sends ${short(a)}`
    return `Sends ${codeName(a.code)}`
  }

  function pick(e) {
    selected = e.detail.key
    const a = keymap[String(selected.hid)]
    kind = a ? (a.type === 'disabled' ? 'key' : a.type) : 'key'
    combo = new Set(a?.type === 'shortcut' ? a.codes : [])
  }

  // undo history for this session: what each key did before a change
  let history = []
  async function assign(a, key = selected, lay = layer, record = true) {
    if (!key) return
    const prev = $profile?.keymap?.[lay]?.[String(key.hid)] ?? { type: 'default' }
    await run('assign_key', [+lay, key.hid, a])
    if (record) history = [...history.slice(-49), { key, layer: lay, prev, next: a }]
  }
  async function undo() {
    const h = history.at(-1)
    if (!h) return
    history = history.slice(0, -1)
    await run('assign_key', [+h.layer, h.key.hid, h.prev], { success: `Undid ${h.key.label}` })
  }
  function onUndoKey(e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !capture && !(e.target instanceof HTMLInputElement)) { e.preventDefault(); undo() }
  }
  $: changes = Object.entries(keymap).map(([src, a]) => ({ key: KEY_BY_HID[+src], action: a })).filter(c => c.key)

  function onCapture(e) {
    if (!capture || !selected) return
    e.preventDefault(); e.stopPropagation()
    const hid = DOM_CODE_TO_HID[e.code]
    if (hid == null) return
    if (kind === 'shortcut') { combo.add(hid); combo = combo; if (hid < 0xE0) capture = false }
    else { capture = false; assign({ type: 'key', code: hid }) }
  }

  const MODS = [[0xE0, 'Ctrl'], [0xE1, 'Shift'], [0xE2, 'Alt'], [0xE3, 'Win']]
  function toggleMod(m) { combo.has(m) ? combo.delete(m) : combo.add(m); combo = combo }
  $: comboList = [...combo].sort((a, b) => (b >= 0xE0) - (a >= 0xE0) || a - b)
  const PRESETS = [
    ['Copy', [0xE0, 0x06]], ['Paste', [0xE0, 0x19]], ['Undo', [0xE0, 0x1D]], ['Screenshot', [0xE3, 0xE1, 0x16]],
    ['Task Manager', [0xE0, 0xE1, 0x29]], ['Lock PC', [0xE3, 0x0F]], ['Desktop', [0xE3, 0x07]], ['Emoji', [0xE3, 0x37]],
  ]
</script>

<svelte:window on:keydown|capture={onCapture} on:keydown={onUndoKey} />

<section class="px-7 pt-6 pb-10 max-w-[1180px]">
  <div class="flex items-center justify-between mb-4">
    <div class="seg">
      <button aria-pressed={layer === '1'} on:click={() => (layer = '1')}>Base layer</button>
      <button aria-pressed={layer === '2'} on:click={() => (layer = '2')}>Fn layer</button>
    </div>
    <div class="flex items-center gap-2">
      <span class="text-[12.5px] text-ink-mute">{changedCount ? `${changedCount} key${changedCount > 1 ? 's' : ''} changed on this layer` : 'Every key is at its default'}</span>
      <button class="btn-quiet" disabled={!history.length} title="Undo the last key change (Ctrl+Z)" on:click={undo}><History size={14} /> Undo</button>
      {#if changedCount}<button class="btn-quiet" on:click={() => run('reset_keys', [+layer], { success: 'Layer restored to defaults' })}><RotateCcw size={14} /> Reset layer</button>{/if}
    </div>
  </div>

  <KeyboardStage mode="select" selected={new Set(selected ? [selected.hid] : [])} {badges} disabled={fnLocked} on:select={pick} />
  {#if layer === '2'}<p class="text-[12.5px] text-ink-mute mt-3">Fn layer: what a key does while you hold Fn. Greyed keys are reserved by the keyboard's own Fn shortcuts.</p>{/if}

  {#if !selected}
    <div class="mt-7 grid grid-cols-[1fr_360px] gap-10">
      <p class="text-ink-mute text-[13.5px]">Choose a key on the keyboard to change what it does.</p>
      <div>
        <h2 class="text-[13px] font-semibold mb-2">Changed on the {layer === '1' ? 'base' : 'Fn'} layer</h2>
        {#if changes.length}
          <ul class="rounded-xl border border-rule bg-card divide-y divide-rule">
            {#each changes as c}
              <li class="flex items-center gap-3 h-10 px-3 text-[13px]">
                <button class="font-cap w-14 text-left hover:text-lav" on:click={() => pick({ detail: { key: c.key } })}>{c.key.label}</button>
                <span class="text-ink-faint">→</span>
                <span class="flex-1 truncate">{short(c.action)}</span>
                <button class="btn-quiet h-7 w-7 px-0" aria-label="Restore {c.key.label}" title="Restore default" on:click={() => assign({ type: 'default' }, c.key)}><Undo2 size={14} /></button>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="text-[12.5px] text-ink-faint">Nothing yet. Every key does what's printed on it.</p>
        {/if}
      </div>
    </div>
  {:else}
    <div class="mt-7 grid grid-cols-[220px_1fr] gap-8">
      <div>
        <div class="font-cap text-[28px] leading-none text-ink">{selected.label}</div>
        <div class="text-[13px] text-ink-mute mt-2">{describe(action)}</div>
        {#if action}
          <button class="btn-quiet mt-3 -ml-3" on:click={() => assign({ type: 'default' })}><Undo2 size={14} /> Restore default</button>
        {/if}
        <button class="btn-quiet -ml-3 {action?.type === 'disabled' ? 'text-bad' : ''}" on:click={() => assign({ type: action?.type === 'disabled' ? 'default' : 'disabled' })}>
          <Ban size={14} /> {action?.type === 'disabled' ? 'Enable key' : 'Disable key'}
        </button>
      </div>

      <div>
        <div class="seg mb-5">
          <button aria-pressed={kind === 'key'} on:click={() => (kind = 'key')}><KbIcon size={14} class="inline -mt-0.5 mr-1" />Another key</button>
          <button aria-pressed={kind === 'media'} on:click={() => (kind = 'media')}><Music size={14} class="inline -mt-0.5 mr-1" />Media &amp; apps</button>
          <button aria-pressed={kind === 'shortcut'} on:click={() => (kind = 'shortcut')}><Command size={14} class="inline -mt-0.5 mr-1" />Shortcut</button>
          <button aria-pressed={kind === 'macro'} on:click={() => (kind = 'macro')}><Repeat size={14} class="inline -mt-0.5 mr-1" />Macro</button>
        </div>

        {#if kind === 'key'}
          <button class="btn-line mb-5 {capture ? 'border-lav text-lav' : ''}" on:click={() => (capture = !capture)}>
            {capture ? 'Press the key you want…' : 'Press a key to choose it'}
          </button>
          <div class="flex flex-col gap-4">
            {#each KEY_GROUPS as g}
              <div>
                <div class="label mb-1.5">{g.name}</div>
                <div class="flex flex-wrap gap-1">
                  {#each g.codes as c}
                    <button class="h-8 min-w-[34px] px-2 rounded-md font-cap text-[12.5px] border transition-colors
                                   {action?.type === 'key' && action.code === c ? 'bg-lav text-white border-lav' : 'bg-card border-rule hover:border-ink-faint'}"
                            on:click={() => assign({ type: 'key', code: c })}>{HID_NAMES[c]}</button>
                  {/each}
                </div>
              </div>
            {/each}
          </div>

        {:else if kind === 'media'}
          <div class="grid grid-cols-3 gap-2 max-w-[620px]">
            {#each MEDIA as m}
              <button class="h-10 rounded-lg border px-3 text-left text-[13px] transition-colors
                             {action?.code === m.code && action?.type !== 'macro' ? 'bg-lav-wash border-lav text-lav-deep font-semibold' : 'bg-card border-rule hover:border-ink-faint'}"
                      on:click={() => assign({ type: 'media', code: m.code })}>{m.name}</button>
            {/each}
          </div>

        {:else if kind === 'shortcut'}
          <div class="flex flex-wrap items-center gap-2 mb-4">
            {#each MODS as [c, n]}
              <button class="h-8 px-3 rounded-md border text-[13px] {combo.has(c) ? 'bg-lav text-white border-lav' : 'bg-card border-rule'}" on:click={() => toggleMod(c)}>{n}</button>
            {/each}
            <span class="text-ink-faint">+</span>
            <button class="btn-line {capture ? 'border-lav text-lav' : ''}" on:click={() => (capture = !capture)}>{capture ? 'Press a key…' : 'Add a key'}</button>
          </div>
          <div class="flex items-center gap-3 mb-6">
            <div class="font-cap text-[18px] min-h-[28px]">{comboList.length ? comboList.map(c => (HID_NAMES[c] ?? '?').replace(/^L-/, '')).join(' + ') : 'Nothing yet'}</div>
            {#if comboList.length}<button class="btn-quiet" on:click={() => (combo = new Set())}>Clear</button>{/if}
            <button class="btn-primary ml-auto" disabled={!comboList.length} on:click={() => assign({ type: 'shortcut', codes: comboList })}>Assign shortcut</button>
          </div>
          <div class="label mb-2">Common shortcuts</div>
          <div class="flex flex-wrap gap-2">
            {#each PRESETS as [n, codes]}
              <button class="btn-line" on:click={() => { combo = new Set(codes); assign({ type: 'shortcut', codes }) }}>{n}</button>
            {/each}
          </div>

        {:else}
          {#if !$macros.length}
            <p class="text-[13px] text-ink-mute mb-3">You don't have any macros yet.</p>
            <button class="btn-primary" on:click={() => page.set('macros')}>Record a macro</button>
          {:else}
            <div class="flex flex-col gap-1.5 max-w-[420px]">
              {#each $macros as m}
                <button class="h-10 flex items-center justify-between rounded-lg border px-3 text-[13px]
                               {action?.type === 'macro' && action.macro_id === m.id ? 'bg-lav-wash border-lav text-lav-deep font-semibold' : 'bg-card border-rule hover:border-ink-faint'}"
                        on:click={() => assign({ type: 'macro', macro_id: m.id })}>
                  {m.name}<span class="text-[12px] text-ink-mute font-normal">{m.events.length} steps</span>
                </button>
              {/each}
            </div>
          {/if}
        {/if}
      </div>
    </div>
  {/if}
</section>
