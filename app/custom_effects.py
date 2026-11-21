import time
import threading
import random
import math
from .keyboard import KeyboardRGB, NUM_LEDS

SOFTWARE_MODES = {
    100: {"name": "Lightning Storm", "controls": "BSC"},
    101: {"name": "Matrix Rain", "controls": "BSC"},
    102: {"name": "Campfire", "controls": "BSC"},
    103: {"name": "Starlight", "controls": "BSC"},
    104: {"name": "Radar", "controls": "BSDC"},
    105: {"name": "Ripple", "controls": "BSC"}
}

COLOR_MAP = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "pink": (255, 0, 255),
    "cyan": (0, 255, 255),
    "white": (255, 255, 255),
}

class CustomEffectsEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self._thread = None
        self.mode_id = 100
        self.brightness = 4
        self.speed = 2
        self.direction = 0
        self.color_name = "rgb"
        
    def start(self, kb: KeyboardRGB, mode_id: int, brightness: int = 4, speed: int = 2, direction: int = 0, color_name: str = "rgb") -> bool:
        with self._lock:
            if self.running:
                self.running = False
                if self._thread:
                    self._thread.join(timeout=1.0)
            
            self.mode_id = mode_id
            self.brightness = brightness
            self.speed = speed
            self.direction = direction
            self.color_name = color_name
            self.running = True
            self._thread = threading.Thread(target=self._loop, args=(kb,), daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        with self._lock:
            self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            
    def _get_base_color(self):
        if self.color_name in COLOR_MAP:
            return COLOR_MAP[self.color_name]
        return None # "rgb" means random/rainbow or default
        
    def _apply_brightness(self, color):
        mult = (max(0, min(4, int(self.brightness))) + 1) / 5.0
        return tuple(max(0, min(254, int(v * mult))) for v in color)

    def _get_sleep_time(self, base_sleep):
        # speed is 0 to 4. 0 is slow, 4 is fast.
        mult = 2.0 - (self.speed * 0.375) 
        return base_sleep * mult

    def _push(self, kb: KeyboardRGB, frame):
        # Apply brightness to the whole frame
        frame = [self._apply_brightness(c) for c in frame]
        kb.leds = frame
        kb.push_frame()

    def _loop(self, kb: KeyboardRGB):
        kb.init_custom_mode()
        if self.mode_id == 100:
            self._loop_lightning(kb)
        elif self.mode_id == 101:
            self._loop_matrix(kb)
        elif self.mode_id == 102:
            self._loop_campfire(kb)
        elif self.mode_id == 103:
            self._loop_starlight(kb)
        elif self.mode_id == 104:
            self._loop_radar(kb)
        elif self.mode_id == 105:
            self._loop_ripple(kb)
            
    def _loop_lightning(self, kb: KeyboardRGB):
        bg = self._get_base_color()
        if not bg: bg = (10, 0, 20)
        else: bg = (bg[0]//10, bg[1]//10, bg[2]//10)
        
        flash_color = (255, 255, 255)
        
        while self.running:
            frame = [bg] * NUM_LEDS
            
            if random.random() < 0.15: 
                num_flashes = random.randint(1, 4)
                for _ in range(num_flashes):
                    idx = random.randint(0, NUM_LEDS - 1)
                    frame[idx] = flash_color
                    if idx > 0: frame[idx-1] = (200, 200, 255)
                    if idx < NUM_LEDS - 1: frame[idx+1] = (200, 200, 255)
                    
            try:
                self._push(kb, frame)
            except OSError:
                self.running = False
                break
                
            time.sleep(self._get_sleep_time(0.05))
            
    def _loop_matrix(self, kb: KeyboardRGB):
        base = self._get_base_color()
        if not base: base = (0, 255, 0)
        
        tails = [0.0] * NUM_LEDS
        while self.running:
            for i in range(NUM_LEDS):
                tails[i] = max(0.0, tails[i] - 0.15)
                
            for _ in range(3):
                if random.random() < 0.4:
                    idx = random.randint(0, NUM_LEDS - 1)
                    tails[idx] = 1.0
                
            frame = [(int(base[0] * val), int(base[1] * val), int(base[2] * val)) for val in tails]
            try:
                self._push(kb, frame)
            except OSError:
                self.running = False
                break
            time.sleep(self._get_sleep_time(0.05))
            
    def _loop_campfire(self, kb: KeyboardRGB):
        base = self._get_base_color()
        if not base: base = (255, 100, 0) # Orange default
        
        while self.running:
            frame = []
            for _ in range(NUM_LEDS):
                heat = random.random()
                if heat < 0.4:
                    # Deep
                    r, g, b = base[0], base[1]//3, base[2]//3
                elif heat < 0.8:
                    # Mid
                    r, g, b = base[0], int(base[1]*1.2), base[2]
                else:
                    # High
                    r, g, b = min(255, int(base[0]*1.2)), min(255, int(base[1]*1.5)), min(255, int(base[2]*2))
                    
                dim = random.uniform(0.1, 1.0)
                frame.append((int(r * dim), int(g * dim), int(b * dim)))
                
            try:
                self._push(kb, frame)
            except OSError:
                self.running = False
                break
            time.sleep(self._get_sleep_time(0.08))

    def _loop_starlight(self, kb: KeyboardRGB):
        base = self._get_base_color()
        stars = [0.0] * NUM_LEDS
        dirs = [0] * NUM_LEDS # 1 for up, -1 for down
        
        while self.running:
            frame = []
            for i in range(NUM_LEDS):
                if dirs[i] == 0:
                    if random.random() < 0.05:
                        dirs[i] = 1
                elif dirs[i] == 1:
                    stars[i] += 0.1
                    if stars[i] >= 1.0:
                        stars[i] = 1.0
                        dirs[i] = -1
                else:
                    stars[i] -= 0.05
                    if stars[i] <= 0:
                        stars[i] = 0
                        dirs[i] = 0
                        
                val = stars[i]
                if base:
                    frame.append((int(base[0] * val), int(base[1] * val), int(base[2] * val)))
                else:
                    frame.append((int(255 * val), int(255 * val), int(255 * val)))
                    
            try:
                self._push(kb, frame)
            except OSError:
                self.running = False
                break
            time.sleep(self._get_sleep_time(0.05))

    def _loop_radar(self, kb: KeyboardRGB):
        base = self._get_base_color()
        if not base: base = (0, 255, 255)
        
        pos = 0.0
        while self.running:
            frame = []
            for i in range(NUM_LEDS):
                dist = abs(i - pos)
                if dist > NUM_LEDS / 2: # Wrap around
                    dist = NUM_LEDS - dist
                
                val = max(0.0, 1.0 - (dist / 10.0))
                frame.append((int(base[0] * val), int(base[1] * val), int(base[2] * val)))
                
            try:
                self._push(kb, frame)
            except OSError:
                self.running = False
                break
                
            if self.direction == 0:
                pos += 1.5
                if pos >= NUM_LEDS: pos = 0
            else:
                pos -= 1.5
                if pos < 0: pos = NUM_LEDS - 1
                
            time.sleep(self._get_sleep_time(0.03))

    def _loop_ripple(self, kb: KeyboardRGB):
        base = self._get_base_color()
        if not base: base = (255, 0, 255)
        
        ripples = [] # tuples of (center_idx, radius)
        
        while self.running:
            if random.random() < 0.1:
                ripples.append([random.randint(0, NUM_LEDS-1), 0.0])
                
            frame = [(0, 0, 0)] * NUM_LEDS
            
            new_ripples = []
            for r in ripples:
                center, rad = r
                
                # Draw ripple
                for i in range(NUM_LEDS):
                    dist = abs(i - center)
                    if abs(dist - rad) < 1.5:
                        # Inside ripple edge
                        intensity = max(0.0, 1.0 - (rad / 15.0))
                        frame[i] = (
                            min(255, frame[i][0] + int(base[0] * intensity)),
                            min(255, frame[i][1] + int(base[1] * intensity)),
                            min(255, frame[i][2] + int(base[2] * intensity))
                        )
                        
                rad += 0.8
                if rad < 20: # max radius
                    new_ripples.append([center, rad])
            ripples = new_ripples
            
            try:
                self._push(kb, frame)
            except OSError:
                self.running = False
                break
                
            time.sleep(self._get_sleep_time(0.04))
