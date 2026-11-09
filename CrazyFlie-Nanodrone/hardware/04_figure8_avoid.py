"""
04_figure8_avoid.py - the full behaviour: fly the figure-8, avoid a person
detected by the Multi-ranger, then return to the path and continue.

States (see avoidance.py for the details):
    FOLLOW -> AVOID -> WAIT -> RETURN -> FOLLOW

    python 04_figure8_avoid.py --dry-run     # simulate with a fake person and plot, no drone
    python 04_figure8_avoid.py --dry-run --person 1.4 0.3 -1.4 0.3 0.5 6
                                             # your own fake person: from (x0,y0) to (x1,y1)
                                             # at 0.5 m/s, starting 6 s into the figure-8
                                             # (repeat --person for more people)
    python 04_figure8_avoid.py               # fly for real

Start real tests by stepping SLOWLY into the drone's front or side beam at
about 1 m distance, never by walking straight at it.
"""

import argparse
import math
from collections import defaultdict

import config
from avoidance import FOLLOW, AvoidanceStateMachine
from figure8 import Figure8, add_figure8_args, check_figure8_args, describe

BEAMS = ("front", "back", "left", "right")


def dry_run(fig8, args, people):
    from common import FlightLogger
    from dry_run import SimDrone, fake_ranges, make_rng, plot_avoid_run

    dt = 1.0 / config.CONTROL_RATE_HZ
    rng = make_rng(config)
    drone = SimDrone(config.DRY_RUN_DRONE_LAG)
    events = []
    t = 0.0
    sm = AvoidanceStateMachine(config, fig8, lambda text, beam: events.append(
        (t, sm.state, beam, drone.pos[0], drone.pos[1], text)))

    # the figure-8 as it would be flown without anybody in the way (for the plot)
    plan = Figure8(args.width, args.speed, 1, 0)
    plan_points = [plan.position()]
    while not plan.done:
        plan.advance(dt)
        plan_points.append(plan.position())

    rec = defaultdict(list)
    ending = "figure-8 finished"
    closest = math.inf          # closest the edge of a person's body came to the drone
    for line in describe(fig8, args, config):
        print(line)
    for p in people:
        print(f"Fake person: {p.start} -> {p.end} at {p.speed} m/s, starting at {p.delay} s")
    print()

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with FlightLogger(config.LOG_DIR, "04_dry_run") as logger:
        while not (fig8.done and sm.state == FOLLOW):
            # 1. fake sensor readings -> filter (on the real drone: telemetry)
            readings, glitched = fake_ranges(drone.pos, 0.0, people, t, config, rng)
            sm.filter.update(dict(readings, x=drone.pos[0], y=drone.pos[1], yaw=0.0), t)
            # 2. the same state machine as the real flight
            n_events = len(events)
            setpoint = sm.step(t, dt, drone.pos, 0.0)
            # 3. the same safety rules (only the ones that make sense without a drone)
            distance = math.hypot(*drone.pos)
            if distance > config.GEOFENCE_RADIUS:
                ending = f"GEOFENCE exceeded ({distance:.2f} m), would land"
            elif sm.land_reason:
                ending = f"{sm.land_reason}, would land"
            elif t > config.MAX_FLIGHT_TIME:
                ending = "maximum flight time reached, would land"
            # 4. record and log
            new = events[n_events:]
            for (te, _s, _b, _x, _y, text) in new:
                print(f"[{te:6.1f} s] {text}")
            for p in people:
                where = p.position(t)
                if where is not None:
                    closest = min(closest, math.dist(where, drone.pos) - p.radius)
            rec["t"].append(t)
            rec["state"].append(sm.state)
            rec["x"].append(drone.pos[0])
            rec["y"].append(drone.pos[1])
            rec["glitch"].append(glitched)
            for beam in BEAMS:
                rec[beam].append(readings[beam])
            person = (people[0].position(t) if people else None) or (None, None)
            logger.write(dict(t=t, state=sm.state, event="; ".join(e[5] for e in new),
                              beam=",".join(e[2] for e in new if e[2]),
                              x=drone.pos[0], y=drone.pos[1], z=args.height, yaw=0.0,
                              sp_x=setpoint[0], sp_y=setpoint[1], sp_z=args.height,
                              person_x=person[0], person_y=person[1], **readings))
            if ending != "figure-8 finished":
                break
            # 5. move the simulated drone
            drone.step(setpoint, dt)
            t += dt
        print(f"\nResult: {ending} after {t:.1f} s. {sum(1 for e in events if e[1] == 'AVOID')} avoid event(s).")
        print(f"Closest a person came to the drone: {closest:.2f} m"
              + ("   <-- COLLISION (the drone is ~0.05 m from its centre to its edge)" if closest < 0.05 else ""))
        print(f"Dry-run log saved to {logger.path}")

    rec["plan_x"] = [p[0] for p in plan_points]
    rec["plan_y"] = [p[1] for p in plan_points]
    plot_avoid_run(rec, events, people, config,
                   f"04 dry run: {ending} after {t:.1f} s",
                   config.LOG_DIR / "04_figure8_avoid_dry_run.png", show=not args.no_show)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_figure8_args(parser, config)
    parser.add_argument("--person", nargs=6, type=float, action="append",
                        metavar=("X0", "Y0", "X1", "Y1", "SPEED", "DELAY"),
                        help="dry run: a fake person walking from (X0,Y0) to (X1,Y1); replaces FAKE_PEOPLE")
    args = parser.parse_args()
    fig8 = check_figure8_args(parser, args, config)

    if args.dry_run:
        from dry_run import FakePerson
        if args.person:
            people = [FakePerson((p[0], p[1]), (p[2], p[3]), p[4], p[5]) for p in args.person]
        else:
            people = [FakePerson(**p) for p in config.FAKE_PEOPLE]
        dry_run(fig8, args, people)
        return

    from drone import AbortFlight, run_flight      # only needed for real flights

    def fly(flight):
        dt = 1.0 / config.CONTROL_RATE_HZ
        height = args.height
        pending = []                                # events from the state machine for the log
        sm = AvoidanceStateMachine(config, fig8, lambda text, beam: pending.append((text, beam)))

        print(f">>> Hovering {config.FIG8_HOVER_TIME:.0f} s and checking the room, "
              "then starting the figure-8 with avoidance ...")
        snap = flight.hover_and_check_room(height, args.width, config.FIG8_HOVER_TIME)
        last_count = snap["range_count"]
        snap = flight.tick(FOLLOW, (0.0, 0.0, height), event="FOLLOW: starting the figure-8")

        next_lap = 1
        while not (fig8.done and sm.state == FOLLOW):
            if snap["range_count"] != last_count:   # only feed NEW ranger readings to the filter
                last_count = snap["range_count"]
                sm.filter.update(snap, flight.elapsed())
            x, y = sm.step(flight.elapsed(), dt, (snap["x"], snap["y"]), snap.get("yaw", 0.0))
            if sm.land_reason:
                raise AbortFlight(sm.land_reason)
            event = "; ".join(text for text, _ in pending)
            beam = ",".join(b for _, b in pending if b)
            pending.clear()
            snap = flight.tick(sm.state, (x, y, height), event, beam)
            if fig8.laps_done >= next_lap:
                print(f">>> Lap {next_lap} of {args.laps} done.")
                next_lap += 1
        for _ in range(config.CONTROL_RATE_HZ):     # 1 s hover at the centre before landing
            flight.tick("HOVER", (0.0, 0.0, height))

    lines = describe(fig8, args, config) + [
        f"AVOID when a beam sees something closer than {config.AVOID_DISTANCE} m "
        f"({config.AVOID_CONFIRM_COUNT} readings in a row); move {config.RETREAT_DISTANCE}-{config.MAX_RETREAT_DISTANCE} m away;",
        f"return when the person's beam and the way back see more than {config.CLEAR_DISTANCE} m "
        f"for {config.CLEAR_TIME:.0f} s."]
    run_flight(config, "04_figure8_avoid", lines, args.height, fly)


if __name__ == "__main__":
    main()
