#!/usr/bin/env python3
"""
realhm — Real Harmonium terminal instrument
"""

import sys
import time
import argparse
import threading


def main():
    parser = argparse.ArgumentParser(prog="realhm")
    parser.add_argument("--mouse",    action="store_true", help="Force mouse bellows mode")
    parser.add_argument("--no-sound", action="store_true", help="Disable audio (UI only)")
    parser.add_argument("--version",  action="store_true", help="Print version and exit")
    args = parser.parse_args()

    if args.version:
        from realharmonium import __version__
        print(f"realharmonium {__version__}")
        sys.exit(0)

    try:
        import shutil
        cols, rows = shutil.get_terminal_size()
        if cols < 80 or rows < 24:
            print(f"Terminal too small ({cols}x{rows}). Minimum: 80x24.")
            sys.exit(1)
    except Exception:
        pass

    missing = []
    try:
        import numpy
    except ImportError:
        missing.append("numpy")
    try:
        import pygame
    except ImportError:
        missing.append("pygame")
    if missing:
        print("Missing:", ", ".join(missing))
        print("Install: pip3 install " + " ".join(missing))
        sys.exit(1)

    from realharmonium.sound_engine import SoundEngine, preload_all_notes
    from realharmonium.tilt_engine  import TiltEngine
    from realharmonium.ui           import HarmoniumUI

    NOTE_MAP = {
        "C4":  261.63, "C#4": 277.18, "D4":  293.66, "D#4": 311.13,
        "E4":  329.63, "F4":  349.23, "F#4": 369.99, "G4":  392.00,
        "G#4": 415.30, "A4":  440.00, "A#4": 466.16, "B4":  493.88,
        "C5":  523.25, "C#5": 554.37, "D5":  587.33, "D#5": 622.25,
        "E5":  659.25,
    }

    sound    = SoundEngine()
    tilt     = TiltEngine()
    # stop_evt is shared — set it to cleanly stop the bellows loop
    stop_evt = threading.Event()

    if not args.no_sound:
        sound.init()

    if args.mouse:
        tilt.mode     = "mouse"
        tilt._running = True
        threading.Thread(target=tilt._mouse_loop, daemon=True).start()
    else:
        tilt.start()

    if not args.no_sound:
        preload_thread = threading.Thread(
            target=preload_all_notes, args=(NOTE_MAP,), daemon=True)
        preload_thread.start()
    else:
        preload_thread = None

    # Bellows update loop — stops cleanly when stop_evt is set
    def bellows_update_loop():
        while not stop_evt.is_set():
            try:
                sound.update_bellows(tilt.bellows_level)
            except Exception:
                pass
            stop_evt.wait(timeout=0.033)

    bloop = threading.Thread(target=bellows_update_loop, daemon=True)
    bloop.start()

    if preload_thread:
        preload_thread.join()

    if not args.no_sound:
        sound.start_drone()

    ui = HarmoniumUI(sound, tilt)
    try:
        ui.run()
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()      # stop bellows loop cleanly
        tilt.stop()
        bloop.join(timeout=0.5)   # wait for it to exit before pygame teardown
        print("\nGoodbye.")
        sys.exit(0)


if __name__ == "__main__":
    main()