<script>
  import { onMount } from 'svelte'
  import { Lightbulb, Keyboard, Repeat, Layers, SlidersHorizontal, Usb, Wifi, Unplug, Command, Gamepad } from 'lucide-svelte'
  import { ready, page, status, profile, profiles, toasts, paletteOpen, meta, loadState, waitForBackend, run } from './lib/store.js'
  import GamesPage from './lib/GamesPage.svelte'
  import LightingPage from './lib/LightingPage.svelte'
  import KeysPage from './lib/KeysPage.svelte'
  import MacrosPage from './lib/MacrosPage.svelte'
  import ProfilesPage from './lib/ProfilesPage.svelte'
  import DevicePage from './lib/DevicePage.svelte'
  import CommandPalette from './lib/CommandPalette.svelte'

  const NAV = [
    { id: 'lighting', label: 'Lighting', icon: Lightbulb, hint: 'Effects, per-key colour and live studio modes' },
    { id: 'keys',     label: 'Keys',     icon: Keyboard,  hint: 'Remap keys on the base and Fn layers' },
    { id: 'macros',   label: 'Macros',   icon: Repeat,    hint: 'Record and edit key sequences' },
    { id: 'profiles', label: 'Profiles', icon: Layers,    hint: 'Switch setups, link them to apps' },
    { id: 'device',   label: 'Device',   icon: SlidersHorizontal, hint: 'Sleep, response time, game mode, key test' },
    { id: 'play',     label: 'Play',     icon: Gamepad,   hint: 'Games played on the keyboard lights' },
  ]
  let failed = ''

  onMount(async () => {
    await waitForBackend()
    try { await loadState() } catch (e) { failed = e.message }
  })

  function onKey(e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); paletteOpen.update(v => !v) }
    if (e.ctrlKey && /^[1-6]$/.test(e.key)) { e.preventDefault(); page.set(NAV[+e.key - 1].id) }
  }

  $: conn = $status.connected ? ($status.connection === 'wireless' ? 'Wireless' : 'Wired') : 'Not connected'
</script>

<svelte:window on:keydown={onKey} />

<div class="h-full flex">
  <!-- rail -->
  <nav class="w-[212px] shrink-0 flex flex-col px-3 pt-5 pb-4 border-r border-rule bg-sheet/60" aria-label="Sections">
    <div class="px-2.5 mb-7">
      <div class="font-display text-[19px] font-semibold leading-none">AK820 Studio</div>
      <div class="text-[12px] text-ink-mute mt-1.5">AJAZZ AK820 Max Plus</div>
    </div>

    <ul class="flex flex-col gap-0.5">
      {#each NAV as n, i}
        <li>
          <button
            class="w-full flex items-center gap-3 h-9 px-2.5 rounded-lg text-[13.5px] transition-colors
                   {$page === n.id ? 'bg-card text-ink font-semibold shadow-sm' : 'text-ink-soft hover:bg-ink/[0.05]'}"
            aria-current={$page === n.id ? 'page' : undefined}
            title="{n.hint} (Ctrl+{i + 1})"
            on:click={() => page.set(n.id)}
          >
            <svelte:component this={n.icon} size={17} strokeWidth={$page === n.id ? 2.2 : 1.8}
              class={$page === n.id ? 'text-lav' : ''} />
            {n.label}
          </button>
        </li>
      {/each}
    </ul>

    <div class="mt-auto flex flex-col gap-3 px-1">
      <button class="flex items-center justify-between h-8 px-2.5 rounded-lg border border-rule bg-card text-[12.5px] text-ink-mute hover:border-ink-faint"
              on:click={() => paletteOpen.set(true)}>
        <span class="flex items-center gap-2"><Command size={14} /> Quick actions</span>
        <kbd class="text-[11px] text-ink-faint">Ctrl K</kbd>
      </button>

      <div class="rounded-xl px-3 py-2.5 bg-card border border-rule">
        <div class="flex items-center gap-2 text-[12.5px] font-medium">
          {#if $status.connected}
            <span class="relative flex h-2 w-2"><span class="absolute inline-flex h-full w-full rounded-full bg-ok opacity-40 animate-ping"></span><span class="relative h-2 w-2 rounded-full bg-ok"></span></span>
            {#if $status.connection === 'wireless'}<Wifi size={14} class="text-ink-mute" />{:else}<Usb size={14} class="text-ink-mute" />{/if}
          {:else}
            <Unplug size={14} class="text-bad" />
          {/if}
          {conn}
        </div>
        {#if $status.connected && $status.battery != null}
          <div class="flex items-center gap-2 mt-2" title="Battery level reported by the keyboard{$status.connection === 'wired' ? ' (charging over USB)' : ''}">
            <span class="relative w-7 h-3.5 rounded-[3px] border border-ink-faint p-[1.5px]">
              <span class="block h-full rounded-[1px] {$status.battery <= 15 ? 'bg-bad' : 'bg-ok'}" style="width:{$status.battery}%"></span>
            </span>
            <span class="text-[12px] text-ink-soft">{$status.battery}%{$status.connection === 'wired' ? ', charging' : ''}</span>
          </div>
        {/if}
        {#if $status.connected && $status.firmware}
          <div class="text-[11.5px] text-ink-faint mt-1">Firmware {$status.firmware}</div>
        {/if}
        {#if !$status.connected && $meta.web}
          {#if $meta.hid_supported}
            <button class="btn-primary w-full mt-2" on:click={() => run('connect_device', [], { success: 'Keyboard connected' })}>Connect keyboard</button>
          {:else}
            <p class="text-[11.5px] text-ink-mute mt-1 leading-snug">Open this page in Chrome or Edge to connect the keyboard.</p>
          {/if}
        {/if}
        {#if !$status.connected && $status.error}
          <p class="text-[11.5px] text-ink-mute mt-1 leading-snug">{$status.error}</p>
        {/if}
      </div>
    </div>
  </nav>

  <!-- main -->
  <main class="flex-1 min-w-0 flex flex-col">
    <header class="h-14 shrink-0 flex items-center justify-between px-7 border-b border-rule">
      <h1 class="text-[17px] font-semibold">{NAV.find(n => n.id === $page)?.label}</h1>
      {#if $profile}
        <label class="flex items-center gap-2.5 text-[12.5px] text-ink-mute">
          Profile
          <select class="field pr-7 font-medium text-ink min-w-[160px]"
                  value={$profile.id}
                  on:change={e => run('activate_profile', [e.currentTarget.value])}>
            {#each $profiles as p}<option value={p.id}>{p.name}</option>{/each}
          </select>
          {#if $status.auto_profile}<span class="chip bg-lav-wash text-lav-deep" title="Switched automatically for {$status.foreground}">Auto</span>{/if}
        </label>
      {/if}
    </header>

    <div class="flex-1 overflow-y-auto">
      {#if failed}
        <div class="p-10 max-w-lg">
          <h2 class="text-lg font-semibold mb-2">The backend didn't start</h2>
          <p class="text-ink-mute">{failed}. Close AK820 Studio and open it again.</p>
        </div>
      {:else if !$ready}
        <div class="p-10 text-ink-mute">Starting…</div>
      {:else if $page === 'lighting'}<LightingPage />
      {:else if $page === 'keys'}<KeysPage />
      {:else if $page === 'macros'}<MacrosPage />
      {:else if $page === 'profiles'}<ProfilesPage />
      {:else if $page === 'device'}<DevicePage />
      {:else}<GamesPage />{/if}
    </div>
  </main>
</div>

{#if $paletteOpen}<CommandPalette />{/if}

<div class="fixed bottom-5 right-5 flex flex-col gap-2 z-50" aria-live="polite">
  {#each $toasts as t (t.id)}
    <div class="max-w-sm rounded-xl px-4 py-2.5 text-[13px] shadow-lift border bg-card
                {t.kind === 'bad' ? 'border-bad/30 text-bad' : t.kind === 'warn' ? 'border-warn/30 text-ink' : t.kind === 'ok' ? 'border-ok/30 text-ink' : 'border-rule text-ink'}">
      {t.message}
    </div>
  {/each}
</div>
