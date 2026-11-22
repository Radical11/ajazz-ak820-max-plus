<script>
  import { Plus, Download, Upload, Trash2, Check, X, AppWindow } from 'lucide-svelte'
  import { profiles, profile, settings, status, meta, run, api, toast } from './store.js'

  let sel = $profile?.id
  $: P = $profiles.find(p => p.id === sel) ?? $profiles[0]
  let newName = ''
  let creating = false
  let appInput = ''
  let running = []

  async function create() {
    const r = await run('create_profile', [newName.trim() || 'New profile', $profile?.id], { success: 'Profile created' })
    sel = r.profile.id; newName = ''; creating = false
  }
  async function rename(name) { if (name.trim() && name !== P.name) await run('update_profile_meta', [P.id, name, null]) }
  async function setApps(apps) { await run('update_profile_meta', [P.id, null, apps]) }
  function addApp(name) {
    name = name.trim().toLowerCase()
    if (!name) return
    if (!name.endsWith('.exe')) name += '.exe'
    if (!P.apps.includes(name)) setApps([...P.apps, name])
    appInput = ''
  }
  async function loadRunning() { try { running = (await api('running_apps')).apps } catch {} }
  loadRunning()

  async function exportIt() {
    const r = await run('export_profile_file', [P.id])
    if (r.path) toast('Profile exported', 'ok')
  }
  async function importIt() {
    const r = await run('import_profile_file', [])
    if (r.profile) sel = r.profile.id
  }
  async function del() { await run('delete_profile', [P.id], { success: `Deleted “${P.name}”` }); sel = 'default' }

  function summary(p) {
    const keys = Object.keys(p.keymap['1']).length + Object.keys(p.keymap['2']).length
    const L = p.lighting
    const light = L.kind === 'custom' ? 'Per-key colour' : L.kind === 'studio' ? ({ audio: 'Music', heatmap: 'Typing heat', sysmon: 'System monitor', effect: 'App effect' })[L.engine] : 'Keyboard effect'
    return `${light}, ${keys ? keys + ' remapped key' + (keys > 1 ? 's' : '') : 'no remaps'}`
  }
</script>

<section class="px-7 pt-6 pb-10 grid grid-cols-[300px_1fr] gap-10 max-w-[1100px]">
  <div>
    <div class="flex gap-2 mb-4">
      <button class="btn-primary" on:click={() => (creating = true)}><Plus size={15} /> New</button>
      <button class="btn-line" on:click={importIt}><Upload size={14} /> Import</button>
    </div>
    {#if creating}
      <form class="flex gap-2 mb-3" on:submit|preventDefault={create}>
        <!-- svelte-ignore a11y-autofocus -->
        <input class="field flex-1" placeholder="Profile name" bind:value={newName} autofocus />
        <button class="btn-primary px-2" aria-label="Create"><Check size={15} /></button>
        <button type="button" class="btn-quiet px-2" aria-label="Cancel" on:click={() => (creating = false)}><X size={15} /></button>
      </form>
      <p class="text-[12px] text-ink-mute -mt-1 mb-3">Starts as a copy of “{$profile?.name}”.</p>
    {/if}
    <ul class="flex flex-col gap-1">
      {#each $profiles as p}
        <li>
          <button class="w-full rounded-xl px-3.5 py-2.5 text-left transition-colors
                         {P?.id === p.id ? 'bg-card shadow-sm' : 'hover:bg-ink/[0.05]'}"
                  on:click={() => (sel = p.id)}>
            <div class="flex items-center justify-between">
              <span class="text-[13.5px] font-semibold">{p.name}</span>
              {#if $profile?.id === p.id}<span class="chip bg-ok/10 text-ok">Active</span>{/if}
            </div>
            <div class="text-[12px] text-ink-mute mt-0.5">{summary(p)}</div>
          </button>
        </li>
      {/each}
    </ul>
  </div>

  {#if P}
    <div class="flex flex-col gap-8">
      <div class="flex items-center gap-3">
        <input class="field text-[16px] font-semibold h-10 w-[320px]" value={P.name} aria-label="Profile name"
               on:change={e => rename(e.currentTarget.value)} />
        {#if $profile?.id !== P.id}
          <button class="btn-primary h-10" on:click={() => run('activate_profile', [P.id], { success: `Using ${P.name}` })}>Use this profile</button>
        {/if}
        <button class="btn-quiet h-10" on:click={exportIt}><Download size={15} /> Export</button>
        {#if P.id !== 'default'}<button class="btn-danger h-10" on:click={del}><Trash2 size={15} /> Delete</button>{/if}
      </div>

      {#if $meta.web}
        <p class="text-[12.5px] text-ink-mute max-w-[560px]">Switching profiles automatically per app needs the desktop app; the browser can't see which app you're using.</p>
      {:else}
      <div>
        <h2 class="text-[14px] font-semibold mb-1">Switch automatically</h2>
        <p class="text-[12.5px] text-ink-mute mb-3 max-w-[560px]">
          When one of these apps is in front, this profile turns on. Switching back to anything else returns to the profile you picked yourself.
        </p>
        <div class="flex flex-wrap gap-2 mb-3">
          {#each P.apps as a}
            <span class="chip h-7 bg-card border border-rule text-ink"><AppWindow size={13} class="text-ink-mute" />{a}
              <button class="ml-1 text-ink-faint hover:text-bad" aria-label="Remove {a}" on:click={() => setApps(P.apps.filter(x => x !== a))}><X size={13} /></button></span>
          {:else}
            <span class="text-[12.5px] text-ink-faint">No apps linked.</span>
          {/each}
        </div>
        <form class="flex gap-2 max-w-[460px]" on:submit|preventDefault={() => addApp(appInput)}>
          <input class="field flex-1" list="running-apps" placeholder="App, e.g. valorant.exe" bind:value={appInput} on:focus={loadRunning} />
          <datalist id="running-apps">{#each running as a}<option value={a} />{/each}</datalist>
          <button class="btn-line">Link app</button>
        </form>
        <label class="flex items-center gap-2.5 mt-4 text-[13px]">
          <input type="checkbox" class="accent-lav w-4 h-4" checked={$settings.auto_switch}
                 on:change={e => run('update_settings', [{ auto_switch: e.currentTarget.checked }]).then(r => settings.set(r.settings))} />
          Automatic switching is {$settings.auto_switch ? 'on' : 'off'} for all profiles
        </label>
        {#if $status.foreground}<p class="text-[12px] text-ink-faint mt-2">Last app in front: {$status.foreground}</p>{/if}
      </div>
      {/if}

      <div class="text-[12.5px] text-ink-mute max-w-[560px] leading-relaxed">
        A profile holds lighting, key remaps on both layers, sleep and response settings, and game mode. Edit them on the other pages while the profile is active; changes save as you make them.
      </div>
    </div>
  {/if}
</section>
