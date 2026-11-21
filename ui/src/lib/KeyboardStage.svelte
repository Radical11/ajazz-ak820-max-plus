<script>
  // The keyboard, drawn from the vendor's own layout data, sitting on a desk mat.
  // Colours come from the real LED buffer, so what you see is what the board shows.
  import { createEventDispatcher } from 'svelte'
  import { KEYS, BOUNDS } from './layout.js'

  export let colors = null          // 108 '#rrggbb' or null
  export let mode = 'view'          // view | paint | select
  export let selected = new Set()   // hid codes
  export let pressed = new Set()    // hid codes
  export let badges = {}            // hid -> short text (remaps)
  export let disabled = new Set()   // hid codes that can't be edited here
  export let compact = false

  const dispatch = createEventDispatcher()
  const PAD = 10
  const X0 = BOUNDS.minX - PAD, Y0 = BOUNDS.minY - PAD
  const W = BOUNDS.width - BOUNDS.minX + PAD * 2, H = BOUNDS.height - BOUNDS.minY + PAD * 2

  const LAV = new Set(['Tab', 'CapsLock', 'LShift', 'RShift', 'LCtrl', 'Win', 'LAlt', 'RAlt', 'Fn', 'RCtrl',
    'Backspace', 'F5', 'F6', 'F7', 'F8', 'Home', 'PgUp', 'PgDn', 'End', 'Del', '↑', '←', '↓', '→'])
  const SKY = new Set(['Esc', 'Space', 'Enter'])
  const capTone = k => SKY.has(k.id) ? 'sky' : LAV.has(k.id) ? 'lav' : 'white'

  let painting = false

  function lum(hex) {
    if (!hex) return 0
    const n = parseInt(hex.slice(1), 16)
    return Math.max((n >> 16) & 255, (n >> 8) & 255, n & 255) / 255
  }

  function down(e, k) {
    if (disabled.has(k.hid)) return
    if (mode === 'paint') { painting = true; dispatch('paint', { key: k }) }
    else if (mode === 'select') dispatch('select', { key: k, additive: e.shiftKey || e.ctrlKey })
  }
  function enter(k) { if (painting && mode === 'paint' && !disabled.has(k.hid)) dispatch('paint', { key: k }) }
  function keydown(e, k) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); down(e, k) } }
</script>

<svelte:window on:pointerup={() => (painting = false)} />

<div class="stage" class:compact role="group" aria-label="Keyboard">
  <div class="board" style="aspect-ratio:{W} / {H}">
    {#each KEYS as k (k.hid)}
      {@const c = colors ? colors[k.led] : null}
      {@const glow = lum(c)}
      <button
        type="button"
        class="key {capTone(k)}"
        class:sel={selected.has(k.hid)}
        class:hit={pressed.has(k.hid)}
        class:off={disabled.has(k.hid)}
        class:interactive={mode !== 'view'}
        style="left:{((k.x - X0) / W) * 100}%; top:{((k.y - Y0) / H) * 100}%;
               width:{(k.w / W) * 100}%; height:{(k.h / H) * 100}%;
               --led:{c ?? 'transparent'}; --glow:{glow};"
        aria-label={k.id}
        aria-pressed={selected.has(k.hid)}
        tabindex={mode === 'view' ? -1 : 0}
        on:pointerdown|preventDefault={e => down(e, k)}
        on:pointerenter={() => enter(k)}
        on:keydown={e => keydown(e, k)}
      >
        <span class="cap">
          {#if k.shift}<span class="shift">{k.shift}</span>{/if}
          <span class="legend">{k.label}</span>
          {#if badges[k.hid]}<span class="badge">{badges[k.hid]}</span>{/if}
        </span>
      </button>
    {/each}
    <!-- volume knob -->
    <div class="knob" style="left:{((537 - X0) / W) * 100}%; top:{((38 - Y0) / H) * 100}%; width:{(36 / W) * 100}%"></div>
  </div>
</div>

<style>
  .stage {
    background:
      radial-gradient(120% 140% at 50% 0%, #26243A 0%, #1A1926 55%, #15141F 100%);
    border-radius: 18px;
    padding: 28px 36px;
    box-shadow: inset 0 0 0 1px #2A2838, 0 20px 40px -24px rgba(26,25,38,.6);
  }
  .stage.compact { padding: 18px 24px; }
  .stage.compact .board { max-width: min(900px, calc((100vh - 330px) * 2.4)); }
  .board {
    position: relative;
    width: 100%;
    max-width: min(1040px, calc((100vh - 330px) * 2.4));
    margin: 0 auto;
    background: linear-gradient(#F4F5FA, #E3E5EE);
    border-radius: 14px;
    box-shadow: 0 1px 0 rgba(255,255,255,.4) inset, 0 18px 30px -12px rgba(0,0,0,.6), 0 2px 0 #C9CBD8;
  }
  .key {
    position: absolute;
    padding: 1.5px;
    border-radius: 7px;
    background: transparent;
    /* the LED: light leaking up around the cap */
    box-shadow: 0 0 calc(4px + 10px * var(--glow)) calc(1px * var(--glow)) color-mix(in srgb, var(--led) calc(var(--glow) * 85%), transparent);
    transition: transform .06s ease, box-shadow .2s ease;
    cursor: default;
  }
  .key.interactive { cursor: pointer; }
  .cap {
    position: relative;
    display: flex; flex-direction: column; justify-content: center; align-items: center;
    width: 100%; height: 100%;
    border-radius: 6px;
    font-family: Bahnschrift, 'Segoe UI', sans-serif;
    font-size: clamp(8px, 0.95vw, 12px);
    line-height: 1;
    color: #3B3654;
    box-shadow: inset 0 -3px 0 rgba(0,0,0,.12), inset 0 1px 0 rgba(255,255,255,.8), 0 1px 1px rgba(0,0,0,.3);
    /* underglow tint on the cap's lower edge */
    background-image: linear-gradient(to top, color-mix(in srgb, var(--led) calc(var(--glow) * 45%), transparent) 0%, transparent 38%);
  }
  .white .cap { background-color: #F2F3F8; }
  .lav .cap   { background-color: #BDB2E8; color: #2E2650; }
  .sky .cap   { background-color: #B6CBE8; color: #23324F; }
  .shift { font-size: .8em; opacity: .6; margin-bottom: 2px; }
  .badge {
    position: absolute; left: 50%; bottom: -7px; transform: translateX(-50%);
    max-width: 140%; padding: 1px 5px; border-radius: 6px;
    background: #6D5BD0; color: #fff; font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
    font-size: 9.5px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    box-shadow: 0 2px 6px rgba(75,59,170,.45);
    z-index: 2;
  }
  .key.interactive:hover .cap { filter: brightness(1.04); }
  .key.sel { box-shadow: 0 0 0 2px #fff, 0 0 0 4px #6D5BD0; z-index: 3; }
  .key.hit { transform: translateY(1.5px); }
  .key.hit .cap { background-color: #6D5BD0; color: #fff; }
  .key.off { opacity: .35; }
  .knob {
    position: absolute; aspect-ratio: 1; border-radius: 50%;
    background: conic-gradient(from 0deg, #e9eaf0, #b9bccb, #f4f5fa, #aeb1c1, #e9eaf0);
    box-shadow: inset 0 0 0 3px #d6d8e2, 0 3px 6px rgba(0,0,0,.35);
  }
</style>
