# realharmonium 🎹

**A tilt-controlled harmonium for the Linux terminal.**

Tilt your laptop screen forward and back — like pumping real harmonium bellows —
while playing notes on your keyboard. Built with Python, curses, numpy, and pygame.

```
  ╔══════════════════════════════════════════════════════════════════════════╗
  ║  ✦                          HARMONIUM                               ✦   ║
  ╠══════════════════════════════════════════════════════════════════════════╣
  ║  BELLOWS  [████████████████░░░░░░░░░░░░░░░░]  62%   β +14.2°           ║
  ╠══════════════════════════════════════════════════════════════════════════╣
  ║        ┌──┐ ┌──┐   ┌──┐ ┌──┐ ┌──┐   ┌──┐ ┌──┐                        ║
  ║        │C#│ │D#│   │F#│ │G#│ │A#│   │C#│ │D#│                        ║
  ║        └──┘ └──┘   └──┘ └──┘ └──┘   └──┘ └──┘                        ║
  ║    ┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐                     ║
  ║    │ C ││ D ││ E ││ F ││ G ││ A ││ B ││ C ││ D │                     ║
  ║    │   ││   ││   ││   ││   ││   ││   ││   ││   │                     ║
  ║    │ A ││ S ││ D ││ F ││ G ││ H ││ J ││ K ││ L │                     ║
  ║    └───┘└───┘└───┘└───┘└───┘└───┘└───┘└───┘└───┘                     ║
  ╠══════════════════════════════════════════════════════════════════════════╣
  ║  [DRONE: ○ OFF]  d:toggle    ♪ C4  E4  G4           q: quit            ║
  ╚══════════════════════════════════════════════════════════════════════════╝
```

---

## Install

### Via apt (recommended — once PPA is set up)

```bash
sudo add-apt-repository ppa:realharmonium/realharmonium
sudo apt update
sudo apt install realharmonium
```

### Via pip

```bash
pip3 install realharmonium
```

### From source

```bash
git clone https://github.com/realharmonium/realharmonium
cd realharmonium
pip3 install -e .
```

### Quick script

```bash
curl -fsSL https://realharmonium.dev/install.sh | bash
```

---

## Run

```bash
realhm
```

That's it. The terminal goes fullscreen and you're playing.

---

## How to play

### The bellows (the whole point)

A real harmonium makes no sound without pumping air through its bellows.
This instrument works the same way:

| Input | Effect |
|---|---|
| **Tilt screen** forward/back | Pumps bellows → enables sound |
| Hold still | Bellows lose pressure → notes fade |
| Fast tilt | More air = louder |

**On a laptop with accelerometer** (most modern laptops):
The IIO sensor is read directly from `/sys/bus/iio/devices/`. No sudo needed.

**On desktop or unsupported laptop:**
- Drag the mouse **up and down** anywhere outside the keys
- Or hold the **Space bar** to keep air flowing

### Keys

```
White keys:   A  S  D  F  G  H  J  K  L  ;
Notes:        C  D  E  F  G  A  B  C  D  E

Black keys:   W  E     T  Y  U     O  P
Notes:       C# D#   F# G# A#   C# D#
```

### Commands

| Key | Action |
|---|---|
| `d` | Toggle Sa drone (C4 + G4 bass drone) |
| `q` | Quit |
| `Space` | Bellows pump (desktop mode) |

---

## Sound design

Each key plays **5 stacked oscillators** to replicate the physical reed structure
of a harmonium:

| Layer | Waveform | Detune | Purpose |
|---|---|---|---|
| Reed 1 | Sawtooth | 0¢ | Main fundamental tone |
| Reed 2 | Sawtooth | +7¢ | Upper reed shimmer (beating) |
| Reed 3 | Sawtooth | −5¢ | Lower reed (warmth) |
| Reed 4 | Sawtooth | +1200¢ | Octave reed (brightness) |
| Reed 5 | Square | 0¢ | Nasal body character |

All layers pass through a tanh waveshaper for reed warmth, then a convolver
reverb simulating a wooden cabinet, then a dynamics compressor.

---

## Sensor detection

```
/sys/bus/iio/devices/iio:device*/
  ├── name              ← must contain "accel"
  ├── in_accel_x_raw
  ├── in_accel_y_raw    ← pitch (front/back tilt)
  ├── in_accel_z_raw
  └── in_accel_scale    ← unit conversion (m/s² per LSB)
```

Tested on: Lenovo ThinkPad X1, Dell XPS, ASUS ZenBook, HP EliteBook.
If your laptop sensor isn't detected, open an issue with `ls /sys/bus/iio/devices/`.

---

## Building the .deb

```bash
bash scripts/build_deb.sh
sudo dpkg -i ../realharmonium_1.0.0-1_all.deb
```

To publish on Launchpad PPA so `sudo apt install realharmonium` works globally,
see the instructions printed by `build_deb.sh`.

---

## License

MIT
