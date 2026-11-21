# Ajazz AK820 Max Plus — USB HID Protocol Specification

Reverse-engineered from USB pcap captures and confirmed through live testing.

Provenance: captured from DeviceDriver.exe v1.0.4.6 using a Frida WriteFile hook, Nov 2026.

---

## 1. Device Identification

| Field             | Value              |
|-------------------|--------------------|
| Vendor ID         | `0x1A2C`           |
| Product ID (wired USB)      | `0xA036`     |
| Product ID (2.4 GHz dongle) | `0x8FFF`     |
| Target interface  | `0` (first HID interface) on Linux; `MI_00` on Windows |
| Windows device path (wired) | `hid#vid_1a2c&pid_a036&mi_00#...` |
| Linux device node | `/dev/hidraw*` (matched via `/sys/class/hidraw/`) |
| Report length     | **64 bytes** packet (fixed, all packets) |
| Windows write size | **65 bytes**: report ID `0x00` followed by the 64-byte packet |

The Windows PIDs above are from the vendor's `config.xml`. Earlier revisions of this document listed `0x8FFF` as wired and `0xA036` as the dongle; that was swapped and is corrected here.

The correct hidraw node is identified by walking `/sys/class/hidraw/hidraw*`, reading the `uevent` file for `HID_ID`, matching VID/PID, then extracting the interface number from the symlink path component matching `\d+:\d+\.(\d+)`.

---

## 2. Packet Structure

Every packet sent to the keyboard is exactly **64 bytes**. On Windows the packet is written as a 65-byte report with a leading report ID `0x00` (see §1).

```
Offset  Length  Description
------  ------  -----------
0       4       Magic header: AA 55 CC 33
4       1       Opcode (command identifier)
5       N       Payload (opcode-dependent)
5+N     R       Zero padding to fill 64 bytes
```

**Magic header** `AA 55 CC 33` must appear at the start of every packet. The keyboard silently ignores packets without it.

Helper (Python):
```python
MAGIC      = bytes([0xAA, 0x55, 0xCC, 0x33])
REPORT_LEN = 64

def _pkt(opcode: int, payload: bytes = b"") -> bytes:
    body = MAGIC + bytes([opcode]) + payload
    return body + bytes(REPORT_LEN - len(body))
```

---

## 3. Command Reference

### 3.1 Custom RGB Mode Initialisation — `0x07` (mode entry)

Must be sent before pushing any custom frame. Sets the keyboard into per-key RGB edit mode. The vendor app sends the same `07 17 04 03 00 07` payload.

```
Byte  Value   Description
----  -----   -----------
0-3   MAGIC
4     0x07    Opcode
5     0x17    Sub-command: enter custom mode
6     0x04    Brightness (max)
7     0x03    Speed (mid)
8     0x00    Direction (forward)
9     0x07    Color (RGB/full spectrum)
10    0x00    Padding
```

Full sequence to enter custom mode:
```python
kb._write(_pkt(0x07, bytes([0x17, 0x04, 0x03, 0x00, 0x07, 0x00])))
kb._write(_pkt(0x0B))   # begin edit
kb._write(_pkt(0x09))   # commit/apply
```

---

### 3.2 Hardware Animation Mode — `0x07` (mode config)

The same opcode `0x07` is used for both custom mode entry and hardware animation. The sub-command byte at offset 5 distinguishes them: `0x17` = custom mode, `0x00–0x12` = hardware animation mode ID.

```
Byte  Value     Description
----  -----     -----------
0-3   MAGIC
4     0x07      Opcode
5     mode_id   Animation mode (0x00–0x12, see §6)
6     bright    Brightness  0–4 (UI 1–5, see §8)
7     speed     Speed       0–4 (UI 1–5, see §8)
8     dir       Direction   0 = forward, 1 = reverse
9     color     Primary color (0x00–0x07, see §7)
10    color2    Secondary color (0x00–0x07) — used by Dual Wave (mode 9)
11-63 0x00      Padding
```

Example — set Horizontal Wave, full brightness, medium speed, RGB:
```python
packet = bytearray(64)
packet[0:4] = MAGIC
packet[4]   = 0x07
packet[5]   = 0     # mode id
packet[6]   = 4     # brightness
packet[7]   = 2     # speed
packet[8]   = 0     # direction
packet[9]   = 0x07  # color: rgb
os.write(fd, bytes(packet))
```

---

### 3.3 Begin Edit — `0x0B`

Signals the keyboard to open its frame buffer for writing. Send before the six frame packets.

```
Byte  Value   Description
----  -----   -----------
0-3   MAGIC
4     0x0B    Opcode
5-63  0x00    Padding
```

---

### 3.4 Commit / Apply Frame — `0x09`

Signals the keyboard to apply the frame buffer to the LEDs immediately (live preview, not persisted to flash). The same opcode prefixes the rhythm streaming channel (§3.14).

```
Byte  Value   Description
----  -----   -----------
0-3   MAGIC
4     0x09    Opcode
5-63  0x00    Padding
```

---

### 3.5 Persist to Flash — `0x0A`

Writes the current custom frame permanently to the keyboard's onboard flash memory. The vendor app sends this **once**. Sending it twice is harmless.

```
Byte  Value   Description
----  -----   -----------
0-3   MAGIC
4     0x0A    Opcode
5-63  0x00    Padding
```

```python
kb._write(_pkt(0x0A))
```

---

### 3.6 Heartbeat / Poll — `0x0E`

Must be sent at least once every **5 seconds** while streaming custom frames, otherwise the keyboard reverts to its default mode. The vendor app sends it roughly every 2–5 seconds. It is also used to poll for a response from the keyboard.

```
Byte  Value   Description
----  -----   -----------
0-3   MAGIC
4     0x0E    Opcode
5-63  0x00    Padding
```

**Reply format (partially known):** `AA 55 CC 33 0E 3x 03`. Byte 5 changed from `0x31` to `0x32` during one vendor session. It is probably a battery or state value, but this is not verified. The meaning of the reply is unknown (see §11).

---

### 3.7 Custom Frame Data — `0xF6`–`0xFB` (6 packets)

A single full RGB frame requires **6 consecutive packets**, opcodes `0xF6` through `0xFB`. Each packet carries the RGB data for **18 LEDs** (54 bytes), padded to 59 payload bytes.

```
Byte  Value          Description
----  -----          -----------
0-3   MAGIC
4     0xF6 .. 0xFB   Opcode (packet index 0–5)
5-58  RGB data       18 LEDs × 3 bytes = 54 bytes, then 5 bytes zero padding
59-63 0x00           Padding to reach 64 bytes total
```

#### LED encoding within a packet

Each LED is encoded as three consecutive bytes: **R, G, B** (0–254 each; 0xFF is reserved/avoid).

```
Payload offset  Content
--------------  -------
0               LED[n+0].R
1               LED[n+0].G
2               LED[n+0].B
3               LED[n+1].R
...
53              LED[n+17].B
54-58           0x00 padding
```

#### Packet → LED mapping

| Opcode | Payload offset | LED indices |
|--------|---------------|-------------|
| 0xF6   | 5–58          | 0–17        |
| 0xF7   | 5–58          | 18–35       |
| 0xF8   | 5–58          | 36–53       |
| 0xF9   | 5–58          | 54–71       |
| 0xFA   | 5–58          | 72–89       |
| 0xFB   | 5–58          | 90–107      |

#### Full frame transmission

```python
FRAME_BYTES = 324  # 108 LEDs × 3 bytes

opcodes = (0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFB)
for i, opcode in enumerate(opcodes):
    chunk = led_buffer[i * 54 : (i + 1) * 54]   # 54 bytes
    chunk += bytes(59 - len(chunk))               # pad to 59 bytes
    os.write(fd, _pkt(opcode, chunk))
    time.sleep(0.004)                             # 4 ms inter-packet delay
```

A ~4 ms delay between packets is recommended to prevent buffer overruns. For real-time audio reactive at 30 fps the delay can be reduced to 0 without data loss on most systems.

---

### 3.8 Key Assignment — `0x04`

Assigns one physical key's output on one layer.

```
Byte  Value     Description
----  -----     -----------
0-3   MAGIC
4     0x04      Opcode
5     layer     0x01 = top/base layer, 0x02 = Fn layer
6     src_hid   HID usage of the physical key (`code` in the vendor layout XML)
7     dst       Output code (see below)
8-63  0x00      Padding
```

`dst` values:
- HID usage for normal keys and modifiers (`0xE0`–`0xE7` are the modifier usages).
- `0x00`: default function (restore the key).
- `0x01`: disabled.
- Media/system codes: see §7.1.

Example — remap Q to A on the base layer:
```
04 01 14 04     layer 0x01, src 0x14 (Q), dst 0x04 (A)
```

Keys flagged `fnlayer_disable` in the vendor layout cannot be remapped on the Fn layer (see §5).

---

### 3.9 Macro / Shortcut Assignment — `0x00`, `0x01`, `0x02`

A macro (or shortcut) is sent as a sequence of packets: `0x00` (the macro body), then `0x01`, then `0x02` (empty).

#### `0x00` macro packet

```
Byte  Value     Description
----  -----     -----------
0-3   MAGIC
4     0x00      Opcode
5     layer     0x01 = top/base layer, 0x02 = Fn layer
6     src_hid   HID usage of the physical key being assigned
7     repeat    Repeat field (value 0x01 in the captured example; meaning not decoded)
8     n_events  Number of events that follow (n)
9+2i  code_i    HID usage of event i (i = 0 .. n-1)
10+2i flag_i    Event flags (see below)
```

Event flag byte:
- **bit 7**: `0` = key down, `1` = key up.
- **bits 0–6**: delay after the event, in 10 ms units (min `1`, max `127`, i.e. 10–1270 ms).

A single `0x00` packet holds at most **27 events** (27 × 2 = 54 bytes, offsets 9–62). Continuation for macros longer than 27 events is not known (see §11).

#### Shortcuts are macros

Shortcuts are encoded the same way. The example below is the event data for Select All (LCtrl + A):

```
e0 01   LCtrl down, 10 ms
04 01   A down, 10 ms
04 81   A up, 10 ms
e0 81   LCtrl up, 10 ms
```

#### Worked example

Raw bytes: `00 01 3a 01 0e 07 03 09 03 07 8d ...`

| Offset | Byte | Field | Decoded |
|--------|------|-------|---------|
| 4 | `00` | Opcode | `0x00` macro packet |
| 5 | `01` | layer | top/base layer |
| 6 | `3a` | src_hid | HID `0x3A` = F1 |
| 7 | `01` | repeat | `0x01` (meaning not decoded) |
| 8 | `0e` | n_events | 14 events follow (28 bytes) |
| 9–10 | `07 03` | event 1 | HID `0x07` (D), down, delay `0x03` = 30 ms |
| 11–12 | `09 03` | event 2 | HID `0x09` (F), down, delay 30 ms |
| 13–14 | `07 8d` | event 3 | HID `0x07` (D), up (`0x8D` bit 7 set), delay `0x0D` = 130 ms |
| 15+ | `...` | events 4–14 | Not included in the captured excerpt |

The key letters are from the standard HID keyboard usage table, not from the vendor capture.

After the `0x00` packet, the vendor app sends `0x01`, then `0x02`.

---

### 3.10 Reset All Key Assignments — `0x0F`

```
Byte  Value   Description
----  -----   -----------
0-3   MAGIC
4     0x0F    Opcode
5-63  0x00    Padding
```

Resets all key assignments on both layers to default. The vendor app sends this on profile switch, then replays the profile's non-default assignments (§3.8, §3.9).

---

### 3.11 Sleep Timer — `0x0C`

```
Byte  Value   Description
----  -----   -----------
0-3   MAGIC
4     0x0C    Opcode
5     timer   1 = 5 min, 2 = 15 min, 3 = 30 min, 4 = never
6-63  0x00    Padding
```

---

### 3.12 Key Response Time — `0x0D`

```
Byte  Value   Description
----  -----   -----------
0-3   MAGIC
4     0x0D    Opcode
5     gear    1, 2, or 3
6-63  0x00    Padding
```

Gear `1` is the fastest (wired latency 2–3 ms). The latency for gears `2` and `3` is not in the captured findings.

---

### 3.13 Fn Mode — `0x10`

```
Byte  Value   Description
----  -----   -----------
0-3   MAGIC
4     0x10    Opcode
5     mode    0 = normal mode, 1 = "Fn switch" (F-row default media vs F-keys)
6-63  0x00    Padding
```

---

### 3.14 Music / Screen Rhythm Stream — `0x09` + `0xF0`–`0xF5`

The vendor app's **Music rhythm** and **Screen rhythm** modes use a firmware-rendered streaming channel, not custom RGB frames. Each tick, the vendor app sends `0x09` followed by `0xF0`–`0xF5`.

```
Opcode       Payload    Description
------       -------    -----------
0x09         —          Channel prefix (same opcode as §3.4)
0xF0 .. 0xF5 54 bytes   Stream data (one packet per opcode)
```

In music mode the `0xF0`–`0xF5` payload looks like per-LED or per-column levels, not RGB values. This is observed only; the encoding is not decoded. The tick rate is not in the captured findings.

---

## 4. Custom RGB Workflow

Complete sequence to display a custom frame:

```
1.  _pkt(0x07, [0x17, 0x04, 0x03, 0x00, 0x07, 0x00])   enter custom mode
2.  _pkt(0x0B)                                           begin edit
3.  _pkt(0x09)                                           apply (initial)
4.  _pkt(0xF6, <18 LEDs>)                                frame packet 1/6
5.  _pkt(0xF7, <18 LEDs>)                                frame packet 2/6
6.  _pkt(0xF8, <18 LEDs>)                                frame packet 3/6
7.  _pkt(0xF9, <18 LEDs>)                                frame packet 4/6
8.  _pkt(0xFA, <18 LEDs>)                                frame packet 5/6
9.  _pkt(0xFB, <18 LEDs>)                                frame packet 6/6
```

For subsequent frame updates (e.g. animation loop), only steps 4–9 are needed. Steps 1–3 are a one-time initialisation.

To persist the frame to flash (survives power cycle), additionally send:
```
10. _pkt(0x0A)   — save (the vendor app sends this once)
```

For long-running streams, send `_pkt(0x0E)` every 5 seconds as a keepalive.

---

## 5. LED Index Map

108 LEDs total, indexed 0–107. The mapping below was determined empirically by lighting one LED at a time and recording the physical key. The vendor layout file `layouts/kb-k600t.xml` agrees: its `key_index` equals the LED index used in this frame buffer.

Indices not listed here correspond to unmapped positions (no physical key or no LED).

| Index | Key        | Index | Key        | Index | Key       |
|-------|------------|-------|------------|-------|-----------|
| 3     | F12        | 4     | F11        | 5     | F10       |
| 6     | F9         | 7     | F8         | 8     | F7        |
| 9     | F6         | 10    | F5         | 11    | F4        |
| 12    | F3         | 13    | F2         | 14    | F1        |
| 15    | Esc        | 16    | `          | 17    | 1         |
| 18    | 2          | 19    | 3          | 20    | 4         |
| 21    | 5          | 22    | 6          | 23    | 7         |
| 24    | 8          | 25    | 9          | 26    | 0         |
| 27    | -          | 28    | =          | 29    | BackSpace |
| 31    | Home       | 32    | PgUp       | 41    | PgDn      |
| 42    | End        | 43    | Del        | 44    | \         |
| 45    | ]          | 46    | [          | 47    | p         |
| 48    | o          | 49    | i          | 50    | u         |
| 51    | y          | 52    | t          | 53    | r         |
| 54    | e          | 55    | w          | 56    | q         |
| 57    | Tab        | 58    | CapsLock   | 59    | a         |
| 60    | s          | 61    | d          | 62    | f         |
| 63    | g          | 64    | h          | 65    | j         |
| 66    | k          | 67    | l          | 68    | ;         |
| 69    | '          | 70    | Enter      | 78    | Up        |
| 79    | RShift     | 80    | /          | 81    | .         |
| 82    | ,          | 83    | m          | 84    | n         |
| 85    | b          | 86    | v          | 87    | c         |
| 88    | x          | 89    | z          | 90    | LShift    |
| 91    | LCtrl      | 92    | Win        | 93    | LAlt      |
| 94    | Space      | 95    | RAlt       | 97    | Fn        |
| 98    | RCtrl      | 99    | Left       | 100   | Down      |
| 101   | Right      |       |            |       |           |

**Notes:**
- Indices 0–2, 30, 33–40, 71–77, 96, 102–107 are either unused circuit positions or not physically present on this keyboard model.
- LED color value `0xFF` (255) should be avoided; use `0xFE` (254) as the maximum. Observed to cause incorrect colors on some firmware versions.
- Keys flagged `fnlayer_disable` in the vendor layout (cannot be remapped on the Fn layer): `` ` `` `1` `-` `=` Backspace `\` `Q` `W` `E` `R` `X` Space Up Left Down Right.

---

## 6. Hardware Animation Modes

Sent in byte 5 of the `0x07` config packet. IDs are decimal. The "Vendor name" column is the name shown in the vendor app where known. Where the vendor name and the earlier label differ, the vendor name comes from the captured findings, and the earlier label is kept for continuity.

| ID | Name (earlier label) | Vendor name       | Controls       |
|----|----------------------|-------------------|----------------|
| 0  | Horizontal Wave      | Left and right ripples | B S D C    |
| 1  | Chaos                | Starry dots       | B S            |
| 2  | Vertical Wave        | Up and Down Ripples | B S D C      |
| 3  | Beam                 | Bidirectional ejection | B S D C   |
| 4  | Cycles               | Spectral cycle    | B S            |
| 5  | Ripples              | Kaleidoscope      | B S D C        |
| 6  | Static               | Static            | B C            |
| 7  | Breathing            | Overall breathing | B S C          |
| 8  | Cross Waves          | Cross operation   | B S C          |
| 9  | Dual Wave            | —                 | B S D C C2     |
| 10 | Key Glow             | Single key breathing | B S C       |
| 11 | Key Ripple           | Picture scroll    | B S C          |
| 12 | Snake                | —                 | B S C          |
| 13 | Spiral               | —                 | B S D C        |
| 14 | Split Flow           | Top three bottom three | B S C     |
| 15 | Meteor Shower        | Rain falling      | B S C          |
| 16 | Windmill             | Windmill          | B S C          |
| 17 | Sine Wave            | Sine wave         | B S C          |
| 18 | Row Sweep            | Galloping horse   | B S D C        |

**Controls key:** B = Brightness, S = Speed, D = Direction, C = Color, C2 = Secondary Color

Modes 19–23 exist in the hardware but produce undefined/non-functional output on this firmware version.

### 6.1 Vendor effect names → mode id

| Vendor name (DeviceDriver.exe) | Mode ID |
|--------------------------------|---------|
| Left and right ripples         | `0x00`  |
| Starry dots                    | `0x01`  |
| Up and Down Ripples            | `0x02`  |
| Bidirectional ejection         | `0x03`  |
| Spectral cycle                 | `0x04`  |
| Kaleidoscope                   | `0x05`  |
| Static                         | `0x06`  |
| Overall breathing              | `0x07`  |
| Cross operation                | `0x08`  |
| Single key breathing           | `0x0A`  |
| Picture scroll                 | `0x0B`  |
| Top three bottom three         | `0x0E`  |
| Rain falling                   | `0x0F`  |
| Windmill                       | `0x10`  |
| Sine wave                      | `0x11`  |
| Galloping horse                | `0x12`  |
| Music rhythm                   | Host stream: `0x09` + `0xF0`–`0xF5` (§3.14) |
| Screen rhythm                  | Host stream: `0x09` + `0xF0`–`0xF5` (§3.14) |
| Custom                         | `0x17`  |

---

## 7. Color Values

Sent in byte 9 (primary) and byte 10 (secondary) of the `0x07` config packet.

| Value | Color  |
|-------|--------|
| 0x00  | Red    |
| 0x01  | Green  |
| 0x02  | Blue   |
| 0x03  | Yellow |
| 0x04  | Pink   |
| 0x05  | Cyan   |
| 0x06  | White  |
| 0x07  | RGB (full spectrum / rainbow) |

### 7.1 Media / system key codes

Used as `dst` in the `0x04` key assignment (§3.8). Listed in vendor icon-row order.

| Code | Function      | Code | Function      |
|------|---------------|------|---------------|
| `F9` | My Computer   | `EE` | Play/Pause    |
| `F2` | Calculator    | `EC` | Stop          |
| `F0` | Mail          | `ED` | Previous      |
| `E8` | Media Player  | `EF` | Next          |
| `F1` | Web Home      | `E9` | Volume Down   |
| `F6` | Web Refresh   | `EA` | Volume Up     |
| `F5` | Web Stop      | `EB` | Mute          |
| `F3` | Web Back      | `F8` | Favorites     |
| `F4` | Web Forward   | `F7` | Web Search    |

---

## 8. Parameter Ranges

| Parameter  | Byte min | Byte max | Notes                                              |
|------------|----------|----------|----------------------------------------------------|
| Brightness | 0        | 4        | UI levels 1–5 map to byte 0–4 (UI 1 = byte 0, UI 5 = byte 4) |
| Speed      | 0        | 4        | UI levels 1–5 map to byte 0–4 (UI 1 = byte 0, UI 5 = byte 4) |
| Direction  | 0        | 1        | 0 = forward, 1 = reverse                           |
| Color      | 0        | 7        | See §7                                             |
| LED value  | 0        | 254      | Per channel (R/G/B); avoid 255                     |

---

## 9. Audio Reactive — Implementation Notes

Host-side implementation: the host continuously streams custom frames at ~30 fps using opcodes `0xF6`–`0xFB`, with the LED colors computed from live audio analysis.

The vendor app's own Music rhythm and Screen rhythm modes do not use this path. They use the firmware-rendered `0x09` + `0xF0`–`0xF5` stream (§3.14).

### Volume mode

```
RMS = sqrt(mean(samples²))
brightness = clamp(RMS × sensitivity × 254, 0, 254)
led_buffer = bytes([brightness]) × 324   # all LEDs same brightness
```

### Spectrum mode (FFT)

Audio captured at 44100 Hz, 1024-sample blocks with Hann window:

```
fft = |RFFT(samples × hann_window)| / block_size

Frequency resolution: 44100 / 1024 ≈ 43 Hz per bin

Bass   bins 1–3   → ~43–129 Hz    (kick drums, deep bass)
Mid    bins 4–20  → ~172–860 Hz   (vocals, guitars)
Treble bins 21–100 → ~903–4300 Hz (hi-hats, cymbals, synths)
```

Each band drives a 36-LED zone (108 LEDs ÷ 3 bands). Amplitude uses instant-attack / smooth-decay envelope:

```
if target > smoothed:
    smoothed = target          # instant attack
else:
    smoothed *= falloff        # 0.80–0.85 recommended
```

Heartbeat (`0x0E`) must be sent every 5 seconds during streaming or the keyboard exits custom mode.

---

## 10. Timing Summary

| Operation              | Recommended delay  |
|------------------------|--------------------|
| Inter-packet (frames)  | 4 ms               |
| Inter-packet (realtime)| 0 ms (acceptable)  |
| Mode init sequence     | 50 ms between cmds |
| Heartbeat interval     | ≤ 5 seconds        |

---

## 11. Known Unknowns

- **`0x0E` reply meaning** — the reply format `AA 55 CC 33 0E 3x 03` is known, but byte 5 is undecoded. It changed from `0x31` to `0x32` during one session; the battery/state guess is unverified.
- **Macro continuation for more than 27 events** — a `0x00` packet holds at most 27 events. How longer macros continue (the `0x01` packet may carry them) is not known.
- **LED value `0xFF`** — observed to produce incorrect output on some packets. Use `0xFE` as the practical maximum.
- **Rhythm stream payload (`0xF0`–`0xF5`)** — the per-LED or per-column encoding and the tick rate are not decoded.
- **`0x0D` gears 2 and 3** — only gear 1 (fastest, wired 2–3 ms) is characterised.
- **`0x00` macro `repeat` field** — the value is recorded (`0x01` in the example), but its meaning is not decoded.
- **Byte 10 in `0x07` (secondary color)** — confirmed writable; whether the keyboard firmware uses it for Dual Wave is unverified. It is harmless to send.
- **Indices 0–2, 30, 33–40, 71–77, 96, 102–107** — these positions in the LED buffer appear to be unused circuit traces or non-addressable positions. Writing any value to them has no visible effect.
- **Modes 19–23** — present in the hardware mode register but produce no reliable output on the tested firmware.

---

## 12. Software-Only Features of the Vendor App

These features are handled by the host app and send no keyboard packets:

- Win-key lock
- Alt+F4 lock
- Alt+Tab lock
- Profiles (the app sends `0x0F` and replays assignments on switch; see §3.10)
- Macro library
- Auto-run
