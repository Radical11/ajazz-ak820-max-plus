# AK820 Studio

AK820 Studio is a lighter replacement for the official AJAZZ software for the AJAZZ AK820 Max Plus keyboard on Windows. The USB HID protocol was reverse-engineered from the keyboard; see [PROTOCOL.md](PROTOCOL.md) for the full specification.

## Features

- **Lighting**: 19 on-board effects and 6 effects drawn by the app. Per-key painting is saved to the keyboard. Live music, typing-heat, and system-monitor lighting run while the app is open.
- **Keys**: remap the base and Fn layers, assign media and app keys, shortcuts, or macros, and disable keys.
- **Macros**: record with timing, edit steps, and store up to 27 steps on the keyboard.
- **Profiles**: unlimited profiles with import and export. Profiles can switch automatically per app or from the tray.
- **Device**: response time, sleep timer, F-row mode, game mode (blocks Win, Alt+Tab, and Alt+F4), and a key tester with chatter detection.
- **Navigation**: Ctrl+K opens quick actions; Ctrl+1 to Ctrl+5 switch pages.

## Requirements

- Windows 10 or 11
- Python 3.11+
- Node.js 18+
- Microsoft Edge WebView2 runtime (preinstalled on Windows 11)

## Install

Run `install.bat`. It creates a virtual environment, installs the Python packages, and builds the UI. Run it again after updating the project.

## Run

```
run.bat            start in the background (tray icon, no console window)
run.bat --minimized  start hidden in the tray
run.bat --debug    run with a console and the web inspector enabled
```

## Desktop app (Tauri)

The recommended desktop build is a small native app: the same Svelte UI in Windows' built-in WebView2, with a Rust backend for HID, the global key hook, foreground-app tracking, system audio, screen sampling and the tray.

```
cd ui && npm install && cd ..
npm --prefix ui exec tauri build -- --config src-tauri/tauri.conf.json   # installer in src-tauri/target/release/bundle/nsis
```

Needs the Rust toolchain (rustup) and Visual Studio C++ build tools. The Python app (`run.bat`) still works and uses the same UI.

## Web version

The same UI also runs in Chrome or Edge with no install, talking to the keyboard over WebHID:

```
cd ui
npm run build
npm run preview        # open http://localhost:4173 and click "Connect keyboard"
```

Host `ui/dist` on any HTTPS site to share it. In the browser you get key remaps, macros, sleep and response settings, built-in and app-drawn effects, per-key painting, music and screen lighting (via the share prompt), layers, profiles and the games. Game mode, per-app profile switching, the shortcut lens, typing stats and system-wide key capture need the desktop app, because browsers can't see keys pressed in other apps.

## Data location

Profiles, macros, and settings are stored in `%APPDATA%\AK820Studio`.

## Project structure

```
app/protocol.py       Packet construction
app/keyboard.py       HID transport
app/api.py            UI bridge (pywebview JS API)
app/profiles.py       Profile storage and switching
app/winhooks.py       Global key hook
app/appwatch.py       Foreground app detection
app/audio.py          Audio capture and FFT for music lighting
app/heatmap.py        Typing-heat lighting
app/sysmon.py         System-monitor lighting
app/custom_effects.py App-drawn lighting effects
app/tray.py           System tray icon
app/layout.py         Keyboard layout helpers
app/storage.py        Data directory handling
ui/src/lib/*.svelte   UI pages and components
ui/src/lib/layout.js  Key layout, generated from the vendor layout
main.py               Entry point
PROTOCOL.md           USB HID protocol specification
```

## Notes

- Close the official AJAZZ app and turn off its Auto Run setting. Both apps talking to the keyboard can cause conflicts.
- The keyboard stores key remaps, macros, and settings itself, so they keep working without the app. App-drawn and live lighting need AK820 Studio running.
- The 2.4 GHz dongle (1A2C:8FFF) uses the same protocol but has not been tested.
