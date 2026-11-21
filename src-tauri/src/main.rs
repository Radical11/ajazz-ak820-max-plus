// AK820 Studio desktop shell (Tauri 2).
// The UI and all keyboard logic live in the Svelte app; Rust provides the parts
// a browser can't: HID access, the global key hook, foreground-app tracking,
// system audio, screen sampling, CPU/RAM stats, files, autostart and the tray.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod audio;
mod hid;
mod winsys;

use serde_json::json;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use sysinfo::System;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, WindowEvent};

static CLOSE_TO_TRAY: AtomicBool = AtomicBool::new(true);

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

#[tauri::command]
fn set_close_to_tray(on: bool) {
    CLOSE_TO_TRAY.store(on, Ordering::Relaxed);
}

#[tauri::command]
fn sysmon(state: tauri::State<'_, Mutex<System>>) -> serde_json::Value {
    let mut s = state.lock().unwrap();
    s.refresh_cpu_usage();
    s.refresh_memory();
    let mem = if s.total_memory() > 0 { s.used_memory() as f64 / s.total_memory() as f64 * 100.0 } else { 0.0 };
    json!({ "cpu": s.global_cpu_usage().round(), "mem": mem.round(), "gpu": 0 })
}

#[tauri::command]
fn foreground() -> String {
    winsys::foreground_exe()
}

#[tauri::command]
fn export_file(name: String, content: String) -> Result<Option<String>, String> {
    let Some(path) = rfd::FileDialog::new().set_file_name(&name).add_filter("AK820 profile", &["json"]).save_file() else { return Ok(None) };
    std::fs::write(&path, content).map_err(|e| e.to_string())?;
    Ok(Some(path.display().to_string()))
}

#[tauri::command]
fn import_file() -> Result<Option<String>, String> {
    let Some(path) = rfd::FileDialog::new().add_filter("AK820 profile", &["json"]).pick_file() else { return Ok(None) };
    std::fs::read_to_string(path).map(Some).map_err(|e| e.to_string())
}

#[tauri::command]
fn set_autostart(on: bool) -> Result<(), String> {
    use winreg::enums::*;
    let run = winreg::RegKey::predef(HKEY_CURRENT_USER)
        .open_subkey_with_flags(r"Software\Microsoft\Windows\CurrentVersion\Run", KEY_SET_VALUE)
        .map_err(|e| e.to_string())?;
    if on {
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        run.set_value("AK820Studio", &format!("\"{}\" --minimized", exe.display())).map_err(|e| e.to_string())
    } else {
        let _ = run.delete_value("AK820Studio");
        Ok(())
    }
}

/// Profiles, macros and settings saved by the earlier Python app (%APPDATA%\AK820Studio), for a one-time import.
#[tauri::command]
fn legacy_data() -> serde_json::Value {
    let Some(root) = std::env::var_os("APPDATA").map(|a| std::path::PathBuf::from(a).join("AK820Studio")) else { return json!(null) };
    let read = |p: std::path::PathBuf| std::fs::read_to_string(p).ok().and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok());
    let profiles: Vec<serde_json::Value> = std::fs::read_dir(root.join("profiles"))
        .map(|rd| rd.flatten().filter(|e| e.path().extension().is_some_and(|x| x == "json")).filter_map(|e| read(e.path())).collect())
        .unwrap_or_default();
    json!({ "profiles": profiles, "macros": read(root.join("macros.json")), "settings": read(root.join("settings.json")) })
}

#[tauri::command]
fn quit(app: AppHandle) {
    app.exit(0);
}

fn main() {
    let minimized = std::env::args().any(|a| a == "--minimized");
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .manage(hid::Hid::default())
        .manage(Mutex::new(System::new()))
        .invoke_handler(tauri::generate_handler![
            hid::hid_open, hid::hid_write, hid::hid_close,
            winsys::set_game_mode, winsys::set_key_events, winsys::grab_screen, winsys::idle_seconds, winsys::caps_lock_on,
            audio::audio_start, audio::audio_stop,
            sysmon, foreground, export_file, import_file, set_autostart, set_close_to_tray, legacy_data, quit
        ])
        .setup(move |app| {
            let handle = app.handle().clone();
            winsys::start_hook(handle.clone());
            winsys::start_foreground_watch(handle.clone());

            let open = MenuItem::with_id(app, "open", "Open AK820 Studio", true, None::<&str>)?;
            let off = MenuItem::with_id(app, "lights_off", "Lights off", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &off, &PredefinedMenuItem::separator(app)?, &quit_i])?;
            TrayIconBuilder::with_id("tray")
                .icon(app.default_window_icon().cloned().unwrap())
                .tooltip("AK820 Studio")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, e| match e.id.as_ref() {
                    "open" => show_main(app),
                    "lights_off" => { let _ = app.emit("tray", "lights-off"); }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, e| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = e {
                        show_main(tray.app_handle());
                    }
                })
                .build(app)?;

            let win = app.get_webview_window("main").unwrap();
            let w2 = win.clone();
            win.on_window_event(move |e| {
                if let WindowEvent::CloseRequested { api, .. } = e {
                    if CLOSE_TO_TRAY.load(Ordering::Relaxed) {
                        api.prevent_close();
                        let _ = w2.hide();
                    }
                }
            });
            if !minimized {
                let _ = win.show();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running AK820 Studio");
}
