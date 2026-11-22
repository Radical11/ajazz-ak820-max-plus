//! HID transport: finds the AK820's vendor collection (usage page 0xFF02),
//! writes 64-byte packets (with report ID 0) and streams replies to the UI.

use hidapi::{HidApi, HidDevice};
use serde_json::json;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter};

const VID: u16 = 0x1A2C;
const PIDS: [u16; 2] = [0xA036, 0x8FFF];
const VENDOR_PAGE: u16 = 0xFF02;

#[derive(Default)]
pub struct Hid {
    writer: Mutex<Option<HidDevice>>,
    generation: AtomicU64,
}

fn disconnect(app: &AppHandle, hid: &Hid, gen: u64) {
    if hid.generation.load(Ordering::SeqCst) == gen {
        *hid.writer.lock().unwrap() = None;
        let _ = app.emit("hid-disconnect", ());
    }
}

#[tauri::command]
pub fn hid_open(app: AppHandle, state: tauri::State<'_, Hid>) -> Result<serde_json::Value, String> {
    let api = HidApi::new().map_err(|e| e.to_string())?;
    let mut infos: Vec<_> = api
        .device_list()
        .filter(|d| d.vendor_id() == VID && PIDS.contains(&d.product_id()))
        .collect();
    infos.sort_by_key(|d| (d.usage_page() != VENDOR_PAGE, d.interface_number() != 0, d.product_id() != PIDS[0]));
    let info = infos
        .into_iter()
        .find(|d| d.usage_page() == VENDOR_PAGE || d.interface_number() == 0)
        .ok_or("AK820 Max Plus not found. Plug in the cable or the 2.4 GHz dongle.")?;
    let writer = info.open_device(&api).map_err(|e| format!("Could not open the keyboard: {e}"))?;
    let reader = info.open_device(&api).map_err(|e| format!("Could not open the keyboard: {e}"))?;
    let gen = state.generation.fetch_add(1, Ordering::SeqCst) + 1;
    *state.writer.lock().unwrap() = Some(writer);

    let app2 = app.clone();
    std::thread::spawn(move || {
        let mut buf = [0u8; 65];
        loop {
            let hid = app2.state::<Hid>();
            if hid.generation.load(Ordering::SeqCst) != gen {
                break;
            }
            match reader.read_timeout(&mut buf, 250) {
                Ok(0) => {}
                Ok(n) => {
                    let _ = app2.emit("hid-input", buf[..n].to_vec());
                }
                Err(_) => {
                    disconnect(&app2, &hid, gen);
                    break;
                }
            }
        }
    });
    Ok(json!({ "pid": info.product_id(), "release": info.release_number() }))
}

#[tauri::command]
pub fn hid_write(app: AppHandle, state: tauri::State<'_, Hid>, packets: Vec<Vec<u8>>) -> Result<(), String> {
    let mut guard = state.writer.lock().unwrap();
    let dev = guard.as_ref().ok_or("Connect the keyboard first")?;
    let mut report = [0u8; 65];
    for p in &packets {
        report.fill(0);
        let n = p.len().min(64);
        report[1..1 + n].copy_from_slice(&p[..n]);
        if let Err(e) = dev.write(&report) {
            *guard = None;
            state.generation.fetch_add(1, Ordering::SeqCst);
            let _ = app.emit("hid-disconnect", ());
            return Err(format!("Keyboard I/O error: {e}"));
        }
    }
    Ok(())
}

#[tauri::command]
pub fn hid_close(state: tauri::State<'_, Hid>) {
    state.generation.fetch_add(1, Ordering::SeqCst);
    *state.writer.lock().unwrap() = None;
}

use tauri::Manager;
