"""
common.py - helpers that do not need the drone: the CSV flight log and the
emergency-stop keyboard listener. (Everything that talks to the drone is in drone.py.)
"""

import csv
import math
import os
import select
import sys
import threading
import time
from datetime import datetime

# Columns of every flight log. Distances in metres, yaw in degrees, battery in volts.
#   x, y, z, yaw         position estimate from the drone
#   sp_x, sp_y, sp_z     the setpoint we commanded (where we asked it to be)
#   front ... zrange     raw ranger readings (up to ~4 m; bigger numbers mean "nothing seen")
#   squal                Flow deck surface quality (0-255, higher is better)
#   person_x, person_y   only in dry runs: where the fake person was
LOG_COLUMNS = ["t", "state", "event", "beam", "x", "y", "z", "yaw", "sp_x", "sp_y", "sp_z",
               "vbat", "front", "back", "left", "right", "up", "zrange", "squal",
               "person_x", "person_y"]


class FlightLogger:
    """Writes one CSV row per control tick to logs/<date>_<time>_<name>.csv."""

    def __init__(self, log_dir, name):
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = log_dir / f"{stamp}_{name}.csv"
        self._file = open(self.path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=LOG_COLUMNS, extrasaction="ignore")
        self._writer.writeheader()

    def write(self, values):
        """values: dict with any of the LOG_COLUMNS keys; missing ones stay empty."""
        row = {}
        for key, value in values.items():
            if isinstance(value, float):
                value = "" if math.isnan(value) else f"{value:.3f}"
            row[key] = "" if value is None else value
        self._writer.writerow(row)
        self._file.flush()      # so the log survives a crash

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class KeyboardStop:
    """Listens for keys in the background while the drone flies.

        space, q or Enter  -> land now        (self.land_requested is set)
        k                  -> kill the motors (self.kill_requested is set; the drone drops!)

    Ctrl+C keeps working as usual. The terminal goes back to normal on exit.
    """

    LAND_KEYS = (" ", "q", "Q", "\n", "\r")
    KILL_KEYS = ("k", "K")

    def __init__(self):
        self.land_requested = threading.Event()
        self.kill_requested = threading.Event()
        self._closing = threading.Event()
        self._old_settings = None

    def __enter__(self):
        if not sys.stdin.isatty():
            print("WARNING: no interactive terminal, so the land key will not work. Use Ctrl+C.")
            return self
        import termios
        import tty
        fd = sys.stdin.fileno()
        self._old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)       # read single key presses; Ctrl+C still works
        threading.Thread(target=self._listen, daemon=True).start()
        return self

    def _listen(self):
        fd = sys.stdin.fileno()
        while not self._closing.is_set():
            ready, _, _ = select.select([fd], [], [], 0.1)
            if not ready:
                continue
            key = os.read(fd, 1).decode(errors="ignore")
            if key in self.LAND_KEYS:
                self.land_requested.set()
            elif key in self.KILL_KEYS:
                self.kill_requested.set()
                self.land_requested.set()

    def __exit__(self, *exc):
        self._closing.set()
        if self._old_settings is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_settings)
        return False


class RateKeeper:
    """Sleeps just long enough to run a loop at a fixed rate."""

    def __init__(self, rate_hz):
        self.period = 1.0 / rate_hz
        self._next = time.monotonic()

    def wait(self):
        self._next += self.period
        delay = self._next - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            self._next = time.monotonic()    # we are late; don't try to catch up
