"""
tilt_engine.py — Dynamic tilt detection with real harmonium bellows physics

Bellows model:
  - Movement pumps air in FAST  (fill rate proportional to tilt velocity)
  - Stillness bleeds air SLOWLY (like real reeds leaking pressure)
  - You must keep moving the screen to keep notes sounding
  - Starts at zero, must be pumped up from scratch

Detection order:
  1. IIO sysfs        /sys/bus/iio/devices/iio:device*
  2. hp_accel/lis3    /sys/devices/.../position
  3. evdev            /dev/input/event* with ABS_X+Y+Z
  4. Webcam           optical tilt via OpenCV (asks user first)
  5. Mouse/Space      fallback
"""

import os
import glob
import threading
import time
import math


class TiltEngine:

    def __init__(self):
        self.bellows_level  = 0.0   # always starts at zero — must be pumped
        self.tilt_angle     = 0.0
        self.tilt_velocity  = 0.0
        self.mode           = "none"

        self._running = False
        self._thread  = None

        # IIO
        self._iio_path    = None
        self._iio_x_file  = None
        self._iio_y_file  = None
        self._iio_z_file  = None
        self._iio_scale_x = 1.0
        self._iio_scale_y = 1.0
        self._iio_scale_z = 1.0

        # hp_accel position file
        self._position_file = None

        # evdev
        self._evdev_device = None

        # webcam
        self._cam_index = 0
        self._cam       = None

        # velocity smoothing (short window = responsive)
        self._history     = []
        self._HISTORY_LEN = 5

        # mouse fallback
        self.mouse_delta_y = 0.0

    # ── public ────────────────────────────────────────────────────────────────

    def start(self):
        self._detect_mode()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._cam is not None:
            try:
                self._cam.release()
            except Exception:
                pass

    def debug_info(self) -> str:
        if self.mode == "iio":
            return f"IIO  path={self._iio_path}  y={self._iio_y_file}"
        elif self.mode == "hp_accel":
            return f"hp_accel  position={self._position_file}"
        elif self.mode == "evdev":
            return f"evdev  device={self._evdev_device}"
        elif self.mode == "webcam":
            return f"webcam  /dev/video{self._cam_index}"
        else:
            return "mouse/space fallback"

    # ── bellows physics ───────────────────────────────────────────────────────
    #
    #  Real harmonium bellows:
    #    - Pumping fast  → fills quickly  (FILL_RATE  controls this)
    #    - Pumping slow  → fills slowly
    #    - Holding still → pressure bleeds through the reeds (BLEED_RATE)
    #    - Bleed is slow — a full bellows lasts ~1.5s before going silent
    #    - Fill is fast  — a single firm pump fills it in ~0.3s
    #
    FILL_RATE  = 3.5    # how fast movement fills bellows  (higher = faster fill)
    BLEED_RATE = 0.55   # fraction of pressure lost per second when still
                        # 0.55 = loses ~55% per second → ~1.5s from full to silent

    def _apply_bellows_physics(self, raw_vel: float, dt: float):
        """
        raw_vel: tilt velocity in degrees/second (or equivalent units)
        dt:      time since last sample in seconds

        Maps velocity → fill rate, applies bleed every tick.
        """
        # Smooth velocity
        self._history.append(raw_vel)
        if len(self._history) > self._HISTORY_LEN:
            self._history.pop(0)
        avg_vel = sum(self._history) / len(self._history)
        self.tilt_velocity = avg_vel

        # Velocity → pump rate
        # Below MIN_VEL the screen is considered still (no pumping)
        # Above MAX_VEL it's pumping at full rate
        MIN_VEL = 1.0    # °/s — noise floor / still threshold
        MAX_VEL = 18.0   # °/s — full pump speed

        pump_strength = (avg_vel - MIN_VEL) / (MAX_VEL - MIN_VEL)
        pump_strength = max(0.0, min(1.0, pump_strength))

        # Fill: proportional to pump strength × time
        fill = pump_strength * self.FILL_RATE * dt
        self.bellows_level = min(1.0, self.bellows_level + fill)

        # Bleed: always happening, even while pumping (reeds always leak)
        # Exponential decay: level × (1 - bleed_rate × dt)
        bleed = self.BLEED_RATE * dt
        self.bellows_level = max(0.0, self.bellows_level * (1.0 - bleed))

    # ── detection chain ───────────────────────────────────────────────────────

    def _detect_mode(self):
        if self._probe_iio():
            self.mode = "iio"
            return
        if self._probe_hp_accel():
            self.mode = "hp_accel"
            return
        if self._probe_evdev():
            self.mode = "evdev"
            return
        if self._ask_webcam_permission():
            if self._probe_webcam():
                self.mode = "webcam"
                return
        self.mode = "mouse"

    # ── probe: IIO ────────────────────────────────────────────────────────────

    def _probe_iio(self) -> bool:
        base = "/sys/bus/iio/devices/"
        if not os.path.isdir(base):
            return False
        for dev_dir in sorted(glob.glob(os.path.join(base, "iio:device*"))):
            result = self._check_iio_dir(dev_dir)
            if result:
                self._iio_path    = dev_dir
                self._iio_x_file  = result["x"]
                self._iio_y_file  = result["y"]
                self._iio_z_file  = result["z"]
                self._iio_scale_x = result["sx"]
                self._iio_scale_y = result["sy"]
                self._iio_scale_z = result["sz"]
                return True
        return False

    def _check_iio_dir(self, dev_dir):
        def find_axis(axis):
            for suffix in ("_raw", "_processed"):
                p = os.path.join(dev_dir, f"in_accel_{axis}{suffix}")
                if os.path.exists(p):
                    return p
            return None

        x, y, z = find_axis("x"), find_axis("y"), find_axis("z")
        if not (x and y):
            return None
        if not self._readable_float(x) or not self._readable_float(y):
            return None

        def scale(axis):
            for name in (f"in_accel_{axis}_scale", "in_accel_scale"):
                p = os.path.join(dev_dir, name)
                if os.path.exists(p):
                    try:
                        return float(open(p).read().strip())
                    except Exception:
                        pass
            return 1.0

        return {"x": x, "y": y, "z": z,
                "sx": scale("x"), "sy": scale("y"), "sz": scale("z")}

    # ── probe: hp_accel ───────────────────────────────────────────────────────

    def _probe_hp_accel(self) -> bool:
        candidates = (
            glob.glob("/sys/devices/platform/lis3lv02d/position") +
            glob.glob("/sys/devices/*/lis3lv02d*/position") +
            glob.glob("/sys/bus/platform/drivers/hp_accel/*/position") +
            glob.glob("/sys/devices/platform/*/position")
        )
        for path in candidates:
            try:
                val = open(path).read().strip()
                if len(val) > 2:
                    self._position_file = path
                    return True
            except Exception:
                pass
        return False

    def _read_position_file(self):
        try:
            raw = open(self._position_file).read().strip().strip("()")
            parts = raw.replace(",", " ").split()
            return float(parts[0]), float(parts[1]), float(parts[2])
        except Exception:
            return 0.0, 0.0, 1.0

    # ── probe: evdev ──────────────────────────────────────────────────────────

    def _probe_evdev(self) -> bool:
        try:
            import evdev
            from evdev import ecodes
            for path in evdev.list_devices():
                try:
                    dev  = evdev.InputDevice(path)
                    caps = dev.capabilities()
                    if ecodes.EV_ABS in caps:
                        axes = [a[0] for a in caps[ecodes.EV_ABS]]
                        if (ecodes.ABS_X in axes and
                                ecodes.ABS_Y in axes and
                                ecodes.ABS_Z in axes):
                            self._evdev_device = dev
                            return True
                    dev.close()
                except Exception:
                    pass
        except Exception:
            pass
        return False

    # ── probe: webcam ─────────────────────────────────────────────────────────

    def _ask_webcam_permission(self) -> bool:
        print()
        print("  ┌──────────────────────────────────────────────────────┐")
        print("  │   No hardware accelerometer detected                 │")
        print("  │                                                      │")
        print("  │   The webcam can detect screen tilt optically        │")
        print("  │   by tracking the angle of lines in the frame.       │")
        print("  │   Processed locally — never saved or transmitted.    │")
        print("  └──────────────────────────────────────────────────────┘")
        print()
        try:
            ans = input("  Use webcam for tilt detection? [y/N] ").strip().lower()
            return ans == "y"
        except Exception:
            return False

    def _probe_webcam(self) -> bool:
        try:
            import cv2
        except ImportError:
            print()
            print("  opencv-python not installed.")
            print("  Run:  pip3 install opencv-python")
            print("  Then restart realhm.")
            print()
            return False

        for idx in (0, 1):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    self._cam       = cap
                    self._cam_index = idx
                    return True
            cap.release()
        return False

    # ── helpers ───────────────────────────────────────────────────────────────

    def _readable_float(self, path) -> bool:
        try:
            float(open(path).read().strip())
            return True
        except Exception:
            return False

    def _read_iio(self, path, scale) -> float:
        if not path:
            return 0.0
        try:
            return float(open(path).read().strip()) * scale
        except Exception:
            return 0.0

    # ── loops ─────────────────────────────────────────────────────────────────

    def _loop(self):
        if self.mode == "iio":
            self._iio_loop()
        elif self.mode == "hp_accel":
            self._hp_accel_loop()
        elif self.mode == "evdev":
            self._evdev_loop()
        elif self.mode == "webcam":
            self._webcam_loop()
        else:
            self._mouse_loop()

    def _iio_loop(self):
        INTERVAL   = 0.033
        prev_angle = None
        prev_time  = time.monotonic()
        while self._running:
            ax = self._read_iio(self._iio_x_file, self._iio_scale_x)
            ay = self._read_iio(self._iio_y_file, self._iio_scale_y)
            az = self._read_iio(self._iio_z_file, self._iio_scale_z) if self._iio_z_file else 9.8
            try:
                pitch = math.degrees(math.atan2(ay, math.sqrt(ax*ax + az*az)))
            except Exception:
                pitch = 0.0
            self.tilt_angle = pitch
            now = time.monotonic()
            dt  = now - prev_time
            if prev_angle is not None and dt > 0:
                self._apply_bellows_physics(abs(pitch - prev_angle) / dt, dt)
            prev_angle = pitch
            prev_time  = now
            time.sleep(INTERVAL)

    def _hp_accel_loop(self):
        INTERVAL   = 0.033
        prev_angle = None
        prev_time  = time.monotonic()
        while self._running:
            x, y, z = self._read_position_file()
            try:
                pitch = math.degrees(math.atan2(y, math.sqrt(x*x + z*z)))
            except Exception:
                pitch = 0.0
            self.tilt_angle = pitch
            now = time.monotonic()
            dt  = now - prev_time
            if prev_angle is not None and dt > 0:
                self._apply_bellows_physics(abs(pitch - prev_angle) / dt, dt)
            prev_angle = pitch
            prev_time  = now
            time.sleep(INTERVAL)

    def _evdev_loop(self):
        from evdev import ecodes
        prev_y    = None
        prev_time = time.monotonic()
        try:
            for event in self._evdev_device.read_loop():
                if not self._running:
                    break
                if event.type == ecodes.EV_ABS and event.code == ecodes.ABS_Y:
                    y   = event.value
                    now = time.monotonic()
                    dt  = now - prev_time
                    if prev_y is not None and dt > 0:
                        vel = abs(y - prev_y) / dt
                        self._apply_bellows_physics(vel * 0.05, dt)
                    prev_y    = y
                    prev_time = now
        except Exception:
            self.mode = "mouse"
            self._mouse_loop()

    def _webcam_loop(self):
        """
        Optical flow tilt detection using Lucas-Kanade point tracking.
        Tracks feature points between frames — when you tilt the screen,
        ALL points shift vertically together. Median vertical displacement
        = tilt motion velocity. Still screen = zero = bellows bleeds.
        Moving screen = displacement = bellows fills.
        """
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.mode = "mouse"
            self._mouse_loop()
            return

        INTERVAL  = 0.05
        prev_gray = None
        prev_pts  = None
        prev_time = time.monotonic()

        lk_params = dict(
            winSize=(15, 15),
            maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )
        feature_params = dict(
            maxCorners=80,
            qualityLevel=0.2,
            minDistance=10,
            blockSize=7
        )
        REFRESH_EVERY = 20
        frame_count   = 0

        while self._running:
            ret, frame = self._cam.read()
            if not ret:
                time.sleep(INTERVAL)
                continue

            small = cv2.resize(frame, (320, 240))
            gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            now   = time.monotonic()
            dt    = now - prev_time

            if prev_gray is not None and prev_pts is not None and len(prev_pts) > 0:
                new_pts, status, _ = cv2.calcOpticalFlowPyrLK(
                    prev_gray, gray, prev_pts, None, **lk_params)

                if new_pts is not None and status is not None:
                    good_old = prev_pts[status.flatten() == 1]
                    good_new = new_pts[status.flatten() == 1]

                    if len(good_new) > 5:
                        dy_vals    = good_new[:, 0, 1] - good_old[:, 0, 1]
                        median_dy  = float(np.median(np.abs(dy_vals)))
                        # pixels/frame -> velocity signal
                        vel = (median_dy / INTERVAL) * 0.8
                        self.tilt_angle = float(np.median(dy_vals))
                        if dt > 0:
                            self._apply_bellows_physics(vel, dt)

                    prev_pts = good_new if len(good_new) > 10 else None

            frame_count += 1
            if prev_pts is None or frame_count % REFRESH_EVERY == 0:
                prev_pts = cv2.goodFeaturesToTrack(gray, mask=None, **feature_params)

            prev_gray = gray.copy()
            prev_time = now
            time.sleep(INTERVAL)

    def _mouse_loop(self):
        """
        Space bar / mouse drag bellows.
        Holding space fills bellows, releasing lets it bleed naturally.
        """
        INTERVAL  = 0.033
        prev_time = time.monotonic()
        while self._running:
            now = time.monotonic()
            dt  = now - prev_time
            prev_time = now

            dy = abs(self.mouse_delta_y)
            # Convert mouse delta to a velocity-like signal
            vel = dy / (INTERVAL * 30.0)
            self._apply_bellows_physics(vel, dt)
            self.mouse_delta_y = 0.0
            time.sleep(INTERVAL)