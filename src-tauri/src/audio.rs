//! Audio capture for music lighting: system output (WASAPI loopback) or a microphone.
//! Emits a byte spectrum shaped like Web Audio's AnalyserNode (fft 1024) ~30x a second.

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use rustfft::{num_complex::Complex, FftPlanner};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter};

static GEN: AtomicU64 = AtomicU64::new(0);
const N: usize = 1024;
const BINS: usize = 160;

#[tauri::command]
pub fn audio_start(app: AppHandle, source: String) -> Result<(), String> {
    let gen = GEN.fetch_add(1, Ordering::SeqCst) + 1;
    let (ready_tx, ready_rx) = std::sync::mpsc::channel::<Result<(), String>>();
    std::thread::spawn(move || {
        let host = cpal::default_host();
        let dev = if source == "system" { host.default_output_device() } else { host.default_input_device() };
        let Some(dev) = dev else { let _ = ready_tx.send(Err("No audio device found".into())); return };
        let cfg = if source == "system" { dev.default_output_config() } else { dev.default_input_config() };
        let cfg = match cfg { Ok(c) => c, Err(e) => { let _ = ready_tx.send(Err(e.to_string())); return } };
        if cfg.sample_format() != cpal::SampleFormat::F32 {
            let _ = ready_tx.send(Err("Unsupported audio format".into()));
            return;
        }
        let channels = cfg.channels() as usize;
        let mut ring: Vec<f32> = Vec::with_capacity(N);
        let fft = FftPlanner::<f32>::new().plan_fft_forward(N);
        let hann: Vec<f32> = (0..N).map(|i| 0.5 - 0.5 * (std::f32::consts::TAU * i as f32 / N as f32).cos()).collect();
        let mut last = Instant::now();
        let app2 = app.clone();
        let stream = dev.build_input_stream(
            &cfg.into(),
            move |data: &[f32], _| {
                for frame in data.chunks(channels) {
                    ring.push(frame.iter().sum::<f32>() / channels as f32);
                    if ring.len() == N {
                        if last.elapsed() >= Duration::from_millis(33) {
                            last = Instant::now();
                            let mut buf: Vec<Complex<f32>> = ring.iter().zip(&hann).map(|(s, w)| Complex::new(s * w, 0.0)).collect();
                            fft.process(&mut buf);
                            let bins: Vec<u8> = buf[..BINS]
                                .iter()
                                .map(|c| {
                                    let db = 20.0 * (c.norm() / N as f32 + 1e-9).log10();
                                    (((db + 100.0) / 70.0).clamp(0.0, 1.0) * 255.0) as u8
                                })
                                .collect();
                            let _ = app2.emit("audio-bins", bins);
                        }
                        ring.clear();
                    }
                }
            },
            |_| {},
            None,
        );
        let stream = match stream { Ok(s) => s, Err(e) => { let _ = ready_tx.send(Err(e.to_string())); return } };
        if let Err(e) = stream.play() { let _ = ready_tx.send(Err(e.to_string())); return }
        let _ = ready_tx.send(Ok(()));
        while GEN.load(Ordering::SeqCst) == gen {
            std::thread::sleep(Duration::from_millis(100));
        }
        drop(stream);
    });
    ready_rx.recv_timeout(Duration::from_secs(5)).map_err(|_| "Audio didn't start".to_string())?
}

#[tauri::command]
pub fn audio_stop() {
    GEN.fetch_add(1, Ordering::SeqCst);
}
