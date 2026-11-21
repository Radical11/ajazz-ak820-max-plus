<script>
  import { onMount } from 'svelte'
  import { Search } from 'lucide-svelte'
  import { paletteOpen, page, profiles, modes, run } from './store.js'

  let q = ''
  let i = 0
  let input

  $: actions = [
    ...$profiles.map(p => ({ label: `Use profile: ${p.name}`, go: () => run('activate_profile', [p.id], { success: `Using ${p.name}` }) })),
    ...$modes.filter(m => !m.software).map(m => ({ label: `Effect: ${m.name}`, go: () => run('set_lighting', [{ kind: 'hardware', mode: m.id, brightness: 4, speed: 2, direction: 0, color: 'rgb' }]) })),
    { label: 'Lights off', go: () => run('turn_off', [], { success: 'Lights off' }) },
    { label: 'Start music lighting', go: () => run('set_lighting', [{ kind: 'studio', engine: 'audio', config: { mode: 'spectrum' } }]) },
    { label: 'Start typing heat', go: () => run('set_lighting', [{ kind: 'studio', engine: 'heatmap', config: {} }]) },
    { label: 'Start system monitor', go: () => run('set_lighting', [{ kind: 'studio', engine: 'sysmon', config: {} }]) },
    { label: 'Game mode on (block Windows key, Alt+Tab)', go: () => run('set_game_mode', [true, true, false], { success: 'Game mode on' }) },
    { label: 'Game mode off', go: () => run('set_game_mode', [false, false, false], { success: 'Game mode off' }) },
    { label: 'Reconnect keyboard', go: () => run('reconnect', [], { success: 'Keyboard connected' }) },
    ...['lighting', 'keys', 'macros', 'profiles', 'device'].map(p => ({ label: `Go to ${p[0].toUpperCase() + p.slice(1)}`, go: () => page.set(p) })),
  ]
  $: results = actions.filter(a => a.label.toLowerCase().includes(q.toLowerCase())).slice(0, 9)
  $: if (i >= results.length) i = Math.max(0, results.length - 1)

  function choose(a) { paletteOpen.set(false); a?.go()?.catch?.(() => {}) }
  function key(e) {
    if (e.key === 'Escape') paletteOpen.set(false)
    else if (e.key === 'ArrowDown') { e.preventDefault(); i = (i + 1) % results.length }
    else if (e.key === 'ArrowUp') { e.preventDefault(); i = (i - 1 + results.length) % results.length }
    else if (e.key === 'Enter') choose(results[i])
  }
  onMount(() => input.focus())
</script>

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="fixed inset-0 z-40 bg-ink/25 flex items-start justify-center pt-[14vh]" on:click|self={() => paletteOpen.set(false)}>
  <div class="w-[560px] rounded-2xl bg-white shadow-lift border border-rule overflow-hidden" role="dialog" aria-label="Quick actions">
    <div class="flex items-center gap-3 px-4 h-12 border-b border-rule">
      <Search size={16} class="text-ink-mute" />
      <input bind:this={input} bind:value={q} on:keydown={key} class="flex-1 outline-none text-[14px] bg-transparent" placeholder="Switch profile, change effect, go to a page…" />
    </div>
    <ul class="py-1.5 max-h-[360px] overflow-y-auto" role="listbox">
      {#each results as a, n}
        <li role="option" aria-selected={n === i}>
          <button class="w-full text-left px-4 h-9 text-[13.5px] {n === i ? 'bg-lav-wash text-lav-deep' : 'text-ink'}"
                  on:mouseenter={() => (i = n)} on:click={() => choose(a)}>{a.label}</button>
        </li>
      {:else}
        <li class="px-4 h-9 flex items-center text-[13px] text-ink-mute">Nothing matches “{q}”.</li>
      {/each}
    </ul>
  </div>
</div>
