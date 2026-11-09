"""
01_hover_test.py - take off to ~0.5 m, hover in place for 10 s, land.

This checks the basics before anything else: radio link, decks, battery,
position estimate (Flow deck), takeoff, holding position and landing.

    python 01_hover_test.py                  # defaults from config.py
    python 01_hover_test.py --height 0.4 --time 5

Watch for: a calm takeoff, the drone staying within ~10-20 cm of its start
point, and a soft landing close to where it took off.
"""

import argparse

import config
from drone import run_flight


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--height", type=float, default=config.FLIGHT_HEIGHT, help="hover height in m")
    parser.add_argument("--time", type=float, default=config.HOVER_TIME, help="hover time in s")
    args = parser.parse_args()

    if not 0.2 <= args.height <= config.GEOFENCE_MAX_HEIGHT - 0.1:
        parser.error(f"--height must be between 0.2 and {config.GEOFENCE_MAX_HEIGHT - 0.1:.1f} m")

    target = (0.0, 0.0, args.height)

    def fly(flight):
        print(f">>> Hovering at {args.height:.2f} m for {args.time:.0f} s ...")
        start = flight.elapsed()
        next_print = start
        while flight.elapsed() - start < args.time:
            snap = flight.tick("HOVER", target)
            if flight.elapsed() >= next_print:
                print(f"    x={snap['x']:+.2f}  y={snap['y']:+.2f}  z={snap['z']:.2f} m   "
                      f"battery {snap.get('vbat', 0):.2f} V")
                next_print += 1.0

    run_flight(config, "01_hover", [
        f"HOVER TEST: take off to {args.height:.2f} m, hover {args.time:.0f} s in place, land.",
        f"Geofence: {config.GEOFENCE_RADIUS} m around the start, max height {config.GEOFENCE_MAX_HEIGHT} m.",
    ], args.height, fly)


if __name__ == "__main__":
    main()
