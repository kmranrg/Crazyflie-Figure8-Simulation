"""
02_ranger_monitor.py - NO FLIGHT. Shows the Multi-ranger readings live.

Put the drone on a table or stool at about flight height, then walk around it
and watch which beam sees you and at what distance. The status column uses the
same filter as 04_figure8_avoid.py:

    BLOCKED  confirmed closer than AVOID_DISTANCE (would start AVOID in flight)
    near     between AVOID_DISTANCE and CLEAR_DISTANCE (not clear yet)
    clear    further than CLEAR_DISTANCE, or nothing in range

Press q (or Ctrl+C) to stop. The readings are also saved to logs/.
If no data arrives for more than a second (radio link lost), it says NO DATA.
"""

import time

import config
from avoidance import RangeFilter
from common import FlightLogger, KeyboardStop
from drone import PreflightError, Telemetry, check_decks, connect, connection_help

BEAMS = ("front", "back", "left", "right", "up")


def describe(beam, distance, rfilter):
    if distance is None:
        return "  --  "
    if distance < config.RANGE_MIN_VALID or distance >= config.RANGE_MAX_VALID:
        text = " none "
    else:
        text = f"{distance:5.2f}m"
    if beam not in rfilter.distance:
        return f"{text} (ignored)"
    if beam in rfilter.blocked():
        status = "BLOCKED"
    elif rfilter.distance[beam] is not None and rfilter.distance[beam] <= config.CLEAR_DISTANCE:
        status = "near"
    else:
        status = "clear"
    return f"{text} {status:7s}"


def main():
    scf = connect(config)
    try:
        scf.open_link()
    except Exception as e:
        print(f"Connection failed: {e}")
        connection_help()
        return
    try:
        cf = scf.cf
        try:
            check_decks(cf, need_flow=False, need_ranger=True)
        except PreflightError as e:
            print(f"\nSTOPPED: {e}")
            return
        telemetry = Telemetry(cf, config.LOG_PERIOD_MS)
        telemetry.start()
        rfilter = RangeFilter(config)
        last_count = -1
        lines = []
        start = last_data = time.monotonic()
        stale_logged = False
        print(f"\nAVOID below {config.AVOID_DISTANCE} m (after {config.AVOID_CONFIRM_COUNT} readings in a row), "
              f"clear above {config.CLEAR_DISTANCE} m. Press q to quit.\n")

        def draw(new_lines):
            if lines:
                print(f"\033[{len(lines)}F", end="")      # move the cursor back up to redraw
            for line in new_lines:
                print(line + "\033[K")                     # \033[K clears the rest of the line
            lines[:] = new_lines

        with FlightLogger(config.LOG_DIR, "02_ranger") as logger, KeyboardStop() as keys:
            try:
                while not keys.land_requested.is_set():
                    snap = telemetry.snapshot()
                    now = time.monotonic()
                    if snap["range_count"] != last_count:     # a new set of readings arrived
                        last_count = snap["range_count"]
                        last_data = now
                        stale_logged = False
                        rfilter.update(snap, now - start)
                        blocked = rfilter.blocked()
                        logger.write({k: snap.get(k) for k in BEAMS + ("zrange", "vbat")}
                                     | dict(t=now - start, state="MONITOR", beam=",".join(blocked)))
                        new_lines = [f"  {b:6s} {describe(b, snap.get(b), rfilter)}" for b in BEAMS]
                        new_lines.append(f"  {'down':6s} {snap.get('zrange', 0):5.2f}m (Flow deck height sensor)")
                        new_lines.append(f"  >>> WOULD AVOID: {', '.join(blocked)}" if blocked else "  (no avoidance)")
                        draw(new_lines)
                    elif now - last_data > 1.0 and lines:
                        # no new data: the radio link is probably lost (the values above are old)
                        draw(lines[:-1] + [f"  >>> NO DATA for {now - last_data:.0f} s: radio link lost? "
                                           "Check the drone and the Crazyradio. Press q to quit."])
                        if not stale_logged:
                            logger.write(dict(t=now - start, state="MONITOR", event="NO DATA: link lost?"))
                            stale_logged = True
                    time.sleep(0.02)
            except KeyboardInterrupt:
                pass
            print(f"\nLog saved to {logger.path}")
        telemetry.stop()
    finally:
        scf.close_link()


if __name__ == "__main__":
    main()
