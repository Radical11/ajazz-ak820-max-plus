# AK820 Studio

A light, fast replacement for the official AJAZZ software for the AJAZZ AK820 Max Plus, as a small Windows app (Tauri) or a web page (WebHID). The keyboard's USB HID protocol was reverse-engineered from the official app; see [PROTOCOL.md](PROTOCOL.md).

## Features

- **Lighting**: 19 on-board effects, 14 app-drawn effects (including typing-reactive ripples, trails and fireworks, and gradient/breathing effects in your own colours), per-key painting saved to the keyboard, music (system audio) and screen-ambient lighting, typing heat, CPU/RAM monitor, layers (Caps Lock, highlight keys, game-mode keys, focus timer), a live LED preview, and a schedule for night dimming and lights-off when you're away.
- **Keys**: remap the base and Fn layers to keys, media and app keys, shortcuts or macros, or disable them. Undo, a changed-keys list, and the shortcut lens: hold Ctrl, Alt or Win to light the keys that do something in the current app.
- **Macros**: record with timing, edit steps, up to 27 steps stored on the keyboard.
- **Profiles**: unlimited, import and export, switch automatically per app or from the tray.
- **Device**: response time, sleep timer, F-row mode, game mode (blocks Win, Alt+Tab, Alt+F4), key tester with chatter detection, battery and firmware, opt-in typing stats, light and dark themes.
- **Play**: memory, reaction-time and typing games on the keyboard lights.
- Ctrl+K opens quick actions; Ctrl+1 to Ctrl+6 switch pages.

## Desktop app

Download the installer from the releases, or build it:

```
cd ui && npm install && cd ..
ui\node_modules\.bin\tauri build      # installer in src-tauri\target\release\bundle\nsis
```

Building needs Node.js 18+, the Rust toolchain (rustup) and the Visual Studio C++ build tools. The app uses the WebView2 runtime that ships with Windows 11.

## Web version

The same UI runs in Chrome or Edge with no install:

```
cd ui
npm run build
npm run preview        # open http://localhost:4173 and click "Connect keyboard"
```

Host `ui/dist` on any HTTPS site to share it. Game mode, per-app profiles, the shortcut lens, typing stats, system-wide key capture and lights-off when away need the desktop app, because a browser tab can't see what you do in other apps.

## Project structure

```
src-tauri/src/main.rs      App shell: tray, autostart, file dialogs, CPU/RAM
src-tauri/src/hid.rs       HID transport (vendor interface 0xFF02)
src-tauri/src/winsys.rs    Global key hook, foreground app, screen sampling, idle time, Caps Lock
src-tauri/src/audio.rs     System audio / microphone spectrum (WASAPI)
ui/src/lib/core/           Protocol, effects, lens tables, web and desktop backends
ui/src/lib/*.svelte        Pages and components
ui/src/lib/layout.js       Key layout, generated from the vendor layout file
ui/tests/                  Protocol tests (npm test), byte-exact against captured packets
PROTOCOL.md                USB HID protocol specification
```

## Notes

- Close the official AJAZZ app and turn off its Auto Run, so the two don't fight over the keyboard.
- The keyboard stores remaps, macros and device settings itself, so they work without the app. App-drawn and live lighting need AK820 Studio running.
- Works over the USB cable (1A2C:A036) and the 2.4 GHz dongle (1A2C:8FFF).
- AK820 Studio never writes firmware.
