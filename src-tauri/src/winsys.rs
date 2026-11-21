//! Windows integration: one global keyboard hook (game mode + key events),
//! foreground-app watcher, and tiny GDI screen sampling for ambient lighting.

use serde::Serialize;
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::mpsc::{channel, Sender};
use std::sync::{Mutex, OnceLock};
use tauri::{AppHandle, Emitter};
use windows::core::PWSTR;
use windows::Win32::Foundation::{CloseHandle, HWND, LPARAM, LRESULT, WPARAM};
use windows::Win32::Graphics::Gdi::*;
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::Threading::{OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32, PROCESS_QUERY_LIMITED_INFORMATION};
use windows::Win32::UI::WindowsAndMessaging::*;

#[derive(Serialize, Clone, Copy)]
pub struct KeyEvent {
    vk: u32,
    ext: bool,
    down: bool,
    injected: bool,
}

static GAME: AtomicU8 = AtomicU8::new(0); // bit0 win, bit1 alt+tab, bit2 alt+f4
static EMIT_KEYS: AtomicBool = AtomicBool::new(false);
static TX: OnceLock<Mutex<Sender<KeyEvent>>> = OnceLock::new();

unsafe extern "system" fn hook_proc(code: i32, w: WPARAM, l: LPARAM) -> LRESULT {
    if code == 0 {
        let kb = &*(l.0 as *const KBDLLHOOKSTRUCT);
        let msg = w.0 as u32;
        let down = msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN;
        let injected = kb.flags.0 & LLKHF_INJECTED.0 != 0;
        let alt = kb.flags.0 & LLKHF_ALTDOWN.0 != 0;
        if EMIT_KEYS.load(Ordering::Relaxed) {
            if let Some(tx) = TX.get() {
                let _ = tx.lock().unwrap().send(KeyEvent { vk: kb.vkCode, ext: kb.flags.0 & LLKHF_EXTENDED.0 != 0, down, injected });
            }
        }
        if !injected {
            let g = GAME.load(Ordering::Relaxed);
            let vk = kb.vkCode;
            let block = (g & 1 != 0 && (vk == 0x5B || vk == 0x5C))
                || (g & 2 != 0 && down && alt && vk == 0x09)
                || (g & 4 != 0 && down && alt && vk == 0x73);
            if block {
                return LRESULT(1);
            }
        }
    }
    CallNextHookEx(HHOOK::default(), code, w, l)
}

pub fn start_hook(app: AppHandle) {
    let (tx, rx) = channel::<KeyEvent>();
    let _ = TX.set(Mutex::new(tx));
    std::thread::spawn(move || {
        for ev in rx {
            let _ = app.emit("key", ev);
        }
    });
    std::thread::spawn(|| unsafe {
        let module = GetModuleHandleW(None).unwrap_or_default();
        let _hook = SetWindowsHookExW(WH_KEYBOARD_LL, Some(hook_proc), module, 0);
        let mut msg = MSG::default();
        while GetMessageW(&mut msg, HWND::default(), 0, 0).as_bool() {}
    });
}

#[tauri::command]
pub fn set_game_mode(win: bool, alt_tab: bool, alt_f4: bool) {
    GAME.store((win as u8) | ((alt_tab as u8) << 1) | ((alt_f4 as u8) << 2), Ordering::Relaxed);
}

#[tauri::command]
pub fn set_key_events(on: bool) {
    EMIT_KEYS.store(on, Ordering::Relaxed);
}

pub fn foreground_exe() -> String {
    unsafe {
        let hwnd = GetForegroundWindow();
        if hwnd.0.is_null() {
            return String::new();
        }
        let mut pid = 0u32;
        GetWindowThreadProcessId(hwnd, Some(&mut pid));
        let Ok(h) = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid) else { return String::new() };
        let mut buf = [0u16; 1024];
        let mut size = buf.len() as u32;
        let ok = QueryFullProcessImageNameW(h, PROCESS_NAME_WIN32, PWSTR(buf.as_mut_ptr()), &mut size).is_ok();
        let _ = CloseHandle(h);
        if !ok {
            return String::new();
        }
        let path = String::from_utf16_lossy(&buf[..size as usize]);
        path.rsplit('\\').next().unwrap_or("").to_lowercase()
    }
}

pub fn start_foreground_watch(app: AppHandle) {
    std::thread::spawn(move || {
        let own = std::env::current_exe().ok().and_then(|p| p.file_name().map(|f| f.to_string_lossy().to_lowercase())).unwrap_or_default();
        let mut last = String::new();
        loop {
            std::thread::sleep(std::time::Duration::from_millis(1000));
            let exe = foreground_exe();
            if !exe.is_empty() && exe != last && exe != own && exe != "msedgewebview2.exe" {
                last = exe.clone();
                let _ = app.emit("foreground", exe);
            }
        }
    });
}

/// Downscaled primary screen as RGBA (cols x rows), for ambient lighting.
#[tauri::command]
pub fn grab_screen(cols: i32, rows: i32) -> Result<Vec<u8>, String> {
    unsafe {
        let sw = GetSystemMetrics(SM_CXSCREEN);
        let sh = GetSystemMetrics(SM_CYSCREEN);
        let sdc = GetDC(HWND::default());
        let mdc = CreateCompatibleDC(sdc);
        let bmp = CreateCompatibleBitmap(sdc, cols, rows);
        let old = SelectObject(mdc, bmp);
        SetStretchBltMode(mdc, HALFTONE);
        let _ = StretchBlt(mdc, 0, 0, cols, rows, sdc, 0, 0, sw, sh, SRCCOPY);
        let mut bmi = BITMAPINFO::default();
        bmi.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as u32;
        bmi.bmiHeader.biWidth = cols;
        bmi.bmiHeader.biHeight = -rows;
        bmi.bmiHeader.biPlanes = 1;
        bmi.bmiHeader.biBitCount = 32;
        let mut buf = vec![0u8; (cols * rows * 4) as usize];
        let got = GetDIBits(mdc, bmp, 0, rows as u32, Some(buf.as_mut_ptr() as *mut _), &mut bmi, DIB_RGB_COLORS);
        SelectObject(mdc, old);
        let _ = DeleteObject(bmp);
        let _ = DeleteDC(mdc);
        ReleaseDC(HWND::default(), sdc);
        if got == 0 {
            return Err("Screen capture failed".into());
        }
        for px in buf.chunks_exact_mut(4) {
            px.swap(0, 2); // BGRA -> RGBA
            px[3] = 255;
        }
        Ok(buf)
    }
}
