<script>
  import { onDestroy } from 'svelte'
  import { Gamepad2, Timer, Zap, Activity, Power } from 'lucide-svelte'
  import KeyboardStage from './KeyboardStage.svelte'
  import { profile, settings, meta, pressed, run, api, toast } from './store.js'
  import { KEY_BY_HID } from './layout.js'
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
                        {+d.response === +v ? 'border-lav bg-lav-wash' : 'border-rule bg-white hover:border-ink-faint'}">
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

  <div>
    <h2 class="text-[14px] font-semibold flex items-center gap-2 mb-1"><Gamepad2 size={16} class="text-lav" /> Game mode</h2>
    <p class="text-[12.5px] text-ink-mute mb-3">Block keys that throw you out of a game. Saved with the profile, so link a game to it on the Profiles page to turn this on automatically.</p>
    <div class="flex gap-3">
      {#each [['win', 'Windows key'], ['alt_tab', 'Alt + Tab'], ['alt_f4', 'Alt + F4']] as [k, n]}
        <button class="h-10 px-4 rounded-lg border text-[13px] flex items-center gap-2.5
                       {gm[k] ? 'border-lav bg-lav-wash text-lav-deep font-semibold' : 'border-rule bg-white hover:border-ink-faint'}"
                aria-pressed={gm[k]} on:click={() => setGame({ [k]: !gm[k] })}>
          <span class="w-8 h-[18px] rounded-full relative transition-colors {gm[k] ? 'bg-lav' : 'bg-ink/15'}">
            <span class="absolute top-[2px] w-[14px] h-[14px] rounded-full bg-white shadow transition-all {gm[k] ? 'left-[16px]' : 'left-[2px]'}"></span>
          </span>
          Block {n}
        </button>
      {/each}
    </div>
  </div>

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

  <div class="grid grid-cols-2 gap-10">
    <div>
      <h2 class="text-[14px] font-semibold flex items-center gap-2 mb-3"><Power size={16} class="text-lav" /> App</h2>
      <div class="flex flex-col gap-2.5 text-[13px]">
        <label class="flex items-center gap-2.5"><input type="checkbox" class="accent-lav w-4 h-4" checked={$settings.launch_at_login} on:change={e => setApp({ launch_at_login: e.currentTarget.checked })} /> Start with Windows</label>
        <label class="flex items-center gap-2.5"><input type="checkbox" class="accent-lav w-4 h-4" checked={$settings.start_minimized} on:change={e => setApp({ start_minimized: e.currentTarget.checked })} /> Start hidden in the tray</label>
        <label class="flex items-center gap-2.5"><input type="checkbox" class="accent-lav w-4 h-4" checked={$settings.close_to_tray} on:change={e => setApp({ close_to_tray: e.currentTarget.checked })} /> Keep running in the tray when the window closes</label>
      </div>
      <p class="text-[12px] text-ink-mute mt-3">Close the official AJAZZ app and turn off its Auto Run so the two don't fight over the keyboard.</p>
    </div>
    <div>
      <h2 class="text-[14px] font-semibold mb-1">Restore keys</h2>
      <p class="text-[12.5px] text-ink-mute mb-3">Puts every key back to its factory function on the keyboard. Lighting and your saved profiles aren't touched.</p>
      <button class="btn-danger border border-bad/30" on:click={resetKeyboardKeys}>Restore factory key functions</button>
    </div>
  </div>
</section>
