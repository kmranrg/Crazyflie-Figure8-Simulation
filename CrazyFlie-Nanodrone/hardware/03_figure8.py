"""
03_figure8.py - fly the figure-8 slowly, with NO person avoidance.

The drone takes off at the centre of the figure-8 (the crossing point),
flies FIG8_LAPS laps and lands back at the centre.

    python 03_figure8.py --dry-run           # plot the planned path first, no drone needed
    python 03_figure8.py                     # fly with the defaults from config.py
    python 03_figure8.py --width 0.8 --speed 0.2 --laps 1

Watch for: a smooth path with no jerks, and how far the drone ends up from its
takeoff point after the laps (that is Flow deck drift).
"""

import argparse
import math

import config
from figure8 import add_figure8_args, check_figure8_args, describe


def dry_run(fig8, args):
    from dry_run import plot_figure8_plan
    dt = 1.0 / config.CONTROL_RATE_HZ
    times, points, speeds = [0.0], [fig8.position()], [0.0]
    while not fig8.done:
        fig8.advance(dt)
        points.append(fig8.position())
        speeds.append(math.dist(points[-1], points[-2]) / dt)
        times.append(times[-1] + dt)
    for line in describe(fig8, args, config):
        print(line)
    print(f"Total figure-8 time including speed-up/slow-down: {times[-1]:.1f} s")
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    plot_figure8_plan(times, points, speeds, config,
                      f"03 dry run: {args.width} m figure-8, {args.speed} m/s average, {args.laps} lap(s)",
                      config.LOG_DIR / "03_figure8_dry_run.png", show=not args.no_show)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_figure8_args(parser, config)
    args = parser.parse_args()
    fig8 = check_figure8_args(parser, args, config)

    if args.dry_run:
        dry_run(fig8, args)
        return

    from drone import run_flight      # only needed for real flights

    def fly(flight):
        dt = 1.0 / config.CONTROL_RATE_HZ
        print(">>> Settling for 2 s, then starting the figure-8 ...")
        for _ in range(2 * config.CONTROL_RATE_HZ):
            flight.tick("HOVER", (0.0, 0.0, args.height))
        flight.tick("FOLLOW", (0.0, 0.0, args.height), event="FOLLOW: starting the figure-8")
        next_lap = 1
        while not fig8.done:
            fig8.advance(dt)
            x, y = fig8.position()
            flight.tick("FOLLOW", (x, y, args.height))
            if fig8.laps_done >= next_lap:
                print(f">>> Lap {next_lap} of {args.laps} done.")
                next_lap += 1
        for _ in range(config.CONTROL_RATE_HZ):          # 1 s hover at the centre before landing
            flight.tick("HOVER", (0.0, 0.0, args.height))

    run_flight(config, "03_figure8", describe(fig8, args, config), args.height, fly)


if __name__ == "__main__":
    main()
