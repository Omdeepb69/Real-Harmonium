"""
sound_engine.py — Harmonium reed synthesis
Generates multi-layer sawtooth+square oscillator stacks,
identical to the Web Audio engine in the original HTML version.
"""

import numpy as np
import threading
import time

try:
    import pygame
    import pygame.mixer
    import pygame.sndarray
    PYGAME_OK = True
except ImportError:
    PYGAME_OK = False

SAMPLE_RATE = 44100
BUFFER_SIZE = 512
MAX_POLYPHONY = 16

# ── Reed detune map (cents) ──────────────────────────────────────────────────
# Harmonium has multiple physical reeds per key — slight manufacturing
# variance causes beating, which is the signature shimmer of the instrument.
REED_LAYERS = [
    # (wave_type, cents_detune, amplitude)
    ("saw",    0.0,   0.40),   # Reed 1: main fundamental
    ("saw",   +7.0,   0.26),   # Reed 2: upper reed (+7¢ shimmer)
    ("saw",   -5.0,   0.18),   # Reed 3: lower reed (-5¢)
    ("saw", +1200.0,  0.10),   # Reed 4: octave above (softer)
    ("square", 0.0,   0.03),   # Reed 5: nasal body
]

ATTACK_S  = 0.075   # 75ms — valve opens
RELEASE_S = 0.35    # 350ms — valve closes, pressure bleeds


def cents_to_ratio(cents: float) -> float:
    return 2.0 ** (cents / 1200.0)


def make_reed_tone(freq: float, duration: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """
    Synthesise one harmonium reed stack for `freq` Hz lasting `duration` seconds.
    Returns float32 mono array in [-1, 1].
    """
    n = int(sample_rate * duration)
    t = np.linspace(0, duration, n, endpoint=False, dtype=np.float64)
    signal = np.zeros(n, dtype=np.float64)

    for wave_type, cents, amp in REED_LAYERS:
        f = freq * cents_to_ratio(cents)
        phase = 2.0 * np.pi * f * t

        if wave_type == "saw":
            # Bandlimited sawtooth via additive synthesis (8 harmonics)
            wave = np.zeros(n, dtype=np.float64)
            for k in range(1, 9):
                if f * k > sample_rate / 2:
                    break
                wave += ((-1) ** (k + 1)) / k * np.sin(k * phase)
            wave *= (2.0 / np.pi)
        else:  # square
            wave = np.zeros(n, dtype=np.float64)
            for k in range(1, 8, 2):
                if f * k > sample_rate / 2:
                    break
                wave += (1.0 / k) * np.sin(k * phase)
            wave *= (4.0 / np.pi)

        signal += amp * wave

    # Soft waveshaper (mild tanh saturation — reed warmth)
    signal = np.tanh(signal * 1.4) / np.tanh(1.4)

    # Normalise
    peak = np.max(np.abs(signal))
    if peak > 0:
        signal /= peak * 1.1

    return signal.astype(np.float32)


def apply_envelope(signal: np.ndarray, attack_s: float, release_s: float,
                   sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    n = len(signal)
    env = np.ones(n, dtype=np.float32)
    atk = min(int(attack_s * sample_rate), n)
    rel = min(int(release_s * sample_rate), n)

    # Attack ramp
    env[:atk] = np.linspace(0.0, 1.0, atk)
    # Release ramp
    if rel > 0:
        env[n - rel:] = np.linspace(1.0, 0.0, rel)

    return signal * env


def make_pygame_sound(signal: np.ndarray) -> "pygame.mixer.Sound":
    """Convert float32 mono array → stereo int16 pygame Sound."""
    s16 = (signal * 32000).astype(np.int16)
    stereo = np.column_stack([s16, s16])            # mono → stereo
    return pygame.sndarray.make_sound(stereo)


# ── Prebuilt note cache ───────────────────────────────────────────────────────

_sound_cache: dict = {}   # note_name → pygame.mixer.Sound
_cache_lock = threading.Lock()


def _preload_note(note_name: str, freq: float) -> None:
    dur = 3.0   # generate 3s of reed tone (looped for sustain)
    raw = make_reed_tone(freq, dur)
    env = apply_envelope(raw, ATTACK_S, RELEASE_S)
    snd = make_pygame_sound(env)
    with _cache_lock:
        _sound_cache[note_name] = snd


def preload_all_notes(note_map: dict) -> None:
    """Preload sounds in background threads."""
    threads = []
    for name, freq in note_map.items():
        t = threading.Thread(target=_preload_note, args=(name, freq), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


def get_sound(note_name: str) -> "pygame.mixer.Sound | None":
    with _cache_lock:
        return _sound_cache.get(note_name)


# ── Playback engine ───────────────────────────────────────────────────────────

class SoundEngine:
    """
    Manages note on/off with bellows-driven volume.
    bellows_level: float [0.0, 1.0] — set externally by tilt engine.

    Drone is ALWAYS running (loops silently when bellows = 0).
    Its volume is driven entirely by bellows_level — no manual toggle.
    """

    def __init__(self):
        self.bellows_level: float = 0.0
        self._channels: dict = {}   # note_name -> pygame.Channel
        self._lock = threading.Lock()
        self._drone_channel = None
        self._drone_sound = None

    def init(self):
        if not PYGAME_OK:
            return
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, BUFFER_SIZE)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(MAX_POLYPHONY + 4)

    def start_drone(self):
        """Start the always-on Sa drone (C3 + G3 + C4). Called once at boot."""
        if not PYGAME_OK or self._drone_channel:
            return
        n = int(SAMPLE_RATE * 4.0)
        t = np.linspace(0, 4.0, n, endpoint=False, dtype=np.float64)
        drone_sig = np.zeros(n, dtype=np.float64)
        for freq, amp in [(130.81, 0.45), (196.00, 0.28), (261.63, 0.18)]:
            for k in range(1, 7):
                if freq * k < SAMPLE_RATE / 2:
                    drone_sig += amp / k * np.sin(2 * np.pi * freq * k * t)
        # Slight detune layer for shimmer
        drone_sig += 0.12 * np.sin(2 * np.pi * 130.81 * (2 ** (7/1200)) * t)
        drone_sig = np.tanh(drone_sig * 1.2) / np.tanh(1.2)
        peak = np.max(np.abs(drone_sig))
        if peak > 0:
            drone_sig /= peak * 1.15
        snd = make_pygame_sound(drone_sig.astype(np.float32))
        snd.set_volume(0.0)   # starts silent — bellows brings it alive
        ch = pygame.mixer.find_channel(True)
        if ch:
            ch.play(snd, loops=-1)
            self._drone_channel = ch
            self._drone_sound = snd

    def note_on(self, note_name: str):
        if not PYGAME_OK:
            return
        snd = get_sound(note_name)
        if snd is None:
            return
        vol = max(0.05, self.bellows_level)
        snd.set_volume(vol)
        ch = pygame.mixer.find_channel(True)
        if ch:
            ch.play(snd)
            with self._lock:
                self._channels[note_name] = ch

    def note_off(self, note_name: str):
        if not PYGAME_OK:
            return
        with self._lock:
            ch = self._channels.pop(note_name, None)
        if ch:
            ch.fadeout(300)

    def update_bellows(self, level: float):
        """Called continuously — adjusts volume of all active channels AND drone."""
        self.bellows_level = level
        if not PYGAME_OK:
            return
        vol = max(0.0, min(1.0, level))
        with self._lock:
            for ch in self._channels.values():
                if ch.get_busy():
                    ch.set_volume(vol)
        # Drone volume tracks bellows (subtle undertone)
        if self._drone_channel and self._drone_channel.get_busy():
            self._drone_channel.set_volume(vol * 0.45)

    def is_drone_on(self) -> bool:
        return self._drone_channel is not None
