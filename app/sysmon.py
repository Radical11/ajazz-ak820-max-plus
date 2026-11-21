import time
import threading
import psutil
import ctypes
import os

from .layout import HID_TO_LED


class _NVML:
    """Tiny optional NVIDIA GPU-load reader (nvml.dll ships with the driver). No subprocesses."""
    def __init__(self):
        self.handle = None
        try:
            lib = ctypes.WinDLL("nvml.dll") if hasattr(ctypes, "WinDLL") else ctypes.CDLL("libnvidia-ml.so.1")
        except OSError:
            try:
                lib = ctypes.WinDLL(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvml.dll"))
            except Exception:
                return
        try:
            if lib.nvmlInit_v2() != 0:
                return
            h = ctypes.c_void_p()
            if lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(h)) != 0:
                return
            self.lib, self.handle = lib, h
        except Exception:
            self.handle = None

    def load(self) -> float:
        if not self.handle:
            return 0.0
        class Util(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]
        u = Util()
        try:
            if self.lib.nvmlDeviceGetUtilizationRates(self.handle, ctypes.byref(u)) == 0:
                return float(u.gpu)
        except Exception:
            pass
        return 0.0


# Physical keys ordered row by row, left to right — bars fill along real keys.
_ORDERED = [v[0] for v in sorted(HID_TO_LED.values(), key=lambda v: (v[2], v[3]))]

from .keyboard import KeyboardRGB, NUM_LEDS

class SysmonEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self._thread = None
        
        self.mode = 'cycle' # 'cycle', 'highest', 'split'
        self.interval = 1.0  # Update every 1s
        self.color_low = (0, 255, 0)
        self.color_mid = (255, 255, 0)
        self.color_high = (255, 0, 0)
        
        self.stats = {"cpu": 0, "mem": 0, "gpu": 0, "current_focus": "CPU"}
        self._cycle_idx = 0
        self._cycle_ticks = 0

    def configure(self, mode='cycle', interval=1.0, color_low=(0, 255, 0), color_mid=(255, 255, 0), color_high=(255, 0, 0)):
        with self._lock:
            self.mode = mode
            self.interval = interval
            self.color_low = tuple(color_low)
            self.color_mid = tuple(color_mid)
            self.color_high = tuple(color_high)
            
    def get_stats(self):
        with self._lock:
            return dict(self.stats)

    _nvml = None

    def _get_gpu_load(self):
        if SysmonEngine._nvml is None:
            SysmonEngine._nvml = _NVML()
        return SysmonEngine._nvml.load()

    def _lerp_color(self, c1, c2, t):
        t = max(0.0, min(1.0, t))
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t)
        )

    def _get_color_for_usage(self, usage):
        """usage is 0 to 100"""
        usage = max(0.0, min(100.0, float(usage)))
        if usage <= 50:
            return self._lerp_color(self.color_low, self.color_mid, usage / 50.0)
        else:
            return self._lerp_color(self.color_mid, self.color_high, (usage - 50.0) / 50.0)

    def _loop(self, kb: KeyboardRGB):
        while self.running:
            start_t = time.time()
            
            try:
                with self._lock:
                    mode = self.mode
                    
                cpu = max(0.0, min(100.0, psutil.cpu_percent(interval=None)))
                mem = max(0.0, min(100.0, psutil.virtual_memory().percent))
                gpu = max(0.0, min(100.0, self._get_gpu_load()))
                
                frame = [(0, 0, 0)] * NUM_LEDS
                current_focus = ""
                
                if mode == 'cycle':
                    # Cycle every 3 updates
                    if self._cycle_ticks >= 3:
                        self._cycle_ticks = 0
                        self._cycle_idx = (self._cycle_idx + 1) % 3
                    self._cycle_ticks += 1
                    
                    if self._cycle_idx == 0:
                        val = cpu; current_focus = "CPU"
                    elif self._cycle_idx == 1:
                        val = mem; current_focus = "RAM"
                    else:
                        val = gpu; current_focus = "GPU"
                        
                    color = self._get_color_for_usage(val)
                    n = round((val / 100.0) * len(_ORDERED))
                    for led in _ORDERED[:n]:
                        frame[led] = color
                            
                elif mode == 'highest':
                    highest = max(cpu, mem, gpu)
                    if highest == cpu: current_focus = "CPU"
                    elif highest == mem: current_focus = "RAM"
                    else: current_focus = "GPU"
                    
                    color = self._get_color_for_usage(highest)
                    n = round((highest / 100.0) * len(_ORDERED))
                    for led in _ORDERED[:n]:
                        frame[led] = color
                            
                else: # split
                    current_focus = "CPU / RAM / GPU"
                    third = len(_ORDERED) // 3
                    for k, (val, seg) in enumerate(((cpu, _ORDERED[:third]), (mem, _ORDERED[third:2 * third]), (gpu, _ORDERED[2 * third:]))):
                        c = self._get_color_for_usage(val)
                        for led in seg[:round(val / 100.0 * len(seg))]:
                            frame[led] = c

                with self._lock:
                    self.stats = {"cpu": int(cpu), "mem": int(mem), "gpu": int(gpu), "current_focus": current_focus}

                kb.leds = frame
                kb.push_frame()
            except OSError:
                self.running = False
                break
            except Exception:
                pass
                
            elapsed = time.time() - start_t
            with self._lock:
                sleep_time = self.interval
            time.sleep(max(0.0, sleep_time - elapsed))

    def start(self, kb: KeyboardRGB):
        if self.running:
            return True
            
        self.running = True
        
        # psutil requires a non-blocking prime call
        psutil.cpu_percent(interval=None)
        
        self._thread = threading.Thread(target=self._loop, args=(kb,), daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
