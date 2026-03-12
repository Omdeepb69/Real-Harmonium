"""
ui.py — Full-terminal harmonium interface using curses

Changes from v1:
  - Drone removed from status bar / manual toggle — it is ALWAYS on,
    volume driven purely by laptop tilt (bellows level).
  - Key release: uses a held-key timeout approach (curses terminals don't
    fire key-up events; we detect release when a key stops auto-repeating).
  - 'd' key binding removed; status bar simplified.
"""

import curses
import time
import threading


# ── Note layout ────────────────────────────────────────────────────────────────

NOTE_LAYOUT = [
    # (name, freq,    type,  keyboard_key)
    ("C4",  261.63, "white", "a"),
    ("C#4", 277.18, "black", "w"),
    ("D4",  293.66, "white", "s"),
    ("D#4", 311.13, "black", "e"),
    ("E4",  329.63, "white", "d"),
    ("F4",  349.23, "white", "f"),
    ("F#4", 369.99, "black", "t"),
    ("G4",  392.00, "white", "g"),
    ("G#4", 415.30, "black", "y"),
    ("A4",  440.00, "white", "h"),
    ("A#4", 466.16, "black", "u"),
    ("B4",  493.88, "white", "j"),
    ("C5",  523.25, "white", "k"),
    ("C#5", 554.37, "black", "o"),
    ("D5",  587.33, "white", "l"),
    ("D#5", 622.25, "black", "p"),
    ("E5",  659.25, "white", ";"),
]

WHITE_NOTES = [(n, f, k) for n, f, t, k in NOTE_LAYOUT if t == "white"]
BLACK_NOTES = [(n, f, k) for n, f, t, k in NOTE_LAYOUT if t == "black"]

KEY_MAP = {k: (n, f) for n, f, t, k in NOTE_LAYOUT}

BLACK_OVER_WHITE = {
    "C#4": 0, "D#4": 1,
    "F#4": 3, "G#4": 4, "A#4": 5,
    "C#5": 7, "D#5": 8,
}

# How long (seconds) after the last keydown event before we consider the key released.
# Terminal key-repeat fires every ~30ms; 90ms is a safe release threshold.
KEY_RELEASE_TIMEOUT = 0.09


# ── Color pair IDs ─────────────────────────────────────────────────────────────
CP_BRASS_ON_DARK  = 1
CP_WHITE_KEY      = 2
CP_WHITE_KEY_ACT  = 3
CP_BLACK_KEY      = 4
CP_BLACK_KEY_ACT  = 5
CP_METER_FILL     = 6
CP_METER_EMPTY    = 7
CP_STATUS         = 8
CP_HEADER         = 9
CP_DIM            = 10
CP_NOTE_PILL      = 11


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_BRASS_ON_DARK,  178, -1)
    curses.init_pair(CP_WHITE_KEY,      232, 255)
    curses.init_pair(CP_WHITE_KEY_ACT,  232, 220)
    curses.init_pair(CP_BLACK_KEY,      255, 232)
    curses.init_pair(CP_BLACK_KEY_ACT,  220, 236)
    curses.init_pair(CP_METER_FILL,     220,  88)
    curses.init_pair(CP_METER_EMPTY,    240, 235)
    curses.init_pair(CP_STATUS,         245,  -1)
    curses.init_pair(CP_HEADER,         220,  52)
    curses.init_pair(CP_DIM,            238,  -1)
    curses.init_pair(CP_NOTE_PILL,      178,  52)


class HarmoniumUI:

    def __init__(self, sound_engine, tilt_engine):
        self.sound = sound_engine
        self.tilt  = tilt_engine

        # key_char -> timestamp of last keydown event
        self._key_last_seen: dict = {}
        # key_char -> bool (is considered held right now)
        self._key_held: dict = {}

        self.active_notes: set = set()

        self._prev_mouse_y = None
        self._quit = False

    # ── entry ──────────────────────────────────────────────────────────────────

    def run(self):
        curses.wrapper(self._main)

    def _main(self, stdscr):
        self.scr = stdscr
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)

        try:
            init_colors()
        except Exception:
            pass

        try:
            curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        except Exception:
            pass

        self._draw_loading()
        time.sleep(0.2)
        self._run_loop()

    def _run_loop(self):
        while not self._quit:
            h, w = self.scr.getmaxyx()
            self.scr.erase()

            self._draw_frame(h, w)
            self._draw_bellows(h, w)
            self._draw_keyboard(h, w)
            self._draw_status(h, w)

            self.scr.refresh()

            self._handle_input()
            self._check_key_releases()
            time.sleep(0.033)

    # ── key release detection ──────────────────────────────────────────────────

    def _check_key_releases(self):
        """
        Curses gives no key-up events. We timestamp every keydown.
        If KEY_RELEASE_TIMEOUT passes with no repeat, the key was released.
        """
        now = time.monotonic()
        released = [k for k, ts in self._key_last_seen.items()
                    if now - ts > KEY_RELEASE_TIMEOUT]
        for k in released:
            del self._key_last_seen[k]
            if self._key_held.pop(k, False):
                self._do_note_off(k)

    def _do_note_on(self, ch):
        if ch not in KEY_MAP:
            return
        note_name, freq = KEY_MAP[ch]
        if not self._key_held.get(ch, False):
            self._key_held[ch] = True
            self.active_notes.add(note_name)
            if self.tilt.mode == "mouse":
                self.tilt.mouse_delta_y = max(self.tilt.mouse_delta_y, 25.0)
            self.sound.note_on(note_name)

    def _do_note_off(self, ch):
        if ch not in KEY_MAP:
            return
        note_name, _ = KEY_MAP[ch]
        self._key_held[ch] = False
        self.active_notes.discard(note_name)
        self.sound.note_off(note_name)

    # ── drawing ────────────────────────────────────────────────────────────────

    def _safe_addstr(self, y, x, text, attr=0):
        try:
            h, w = self.scr.getmaxyx()
            if y < 0 or y >= h or x < 0:
                return
            if x + len(text) > w:
                text = text[:w - x]
            if text:
                self.scr.addstr(y, x, text, attr)
        except curses.error:
            pass

    def _draw_loading(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        msg = "  Tuning the reeds...  "
        sub = "synthesising harmonium tones"
        y = h // 2
        self._safe_addstr(y,   max(0, (w - len(msg)) // 2), msg,
                          curses.color_pair(CP_BRASS_ON_DARK) | curses.A_BOLD)
        self._safe_addstr(y+1, max(0, (w - len(sub)) // 2), sub,
                          curses.color_pair(CP_DIM))
        self.scr.refresh()

    def _draw_frame(self, h, w):
        dim = curses.color_pair(CP_DIM)
        hdr = curses.color_pair(CP_HEADER) | curses.A_BOLD

        header = " * " + "HARMONIUM".center(w - 6) + " * "
        self._safe_addstr(0, 0, header[:w], hdr)
        self._safe_addstr(h - 1, 0, "-" * w, dim)

        for row in range(1, h - 1):
            self._safe_addstr(row, 0,     "|", dim)
            self._safe_addstr(row, w - 1, "|", dim)

        divider = "+" + "-" * (w - 2) + "+"
        self._safe_addstr(2,     0, divider, dim)
        self._safe_addstr(4,     0, divider, dim)
        self._safe_addstr(h - 3, 0, divider, dim)

    def _draw_bellows(self, h, w):
        level = self.tilt.bellows_level
        angle = self.tilt.tilt_angle
        mode  = self.tilt.mode

        fill_w = w - 36
        filled = int(fill_w * level)

        brass = curses.color_pair(CP_BRASS_ON_DARK)
        mf    = curses.color_pair(CP_METER_FILL)
        me    = curses.color_pair(CP_METER_EMPTY)
        dim   = curses.color_pair(CP_DIM)

        label = "  BELLOWS  ["
        self._safe_addstr(3, 0, label, brass)
        x = len(label)

        self._safe_addstr(3, x,          "#" * filled,            mf | curses.A_BOLD)
        self._safe_addstr(3, x + filled, "." * (fill_w - filled), me)
        x += fill_w

        pct = int(level * 100)
        if mode == "iio":
            info = f"]  {pct:3d}%   b {angle:+.1f} deg"
        elif mode == "evdev":
            info = f"]  {pct:3d}%   evdev"
        else:
            info = f"]  {pct:3d}%   mouse/kbd"
        self._safe_addstr(3, x, info, brass)

        hint = "  drag up/down or hold SPACE" if mode == "mouse" else "  tilt screen to pump bellows"
        self._safe_addstr(3, x + len(info), hint[:w - x - len(info) - 1], dim)

    def _draw_keyboard(self, h, w):
        KEY_W   = 5
        KEY_H   = 7
        BLACK_H = 4

        total_w = len(WHITE_NOTES) * KEY_W
        start_x = max(1, (w - total_w) // 2)
        start_y = 6

        brass_dim = curses.color_pair(CP_BRASS_ON_DARK) | curses.A_DIM

        # White keys
        for i, (name, freq, kkey) in enumerate(WHITE_NOTES):
            kx = start_x + i * KEY_W
            pressed = name in self.active_notes

            bg = curses.color_pair(CP_WHITE_KEY_ACT) | curses.A_BOLD if pressed \
                 else curses.color_pair(CP_WHITE_KEY)

            self._safe_addstr(start_y, kx, "+---+", brass_dim)

            for row in range(KEY_H):
                y = start_y + 1 + row
                label_short = name.replace("4", "").replace("5", "")
                if row == KEY_H - 3:
                    self._safe_addstr(y, kx, f"|{label_short:^3}|", bg)
                elif row == KEY_H - 2:
                    self._safe_addstr(y, kx, f"| {kkey.upper()} |", bg | curses.A_DIM)
                else:
                    self._safe_addstr(y, kx, "|   |", bg)

            self._safe_addstr(start_y + 1 + KEY_H, kx, "+---+", brass_dim)

        # Black keys
        for name, freq, kkey in BLACK_NOTES:
            wi = BLACK_OVER_WHITE.get(name, 0)
            bx = start_x + wi * KEY_W + 3
            pressed = name in self.active_notes

            bg = curses.color_pair(CP_BLACK_KEY_ACT) | curses.A_BOLD if pressed \
                 else curses.color_pair(CP_BLACK_KEY) | curses.A_BOLD

            self._safe_addstr(start_y, bx, "+--+", brass_dim)

            for row in range(BLACK_H):
                y = start_y + 1 + row
                short = name.replace("4", "").replace("5", "")
                if row == BLACK_H - 2:
                    self._safe_addstr(y, bx, f"|{short:^2}|", bg)
                elif row == BLACK_H - 1:
                    self._safe_addstr(y, bx, f"|{kkey.upper():^2}|", bg | curses.A_DIM)
                else:
                    self._safe_addstr(y, bx, "|  |", bg)

            self._safe_addstr(start_y + 1 + BLACK_H, bx, "+--+", brass_dim)

    def _draw_status(self, h, w):
        dim   = curses.color_pair(CP_DIM)
        pill  = curses.color_pair(CP_NOTE_PILL) | curses.A_BOLD
        brass = curses.color_pair(CP_BRASS_ON_DARK)

        y = h - 2
        level = self.tilt.bellows_level

        if level > 0.65:
            bstr  = " >> full breath  "
            battr = brass | curses.A_BOLD
        elif level > 0.2:
            bstr  = " >  breathing    "
            battr = brass
        else:
            bstr  = " .  still...     "
            battr = dim
        self._safe_addstr(y, 1, bstr, battr)

        if self.active_notes:
            notes_str = "  * " + "  ".join(sorted(self.active_notes)) + "  "
        else:
            notes_str = "  ~ press keys while tilting..."
        self._safe_addstr(y, 18, notes_str[:w - 28], pill if self.active_notes else dim)

        q_str = "  q: quit"
        self._safe_addstr(y, w - len(q_str) - 1, q_str, dim)

    # ── input handling ─────────────────────────────────────────────────────────

    def _handle_input(self):
        try:
            key = self.scr.get_wch()
        except curses.error:
            return

        if key == curses.ERR:
            return

        if key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, bstate = curses.getmouse()
                self._handle_mouse(mx, my, bstate)
            except Exception:
                pass
            return

        ch = key if isinstance(key, str) else (chr(key) if isinstance(key, int) and key < 256 else "")

        if ch.lower() == "q":
            self._quit_gracefully()
            return

        if ch == " ":
            if self.tilt.mode == "mouse":
                self.tilt.mouse_delta_y = 40.0
            return

        ch_lower = ch.lower()
        if ch_lower in KEY_MAP:
            self._key_last_seen[ch_lower] = time.monotonic()
            self._do_note_on(ch_lower)

    def _handle_mouse(self, mx, my, bstate):
        pressed_mask  = getattr(curses, "BUTTON1_PRESSED",  4)
        released_mask = getattr(curses, "BUTTON1_RELEASED", 8)

        if bstate & pressed_mask:
            self._prev_mouse_y = my
        elif bstate & released_mask:
            if self._prev_mouse_y is not None:
                self.tilt.mouse_delta_y = abs(my - self._prev_mouse_y) * 6.0
            self._prev_mouse_y = None
        elif self._prev_mouse_y is not None:
            self.tilt.mouse_delta_y = abs(my - self._prev_mouse_y) * 5.0
            self._prev_mouse_y = my

    def _quit_gracefully(self):
        for note_name in list(self.active_notes):
            self.sound.note_off(note_name)
        time.sleep(0.35)
        self._quit = True
