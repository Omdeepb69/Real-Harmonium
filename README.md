# Real Harmonium 🎹

> A tilt-controlled harmonium for the Linux terminal.

Tilt your laptop screen forward and back — like pumping real harmonium bellows — while playing notes on your keyboard. The screen tilting **is** the instrument. Hold still and the sound dies. Keep moving and the notes sing.

Built with Python, curses, numpy, pygame, and OpenCV.

```
  ╔══════════════════════════════════════════════════════════════════════════╗
  ║  *                          HARMONIUM                               *   ║
  ╠══════════════════════════════════════════════════════════════════════════╣
  ║  BELLOWS  [################................]  62%   b +14.2 deg         ║
  ╠══════════════════════════════════════════════════════════════════════════╣
  ║        +--+ +--+   +--+ +--+ +--+   +--+ +--+                          ║
  ║        |C#| |D#|   |F#| |G#| |A#|   |C#| |D#|                          ║
  ║        +--+ +--+   +--+ +--+ +--+   +--+ +--+                          ║
  ║    +---++---++---++---++---++---++---++---++---+                        ║
  ║    | C || D || E || F || G || A || B || C || D |                        ║
  ║    |   ||   ||   ||   ||   ||   ||   ||   ||   |                        ║
  ║    | A || S || D || F || G || H || J || K || L |                        ║
  ║    +---++---++---++---++---++---++---++---++---+                        ║
  ╠══════════════════════════════════════════════════════════════════════════╣
  ║  >> breathing       * C4  E4  G4                          q: quit       ║
  ╚══════════════════════════════════════════════════════════════════════════╝
```

---

## Install

### One command (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/Omdeepb69/Real-Harmonium/main/install.sh | bash
```

This handles everything — PPA key, repository, and package install.

### Manual

```bash
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 38AA3C5C21B94B38
sudo add-apt-repository ppa:omdeepb69/realhm -y
sudo apt update
sudo apt install realharmonium -y
```

### From source

```bash
git clone https://github.com/Omdeepb69/Real-Harmonium.git
cd Real-Harmonium
pip3 install numpy pygame opencv-python
pip3 install -e .
```

---

## Run

```bash
realhm
```

The terminal goes fullscreen. You're playing.

---

## How to play

### The bellows — the whole point

A real harmonium makes no sound without pumping air through its bellows. This instrument works exactly the same way.

| Action | Effect |
|---|---|
| Tilt screen forward/back | Pumps bellows → sound |
| Tilt fast | More air → louder |
| Hold still | Pressure bleeds → silence |
| Cover webcam | No motion detected → silence |

You must **keep moving** the screen rhythmically to sustain notes — just like a real harmonium player pumps the bellows with one hand while playing with the other.

### Keyboard layout

```
Black keys:   W    E         T    Y    U         O    P
             C#   D#        F#   G#   A#        C#   D#

White keys:   A    S    D    F    G    H    J    K    L    ;
             C    D    E    F    G    A    B    C    D    E
```

### Controls

| Key | Action |
|---|---|
| `q` | Quit |
| `Space` | Bellows pump (mouse/desktop mode) |

---

## Tilt detection

The app automatically detects the best available sensor on your machine and falls back gracefully:

```
1. IIO sysfs accelerometer   /sys/bus/iio/devices/iio:device*
   Most modern laptops (Dell, Lenovo, ASUS, HP)

2. hp_accel / lis3lv02d      /sys/devices/platform/.../position
   HP laptops with platform accelerometer driver

3. evdev input subsystem     /dev/input/event*
   Older ThinkPads, some Chromebooks

4. Webcam optical flow       /dev/video0 or /dev/video1
   Uses Lucas-Kanade point tracking to measure screen motion.
   Works on any laptop with a webcam. Asked before use.
   Camera feed is processed locally — never saved or transmitted.

5. Mouse / Space bar         Universal fallback
   Drag mouse up/down outside the keys, or hold Space.
```

On first run, if no hardware accelerometer is found, the app will ask:
```
  Use webcam for tilt detection? [y/N]
```

Type `y` for the best experience on laptops without exposed accelerometer drivers.

---

## Sound design

Each key plays **5 stacked oscillators** replicating the physical reed structure of a harmonium:

| Layer | Waveform | Detune | Purpose |
|---|---|---|---|
| Reed 1 | Sawtooth | 0¢ | Main fundamental tone |
| Reed 2 | Sawtooth | +7¢ | Upper reed shimmer (beating frequency) |
| Reed 3 | Sawtooth | −5¢ | Lower reed warmth |
| Reed 4 | Sawtooth | +1200¢ | Octave reed brightness |
| Reed 5 | Square | 0¢ | Nasal body character |

Signal chain: oscillators → tanh waveshaper (reed warmth) → convolver reverb (wooden cabinet impulse) → dynamics compressor → output.

An always-on **Sa drone** (C3 + G3 + C4) runs continuously, its volume tied entirely to bellows level — it breathes with the instrument.

### Bellows physics

```
Moving screen  →  fills bellows fast   (FILL_RATE  = 3.5)
Still screen   →  bleeds slowly        (BLEED_RATE = 0.55/s)
Full bellows lasts ~1.5 seconds before going silent
One firm pump fills bellows in ~0.3 seconds
```

---

## Requirements

- Ubuntu 20.04+ (Noble/Jammy/Focal)
- Python 3.10+
- `numpy`, `pygame` (installed automatically)
- `opencv-python` (for webcam mode — `pip3 install opencv-python`)
- A laptop with a webcam, or a hardware accelerometer

---

## Updating

```bash
sudo apt update
sudo apt upgrade realharmonium
```

---

## Building from source / contributing

```bash
git clone https://github.com/Omdeepb69/Real-Harmonium.git
cd Real-Harmonium

# Install deps
pip3 install numpy pygame opencv-python

# Run directly
pip3 install -e .
realhm

# Build .deb
sudo apt install devscripts debhelper dh-python python3-all python3-setuptools
debuild -S -sa
```

---

## Project structure

```
realharmonium/
├── realharmonium/
│   ├── __main__.py       entry point — boots engines, launches UI
│   ├── sound_engine.py   5-layer reed synthesis (numpy + pygame)
│   ├── tilt_engine.py    sensor detection + bellows physics
│   └── ui.py             full-terminal curses keyboard interface
├── debian/               .deb packaging files
├── install.sh            one-command installer
└── setup.py / pyproject.toml
```

---

## License

MIT — do whatever you want with it.

---

<div align="center">
  Made with ♪ by <a href="https://github.com/Omdeepb69">Omdeep Borkar</a>
</div>