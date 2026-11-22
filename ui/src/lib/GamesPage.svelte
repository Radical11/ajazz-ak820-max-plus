<script>
  // Games that use the keyboard's own lights. Keys are read in this window, so keep it focused.
  import { onDestroy } from 'svelte'
  import { Brain, Timer, Type, Trophy } from 'lucide-svelte'
  import KeyboardStage from './KeyboardStage.svelte'
  import { api, toast } from './store.js'
  import { KEYS, KEY_BY_HID } from './layout.js'
  import { DOM_CODE_TO_HID } from './keycodes.js'

  const LETTERS = KEYS.filter(k => k.hid >= 0x04 && k.hid <= 0x1D)
  const PALETTE = ['#f0404e', '#3bcb6b', '#3d6bf0', '#f2c230', '#ee5bc4', '#33cfe0']
  let game = null         // 'simon' | 'reaction' | 'typing'
  let colors = Array(108).fill('#000000')
  let message = ''
  const best = JSON.parse(localStorage.getItem('ak820:best') ?? '{}')
  const saveBest = () => localStorage.setItem('ak820:best', JSON.stringify(best))
  let timers = []
  const later = (fn, ms) => timers.push(setTimeout(fn, ms))
  const clearTimers = () => { timers.forEach(clearTimeout); timers = [] }

  function show(map, fill = '#000000') {
    colors = Array(108).fill(fill)
    for (const [led, c] of Object.entries(map)) colors[led] = c
    api('preview_frame', colors).catch(e => toast(e.message, 'bad'))
  }

  async function stop() {
    clearTimers(); game = null; message = ''
    colors = Array(108).fill('#000000')
    try { await api('restore_lighting') } catch {}
  }
  onDestroy(stop)

  // ── Simon ────────────────────────────────────────────────────────────
  const SIMON = ['Q', 'W', 'E', 'A', 'S', 'D'].map(id => KEYS.find(k => k.id === id))
  let seq = [], pos = 0, accepting = false
  function simon() { stop().then(() => { game = 'simon'; seq = []; nextRound() }) }
  function nextRound() {
    seq = [...seq, Math.floor(Math.random() * SIMON.length)]; pos = 0; accepting = false
    message = `Watch: round ${seq.length}`
    show(Object.fromEntries(SIMON.map((k, i) => [k.led, dim(PALETTE[i])])))
    seq.forEach((n, i) => {
      later(() => show({ ...Object.fromEntries(SIMON.map((k, j) => [k.led, dim(PALETTE[j])])), [SIMON[n].led]: PALETTE[n] }), 600 + i * 650)
      later(() => show(Object.fromEntries(SIMON.map((k, j) => [k.led, dim(PALETTE[j])]))), 1050 + i * 650)
    })
    later(() => { accepting = true; message = 'Your turn: repeat it on Q W E A S D' }, 700 + seq.length * 650)
  }
  const dim = c => '#' + [1, 3, 5].map(i => Math.round(parseInt(c.slice(i, i + 2), 16) * 0.18).toString(16).padStart(2, '0')).join('')
  function simonKey(hid) {
    if (!accepting) return
    const n = SIMON.findIndex(k => k.hid === hid)
    if (n < 0) return
    if (n !== seq[pos]) {
      accepting = false
      const score = seq.length - 1
      if (score > (best.simon ?? 0)) { best.simon = score; saveBest() }
      message = `Missed it. You remembered ${score} step${score === 1 ? '' : 's'}.`
      show(Object.fromEntries(KEYS.map(k => [k.led, '#5a0a12'])))
      return
    }
    show({ ...Object.fromEntries(SIMON.map((k, j) => [k.led, dim(PALETTE[j])])), [SIMON[n].led]: PALETTE[n] })
    if (++pos === seq.length) { accepting = false; message = 'Nice.'; later(nextRound, 700) }
  }

  // ── Reaction ─────────────────────────────────────────────────────────
  let target = null, litAt = 0, times = []
  function reaction() { stop().then(() => { game = 'reaction'; times = []; armReaction() }) }
  function armReaction() {
    target = null; message = 'Wait for a key to light up…'
    show({})
    later(() => { target = LETTERS[Math.floor(Math.random() * LETTERS.length)]; litAt = performance.now(); message = `Press ${target.label}!`; show({ [target.led]: '#33cfe0' }) }, 1200 + Math.random() * 2500)
  }
  function reactionKey(hid) {
    if (!target) { message = 'Too early. Wait for the light.'; clearTimers(); later(armReaction, 900); return }
    if (hid !== target.hid) return
    const ms = Math.round(performance.now() - litAt); times = [...times, ms]; target = null
    if (!best.reaction || ms < best.reaction) { best.reaction = ms; saveBest() }
    message = `${ms} ms`
    if (times.length >= 5) { message = `Average ${Math.round(times.reduce((a, b) => a + b) / times.length)} ms over 5 tries`; show(Object.fromEntries(KEYS.map(k => [k.led, '#123a2a']))); return }
    later(armReaction, 800)
  }

  // ── Typing ───────────────────────────────────────────────────────────
  const WORDS = 'light quick keyboard silver violet ripple studio layer macro profile focus amber frost wave signal orbit pixel lumen'.split(' ')
  let text = '', idx = 0, started = 0, errors = 0
  function typing() { stop().then(() => { game = 'typing'; text = Array.from({ length: 8 }, () => WORDS[Math.floor(Math.random() * WORDS.length)]).join(' '); idx = 0; errors = 0; started = 0; lightNext() }) }
  function lightNext() {
    if (idx >= text.length) {
      const min = (performance.now() - started) / 60000, wpm = Math.round(text.length / 5 / min)
      if (!best.wpm || wpm > best.wpm) { best.wpm = wpm; saveBest() }
      message = `${wpm} words a minute, ${errors} mistake${errors === 1 ? '' : 's'}`
      show(Object.fromEntries(KEYS.map(k => [k.led, '#1b2a55']))); return
    }
    const ch = text[idx], k = ch === ' ' ? KEY_BY_HID[0x2C] : KEYS.find(x => x.label.toLowerCase() === ch)
    show(k ? { [k.led]: '#f2c230' } : {})
  }
  function typingKey(hid) {
    if (idx >= text.length) return
    if (!started) started = performance.now()
    const ch = text[idx], want = ch === ' ' ? 0x2C : KEYS.find(x => x.label.toLowerCase() === ch)?.hid
    if (hid === want) { idx++; lightNext() } else errors++
  }

  function onKey(e) {
    if (!game) return
    const hid = DOM_CODE_TO_HID[e.code]
    if (hid == null || e.repeat) return
    e.preventDefault()
    if (game === 'simon') simonKey(hid)
    else if (game === 'reaction') reactionKey(hid)
    else typingKey(hid)
  }

  const GAMES = [
    { id: 'simon', name: 'Light memory', icon: Brain, start: simon, about: 'Watch the keys flash, then play the pattern back. One more step every round.', best: () => best.simon != null ? `Best: ${best.simon} steps` : '' },
    { id: 'reaction', name: 'Reaction time', icon: Timer, start: reaction, about: 'A random letter lights up after a pause. Press it as fast as you can, five times.', best: () => best.reaction ? `Best: ${best.reaction} ms` : '' },
    { id: 'typing', name: 'Follow the light', icon: Type, start: typing, about: 'Type the sentence by following the lit key. Great for learning to type without looking.', best: () => best.wpm ? `Best: ${best.wpm} wpm` : '' },
  ]
</script>

<svelte:window on:keydown={onKey} />

<section class="px-7 pt-6 pb-10 max-w-[1180px]">
  <KeyboardStage {colors} compact />

  {#if game}
    <div class="mt-6 flex items-center gap-6">
      <div class="font-display text-[22px] font-semibold min-h-[32px]" aria-live="polite">{message}</div>
      {#if game === 'typing'}
        <div class="font-cap text-[18px] tracking-wide">
          <span class="text-ink-faint">{text.slice(0, idx)}</span><span class="text-lav underline underline-offset-4">{text[idx] ?? ''}</span><span>{text.slice(idx + 1)}</span>
        </div>
      {/if}
      <div class="ml-auto flex gap-2">
        <button class="btn-line" on:click={() => GAMES.find(g => g.id === game).start()}>Restart</button>
        <button class="btn-quiet" on:click={stop}>Stop and restore lighting</button>
      </div>
    </div>
    <p class="text-[12px] text-ink-mute mt-2">Keep this window in front while you play.</p>
  {:else}
    <div class="grid grid-cols-3 gap-4 mt-6">
      {#each GAMES as g}
        <button class="text-left rounded-2xl border border-rule bg-card p-5 hover:border-lav transition-colors" on:click={g.start}>
          <svelte:component this={g.icon} size={22} class="text-lav mb-3" />
          <div class="text-[15px] font-semibold mb-1">{g.name}</div>
          <p class="text-[12.5px] text-ink-mute leading-relaxed">{g.about}</p>
          {#if g.best()}<div class="mt-3 text-[12px] text-ink-soft flex items-center gap-1.5"><Trophy size={13} class="text-warn" />{g.best()}</div>{/if}
        </button>
      {/each}
    </div>
  {/if}
</section>
