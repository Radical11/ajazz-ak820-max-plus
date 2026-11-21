"""
api.py - PyWebView JS bridge for AK820 Studio.

Callable from the UI as window.pywebview.api.<method>(...). Every method returns
a JSON-serialisable dict with an "ok" flag. Backend → UI notifications are sent
as DOM CustomEvents (see _emit): 'ak:status', 'ak:profile', 'ak:key', 'ak:record'.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time

from . import protocol as P
from .appwatch import AppWatcher
from .audio import AudioEngine, _DEFAULTS as AUDIO_DEFAULTS
from .custom_effects import CustomEffectsEngine, SOFTWARE_MODES
from .heatmap import HeatmapEngine
from .keyboard import DeviceNotFound, KeyboardRGB
from .profiles import Store, apply_keymap, send_action
from .sysmon import SysmonEngine
from .winhooks import AVAILABLE as HOOK_AVAILABLE, hook, vk_to_hid

log = logging.getLogger(__name__)

HEARTBEAT_S = 2.5
RECONNECT_S = 2.0


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _ok(**kw):
    return {"ok": True, **kw}


def _err(msg):
    return {"ok": False, "error": str(msg)}


class KeyboardAPI:
    def __init__(self):
        self._window = None
        self._kb = KeyboardRGB()
        self._lock = threading.RLock()
        self._store = Store()
        self._audio = AudioEngine()
        self._heatmap = HeatmapEngine()
        self._sysmon = SysmonEngine()
        self._effects = CustomEffectsEngine()
        self._studio: str | None = None          # 'audio' | 'heatmap' | 'sysmon' | 'effect'
        self._manual_profile = self._store.settings.get("active_profile", "default")
        self._auto_profile: str | None = None
        self._recording: list | None = None
        self._rec_last = 0.0
        self._tester_on = False
        self._stop = threading.Event()
        self._last_error = ""
        own = os.path.basename(sys.executable).lower()
        self._watcher = AppWatcher(self._on_foreground, ignore=(own, "python.exe", "pythonw.exe",
                                                                "ak820studio.exe", "msedgewebview2.exe"))

    # ════════════════════════════════════════════════════════════════════
    # lifecycle (called from main.py, not exposed to JS by convention "_")
    # ════════════════════════════════════════════════════════════════════
    def _attach(self, window):
        self._window = window

    def _start_background(self):
        threading.Thread(target=self._supervise, daemon=True, name="Supervisor").start()
        if self._store.settings.get("auto_switch", True):
            self._watcher.start()
        gm = self._store.active_profile()["game_mode"]
        hook.set_game_mode(gm["win"], gm["alt_tab"], gm["alt_f4"])

    def _shutdown(self):
        self._stop.set()
        self._watcher.stop()
        self._stop_studio()
        hook.set_game_mode(False, False, False)
        hook.remove_listener("tester")
        hook.remove_listener("recorder")
        self._kb.disconnect()

    def _emit(self, name: str, data) -> None:
        w = self._window
        if not w:
            return
        try:
            w.evaluate_js(f"window.dispatchEvent(new CustomEvent({json.dumps(name)},"
                          f"{{detail:{json.dumps(data)}}}))")
        except Exception:
            pass

    def _status(self) -> dict:
        return {
            "connected": self._kb.is_connected(),
            "connection": self._kb.connection_type,
            "studio": self._studio,
            "error": self._last_error,
            "active_profile": self._store.settings.get("active_profile"),
            "auto_profile": self._auto_profile,
            "foreground": self._watcher.current,
        }

    # ── connection supervisor: heartbeat + hot-plug reconnect ─────────
    def _supervise(self):
        first = True
        while not self._stop.is_set():
            if self._kb.is_connected():
                try:
                    self._kb.heartbeat()
                except OSError as e:
                    self._last_error = "Keyboard disconnected"
                    log.info("heartbeat failed: %s", e)
                    self._emit("ak:status", self._status())
                self._stop.wait(HEARTBEAT_S)
                continue
            try:
                with self._lock:
                    self._kb.connect()
                self._last_error = ""
                self._on_connected(initial=first)
            except DeviceNotFound as e:
                if self._last_error != str(e):
                    self._last_error = str(e)
                    self._emit("ak:status", self._status())
            first = False
            self._stop.wait(RECONNECT_S)

    def _on_connected(self, initial: bool):
        prof = self._store.active_profile()
        try:
            self._apply_lighting(prof["lighting"])
            if initial:
                self._apply_device(prof["device"])
        except OSError:
            pass
        self._emit("ak:status", self._status())

    # ════════════════════════════════════════════════════════════════════
    # state
    # ════════════════════════════════════════════════════════════════════
    def get_state(self) -> dict:
        modes = [{"id": k, "name": v["name"], "controls": v["controls"], "software": False}
                 for k, v in P.HARDWARE_MODES.items()]
        modes += [{"id": k, "name": v["name"], "controls": v["controls"], "software": True}
                  for k, v in SOFTWARE_MODES.items()]
        return _ok(
            status=self._status(),
            settings=self._store.settings,
            profiles=self._store.list_profiles(),
            profile=self._store.active_profile(),
            macros=self._store.macros,
            modes=modes,
            colors=list(P.COLORS.keys()),
            sleep_options=P.SLEEP_OPTIONS,
            response_options=P.RESPONSE_OPTIONS,
            max_macro_events=P.MAX_MACRO_EVENTS,
            hook_available=HOOK_AVAILABLE,
            leds=self._kb.get_leds_as_hex(),
            audio=self._audio_config(),
            audio_devices=self._audio.get_devices(),
        )

    def get_status(self) -> dict:
        return _ok(status=self._status(), stats=self._sysmon.get_stats() if self._studio == "sysmon" else None)

    def reconnect(self) -> dict:
        with self._lock:
            self._kb.disconnect()
            try:
                self._kb.connect()
            except DeviceNotFound as e:
                self._last_error = str(e)
                return _err(e)
        self._last_error = ""
        self._on_connected(initial=False)
        return _ok(status=self._status())

    # ── helper to run device ops ──────────────────────────────────────
    def _op(self, fn):
        with self._lock:
            if not self._kb.is_connected():
                try:
                    self._kb.connect()
                except DeviceNotFound as e:
                    return _err(e)
            try:
                res = fn()
                return res if isinstance(res, dict) else _ok()
            except OSError as e:
                self._emit("ak:status", self._status())
                return _err(f"Keyboard I/O error: {e}")
            except ValueError as e:
                return _err(e)

    def _update_profile(self, mutate) -> dict:
        p = self._store.active_profile()
        mutate(p)
        return self._store.save_profile(p)

    # ════════════════════════════════════════════════════════════════════
    # lighting
    # ════════════════════════════════════════════════════════════════════
    def _stop_studio(self):
        for eng in (self._audio, self._heatmap, self._sysmon, self._effects):
            if eng.running:
                eng.stop()
        self._studio = None

    def _apply_lighting(self, L: dict):
        kind = L.get("kind")
        self._stop_studio()
        if kind == "hardware":
            self._kb.set_hardware_mode(int(L["mode"]), int(L.get("brightness", 4)), int(L.get("speed", 2)),
                                       int(L.get("direction", 0)), P.COLORS.get(L.get("color", "rgb"), 7),
                                       P.COLORS.get(L.get("color2", "rgb"), 7))
        elif kind == "custom":
            self._kb.leds = [_hex_to_rgb(h) for h in L["leds"]]
            self._kb.init_custom_mode(force=True)
            self._kb.push_frame(force=True)
        elif kind == "studio":
            self._start_studio(L.get("engine"), L.get("config") or {})

    def _start_studio(self, engine: str, cfg: dict):
        self._kb.init_custom_mode(force=True)
        if engine == "audio":
            self._audio.configure(**{k: (tuple(v) if isinstance(v, list) else v)
                                     for k, v in cfg.items() if k in AUDIO_DEFAULTS})
            ok = self._audio.start(cfg.get("mode", "spectrum"), self._kb, cfg.get("device_id"))
        elif engine == "heatmap":
            self._heatmap.configure(cfg.get("decay_rate", 0.02), cfg.get("hot_color", (254, 40, 0)),
                                    cfg.get("cold_color", (0, 0, 60)))
            ok = self._heatmap.start(self._kb)
        elif engine == "sysmon":
            self._sysmon.configure(cfg.get("mode", "cycle"), float(cfg.get("interval", 1.0)),
                                   cfg.get("color_low", (0, 254, 0)), cfg.get("color_mid", (254, 254, 0)),
                                   cfg.get("color_high", (254, 0, 0)))
            ok = self._sysmon.start(self._kb)
        elif engine == "effect":
            ok = self._effects.start(self._kb, int(cfg.get("mode", 100)), int(cfg.get("brightness", 4)),
                                     int(cfg.get("speed", 2)), int(cfg.get("direction", 0)), cfg.get("color", "rgb"))
        else:
            raise ValueError(f"unknown studio engine {engine!r}")
        if not ok:
            raise ValueError(getattr(self._audio, "last_error", "") or f"Could not start {engine}")
        self._studio = engine

    def set_lighting(self, lighting: dict) -> dict:
        """Apply a lighting config and store it in the active profile."""
        def go():
            if lighting.get("kind") == "hardware" and int(lighting.get("mode", 0)) in SOFTWARE_MODES:
                lighting.update(kind="studio", engine="effect", config=dict(lighting))
            self._apply_lighting(lighting)
            self._update_profile(lambda p: p.__setitem__("lighting", lighting))
            return _ok(status=self._status())
        return self._op(go)

    def set_custom_color(self, leds: list[str]) -> dict:
        if len(leds) != P.NUM_LEDS:
            return _err(f"Expected {P.NUM_LEDS} colours")
        return self.set_lighting({"kind": "custom", "leds": leds})

    def set_all_color(self, hex_color: str) -> dict:
        res = self.set_custom_color([hex_color] * P.NUM_LEDS)
        return {**res, "leds": self._kb.get_leds_as_hex()} if res["ok"] else res

    def turn_off(self) -> dict:
        return self.set_all_color("#000000")

    def save_to_hardware(self) -> dict:
        return self._op(lambda: self._kb.save_to_hardware())

    def stop_studio(self) -> dict:
        self._stop_studio()
        return _ok(status=self._status())

    def configure_audio(self, settings: dict) -> dict:
        self._audio.configure(**{k: (tuple(v) if isinstance(v, list) else v)
                                 for k, v in settings.items() if k in AUDIO_DEFAULTS})
        return _ok()

    def configure_heatmap(self, decay_rate, hot_color, cold_color) -> dict:
        self._heatmap.configure(decay_rate, hot_color, cold_color)
        return _ok()

    def configure_sysmon(self, mode, interval, color_low, color_mid, color_high) -> dict:
        self._sysmon.configure(mode, float(interval), color_low, color_mid, color_high)
        return _ok()

    def get_sysmon_stats(self) -> dict:
        return _ok(stats=self._sysmon.get_stats())

    def get_audio_devices(self) -> dict:
        return _ok(devices=self._audio.get_devices())

    def _audio_config(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in AUDIO_DEFAULTS.items()}

    # ════════════════════════════════════════════════════════════════════
    # keys
    # ════════════════════════════════════════════════════════════════════
    def assign_key(self, layer: int, src_hid: int, action: dict) -> dict:
        layer, src_hid = int(layer), int(src_hid)
        if layer not in (1, 2):
            return _err("layer must be 1 or 2")

        def go():
            send_action(self._kb, layer, src_hid, action, self._store)

            def mut(p):
                km = p["keymap"][str(layer)]
                if action.get("type") == "default":
                    km.pop(str(src_hid), None)
                else:
                    km[str(src_hid)] = action
            return _ok(profile=self._update_profile(mut))
        return self._op(go)

    def reset_keys(self, layer: int | None = None) -> dict:
        """Clear assignments for one layer (or both) and resend the remaining map."""
        def go():
            def mut(p):
                for l in ((str(layer),) if layer else ("1", "2")):
                    p["keymap"][l] = {}
            prof = self._update_profile(mut)
            warns = apply_keymap(self._kb, prof, self._store)
            return _ok(profile=prof, warnings=warns)
        return self._op(go)

    # ════════════════════════════════════════════════════════════════════
    # macros + recorder
    # ════════════════════════════════════════════════════════════════════
    def save_macro(self, macro: dict) -> dict:
        try:
            m = self._store.save_macro(macro)
        except ValueError as e:
            return _err(e)
        # re-send keys that use this macro so edits reach the keyboard
        prof = self._store.active_profile()
        uses = [(l, s) for l in ("1", "2") for s, a in prof["keymap"][l].items()
                if a.get("type") == "macro" and a.get("macro_id") == m["id"]]
        if uses and self._kb.is_connected():
            self._op(lambda: [send_action(self._kb, int(l), int(s), {"type": "macro", "macro_id": m["id"]},
                                          self._store) for l, s in uses])
        return _ok(macro=m, macros=self._store.macros)

    def delete_macro(self, macro_id: str) -> dict:
        prof = self._store.active_profile()
        for l in ("1", "2"):
            for s, a in list(prof["keymap"][l].items()):
                if a.get("type") == "macro" and a.get("macro_id") == macro_id:
                    self.assign_key(int(l), int(s), {"type": "default"})
        self._store.delete_macro(macro_id)
        return _ok(macros=self._store.macros, profile=self._store.active_profile())

    def record_start(self) -> dict:
        self._recording = []
        self._rec_last = time.perf_counter()

        def on_key(vk, _scan, down, ext, injected):
            if injected or self._recording is None:
                return
            hid = vk_to_hid(vk, ext)
            if hid is None:
                return
            rec = self._recording
            if rec and rec[-1]["code"] == hid and rec[-1]["up"] == (not down):
                return  # auto-repeat
            now = time.perf_counter()
            if rec:
                rec[-1]["delay"] = int((now - self._rec_last) * 1000)
            self._rec_last = now
            rec.append({"code": hid, "up": not down, "delay": 10})
            self._emit("ak:record", rec[-P.MAX_MACRO_EVENTS:])
        if not hook.add_listener("recorder", on_key):
            self._recording = None
            return _err("Keyboard recording isn't available on this system")
        return _ok()

    def record_stop(self) -> dict:
        hook.remove_listener("recorder")
        events, self._recording = self._recording or [], None
        return _ok(events=events[:P.MAX_MACRO_EVENTS], truncated=len(events) > P.MAX_MACRO_EVENTS)

    # ════════════════════════════════════════════════════════════════════
    # profiles
    # ════════════════════════════════════════════════════════════════════
    def _activate(self, pid: str, manual: bool) -> dict:
        prof = self._store.get_profile(pid)
        if not prof:
            return _err("Profile not found")
        if manual:
            self._manual_profile = pid
            self._auto_profile = None
        self._store.update_settings(active_profile=pid)
        gm = prof["game_mode"]
        hook.set_game_mode(gm["win"], gm["alt_tab"], gm["alt_f4"])

        def go():
            warns = apply_keymap(self._kb, prof, self._store)
            self._apply_device(prof["device"])
            self._apply_lighting(prof["lighting"])
            return _ok(profile=prof, warnings=warns, status=self._status())
        res = self._op(go)
        self._emit("ak:profile", {"profile": prof, "status": self._status()})
        return res if res["ok"] else _ok(profile=prof, warning=res.get("error"))

    def activate_profile(self, pid: str) -> dict:
        return self._activate(pid, manual=True)

    def create_profile(self, name: str, base: str | None = None) -> dict:
        p = self._store.create_profile(name, base)
        return _ok(profile=p, profiles=self._store.list_profiles())

    def update_profile_meta(self, pid: str, name: str | None = None, apps: list | None = None) -> dict:
        p = self._store.get_profile(pid)
        if not p:
            return _err("Profile not found")
        if name is not None:
            p["name"] = name.strip() or p["name"]
        if apps is not None:
            p["apps"] = apps
        self._store.save_profile(p)
        return _ok(profiles=self._store.list_profiles())

    def delete_profile(self, pid: str) -> dict:
        try:
            self._store.delete_profile(pid)
        except ValueError as e:
            return _err(e)
        if self._store.settings.get("active_profile") == "default" and self._manual_profile == pid:
            self._activate("default", manual=True)
        return _ok(profiles=self._store.list_profiles())

    def export_profile(self, pid: str) -> dict:
        p = self._store.get_profile(pid)
        if not p:
            return _err("Profile not found")
        used = {a["macro_id"] for l in ("1", "2") for a in p["keymap"][l].values() if a.get("type") == "macro"}
        bundle = {"format": "ak820studio-profile", "version": 1, "profile": p,
                  "macros": [m for m in self._store.macros if m["id"] in used]}
        return _ok(json=json.dumps(bundle, indent=2), filename=f"{p['id']}.ak820.json")

    def import_profile(self, text: str) -> dict:
        try:
            data = json.loads(text)
            prof = data["profile"] if data.get("format") == "ak820studio-profile" else data
            for m in data.get("macros", []):
                self._store.save_macro(m)
            existing = {p["id"] for p in self._store.list_profiles()}
            if prof.get("id") in existing:
                prof["id"] = f"{prof['id']}-imported"
                prof["name"] = f"{prof.get('name', 'Profile')} (imported)"
            p = self._store.save_profile(prof)
        except (ValueError, KeyError, TypeError) as e:
            return _err(f"Not a valid profile file: {e}")
        return _ok(profile=p, profiles=self._store.list_profiles(), macros=self._store.macros)

    def export_profile_file(self, pid: str) -> dict:
        res = self.export_profile(pid)
        if not res["ok"] or not self._window:
            return res
        import webview
        path = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=res["filename"],
                                               file_types=("AK820 profile (*.json)",))
        if not path:
            return _ok(cancelled=True)
        path = path if isinstance(path, str) else path[0]
        with open(path, "w", encoding="utf-8") as f:
            f.write(res["json"])
        return _ok(path=path)

    def import_profile_file(self) -> dict:
        if not self._window:
            return _err("No window")
        import webview
        paths = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=("AK820 profile (*.json)", "All files (*.*)"))
        if not paths:
            return _ok(cancelled=True)
        try:
            with open(paths[0], encoding="utf-8") as f:
                return self.import_profile(f.read())
        except OSError as e:
            return _err(e)

    def running_apps(self) -> dict:
        try:
            import psutil
            names = sorted({(p.info["name"] or "").lower() for p in psutil.process_iter(["name"])
                            if p.info["name"] and p.info["name"].lower().endswith(".exe")})
        except Exception:
            names = []
        return _ok(apps=names)

    def _on_foreground(self, exe: str):
        if not self._store.settings.get("auto_switch", True):
            return
        target = self._store.profile_for_app(exe)
        want = target["id"] if target else self._manual_profile
        if want != self._store.settings.get("active_profile"):
            self._auto_profile = target["id"] if target else None
            self._activate(want, manual=False)
        else:
            self._emit("ak:status", self._status())

    # ════════════════════════════════════════════════════════════════════
    # device settings, game mode, tester, app settings
    # ════════════════════════════════════════════════════════════════════
    def _apply_device(self, d: dict):
        self._kb.set_sleep(int(d.get("sleep", 3)))
        self._kb.set_response(int(d.get("response", 1)))
        self._kb.set_fn_mode(bool(d.get("fn_swap", False)))

    def set_device(self, sleep: int | None = None, response: int | None = None, fn_swap: bool | None = None) -> dict:
        def go():
            if sleep is not None:
                self._kb.set_sleep(int(sleep))
            if response is not None:
                self._kb.set_response(int(response))
            if fn_swap is not None:
                self._kb.set_fn_mode(bool(fn_swap))

            def mut(p):
                if sleep is not None:
                    p["device"]["sleep"] = int(sleep)
                if response is not None:
                    p["device"]["response"] = int(response)
                if fn_swap is not None:
                    p["device"]["fn_swap"] = bool(fn_swap)
            return _ok(profile=self._update_profile(mut))
        return self._op(go)

    def set_game_mode(self, win: bool, alt_tab: bool, alt_f4: bool) -> dict:
        if not hook.set_game_mode(win, alt_tab, alt_f4):
            return _err("Game mode needs Windows")
        prof = self._update_profile(lambda p: p.__setitem__(
            "game_mode", {"win": bool(win), "alt_tab": bool(alt_tab), "alt_f4": bool(alt_f4)}))
        return _ok(profile=prof)

    def key_tester(self, on: bool) -> dict:
        if on:
            def on_key(vk, scan, down, ext, injected):
                hid = vk_to_hid(vk, ext)
                self._emit("ak:key", {"hid": hid, "vk": vk, "down": down, "t": time.perf_counter()})
            if not hook.add_listener("tester", on_key):
                return _err("Key tester isn't available on this system")
        else:
            hook.remove_listener("tester")
        return _ok()

    def update_settings(self, settings: dict) -> dict:
        s = self._store.update_settings(**settings)
        if "auto_switch" in settings:
            (self._watcher.start if settings["auto_switch"] else self._watcher.stop)()
        if "launch_at_login" in settings:
            self._set_autostart(bool(settings["launch_at_login"]))
        return _ok(settings=s)

    def _set_autostart(self, on: bool):
        if os.name != "nt":
            return
        import winreg
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        cmd = f'"{pyw}" "{os.path.join(root, "main.py")}" --minimized'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "AK820Studio", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, "AK820Studio")
                except FileNotFoundError:
                    pass

    def factory_reset_keys(self) -> dict:
        """Reset the keyboard's key map to stock (does not touch profiles on disk)."""
        return self._op(lambda: self._kb.reset_keymap())
