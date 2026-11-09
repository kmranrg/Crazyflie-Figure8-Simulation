"""
tests.py - check the avoidance logic without a drone. Run it after ANY change
to avoidance.py or the avoidance settings in config.py.

    python tests.py                      # all checks, prints PASS/FAIL
    python tests.py --plots              # also save a plot per scenario to logs/plots/tests/
    python tests.py --baseline old/      # also run an older copy (old/avoidance.py + old/config.py)
                                         # on the same scenarios, for a before/after table

Two kinds of checks:

1. Rules of the ranger filter, one at a time (e.g. "nothing in range counts as
   clear", "a dropout does not count as clear straight away").
2. Closed-loop scenarios: the simulated drone from the dry run flies the
   figure-8 with the real AvoidanceStateMachine, in rooms rebuilt from the
   flight logs of 8 November 2026, with simulated people walking around. Each
   scenario says how it must end and how close a person may come.

Scenario G (a fast walker crossing between two beams) is a known limitation
of four narrow beams: it is run and shown, but not counted as a failure.
"""

import argparse
import importlib.util
import math
import sys
from collections import defaultdict
from pathlib import Path

import config
from avoidance import AvoidanceStateMachine, RangeFilter
from dry_run import SimDrone, fake_ranges, make_rng
from figure8 import Figure8


# --------------------------------------------------------------------------
# Things in the simulated room
# --------------------------------------------------------------------------

class Route:
    """A person who appears at the first point, walks from point to point and leaves after the last.

    points: [(time, (x, y)), ...]; two points with the same position = standing still.
    """

    def __init__(self, points, radius=0.2):
        self.points, self.radius = points, radius
        self.start, self.end = points[0][1], points[-1][1]
        self.length = sum(math.dist(a[1], b[1]) for a, b in zip(points, points[1:]))

    def position(self, t):
        if t < self.points[0][0] or t > self.points[-1][0]:
            return None
        for (t0, p0), (t1, p1) in zip(self.points, self.points[1:]):
            if t0 <= t <= t1:
                f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                return (p0[0] + f * (p1[0] - p0[0]), p0[1] + f * (p1[1] - p0[1]))
        return self.end


def walk(start, end, speed, delay, radius=0.2):
    """Walk in a straight line from start to end at speed m/s, starting at time delay."""
    return Route([(delay, start), (delay + math.dist(start, end) / speed, end)], radius)


def stand(where, until=1e9, radius=0.2):
    """Something standing still from the start until `until` s, then gone (a box, a person)."""
    return Route([(0.0, where), (until, where)], radius)


class Wall:
    """A flat wall, simulated as a huge circle. side: 'left', 'right', 'front' or 'back'."""
    R = 20.0

    def __init__(self, side, distance):
        self.side, self.distance, self.radius = side, distance, self.R
        d = distance + self.R
        self.centre = {"left": (0, d), "right": (0, -d), "front": (d, 0), "back": (-d, 0)}[side]

    def position(self, t):
        return self.centre

    def gap(self, pos):
        return math.dist(self.centre, pos) - self.R


# --------------------------------------------------------------------------
# Scenarios: (description, people, walls, expected ending, min distance to a person, max AVOIDs)
# ending: "finished" or "land" (MAX_PAUSE_TIME reached, the correct answer when the way stays blocked)
# --------------------------------------------------------------------------

def scenarios():
    p = config.FAKE_PEOPLE[0]
    return {
        "A": ("default crossing walker (config.FAKE_PEOPLE)",
              [walk(p["start"], p["end"], p["speed"], p["delay"], p["radius"])], [], "finished", 0.30, None),
        "B": ("20-16-42 room: wall 1.3 m left, box in the path, removed at 12 s",
              [stand((-0.17, -0.42), until=12, radius=0.05)], [Wall("left", 1.3)], "finished", 0.20, None),
        "C": ("same room, the box is never removed",
              [stand((-0.17, -0.42), radius=0.05)], [Wall("left", 1.3)], "land", 0.20, None),
        "D": ("21-54-45 room: wall 1.4 m behind, walker crossing from the right",
              [walk((-0.1, -2.0), (-0.1, 2.0), 0.6, 20)], [Wall("back", 1.4)], "finished", 0.30, None),
        "E": ("walker comes to 0.7 m on the right, stands 8 s, walks away",
              [Route([(8, (0.0, -2.0)), (10, (0.0, -0.9)), (18, (0.0, -0.9)), (20, (0.0, -2.5))])],
              [], "finished", 0.30, None),
        "F": ("slow walker (0.3 m/s) straight at the drone from the front",
              [walk((2.0, 0.1), (-2.0, 0.1), 0.3, 4)], [], "finished", 0.20, None),
        "G": ("KNOWN LIMITATION: two crossings, walls 1.6 m left and right",
              [walk((0.35, 2.0), (0.35, -2.0), 0.8, 3), walk((-0.3, -2.0), (-0.3, 2.0), 1.0, 30)],
              [Wall("left", 1.6), Wall("right", 1.6)], None, None, None),
        "H": ("fast walker (0.8 m/s) straight at the drone from the front",
              [walk((2.0, 0.05), (-2.0, 0.05), 0.8, 4)], [], "finished", 0.10, None),
        "I": ("walker (0.5 m/s) from behind",
              [walk((-2.0, -0.1), (2.0, -0.1), 0.5, 6)], [], "finished", 0.30, None),
        "J": ("fast walker (1.2 m/s) crossing in front",
              [walk((0.35, 2.0), (0.35, -2.0), 1.2, 3)], [], "finished", 0.20, None),
        "K": ("person standing still 0.6 m beyond the left end of the path",
              [stand((0.0, 1.3))], [], "finished", 0.40, None),
        "L": ("21-57-23 room: wall 1.3 m in front, nobody around (must not avoid the wall)",
              [], [Wall("front", 1.3)], "finished", None, 0),
    }


def fly(cfg, machine, people, walls, laps=None):
    """One closed-loop dry run. Returns a dict with the outcome and a record for plotting."""
    fig8 = Figure8(cfg.FIG8_WIDTH, cfg.FIG8_SPEED, laps or cfg.FIG8_LAPS, cfg.FIG8_RAMP_TIME)
    rng = make_rng(cfg)
    drone = SimDrone(cfg.DRY_RUN_DRONE_LAG)
    dt = 1.0 / cfg.CONTROL_RATE_HZ
    events, rec = [], defaultdict(list)
    t = 0.0
    sm = machine(cfg, fig8, lambda text, beam: events.append((t, sm.state, beam, drone.pos[0], drone.pos[1], text)))
    closest, wall_gap, ending = math.inf, math.inf, "finished"
    while not (fig8.done and sm.state == "FOLLOW"):
        readings, glitched = fake_ranges(drone.pos, 0.0, people + walls, t, cfg, rng)
        sm.filter.update(dict(readings, x=drone.pos[0], y=drone.pos[1], yaw=0.0), t)
        setpoint = sm.step(t, dt, drone.pos, 0.0)
        for person in people:
            where = person.position(t)
            if where is not None:
                closest = min(closest, math.dist(where, drone.pos) - person.radius)
        for wall in walls:
            wall_gap = min(wall_gap, wall.gap(drone.pos))
        for key, value in (("t", t), ("state", sm.state), ("x", drone.pos[0]), ("y", drone.pos[1]),
                           ("glitch", glitched)):
            rec[key].append(value)
        for beam in ("front", "back", "left", "right"):
            rec[beam].append(readings[beam])
        if math.hypot(*drone.pos) > cfg.GEOFENCE_RADIUS:
            ending = "GEOFENCE"
        elif wall_gap < 0.05:
            ending = "HIT A WALL"
        elif sm.land_reason:
            ending = "land"
        elif t > cfg.MAX_FLIGHT_TIME:
            ending = "max flight time"
        if ending != "finished":
            break
        drone.step(setpoint, dt)
        t += dt
    plan = Figure8(cfg.FIG8_WIDTH, cfg.FIG8_SPEED, 1, 0)
    rec["plan_x"], rec["plan_y"] = [plan.position()[0]], [plan.position()[1]]
    while not plan.done:
        plan.advance(dt)
        rec["plan_x"].append(plan.position()[0])
        rec["plan_y"].append(plan.position()[1])
    avoids = sum(1 for e in events if e[5].startswith("AVOID"))
    rejoins = sum(1 for e in events if e[5].startswith("FOLLOW: back"))
    return dict(ending=ending, t=t, closest=closest, avoids=avoids, rejoins=rejoins, events=events, rec=rec)


# --------------------------------------------------------------------------
# Filter rules
# --------------------------------------------------------------------------

def filter_checks(cfg):
    """[(description, passed)] for the ranger filter rules."""
    far = cfg.RANGE_MAX_VALID + 28.766            # what the real sensor sends when it sees nothing
    n = cfg.AVOID_CONFIRM_COUNT
    out = []

    f = RangeFilter(cfg)
    for k in range(5):
        f.update({"front": far}, 0.05 * k)
    out.append(("nothing in range counts as clear", f.is_clear("front") and not f.blocked()))

    f = RangeFilter(cfg)
    for k in range(5):
        f.update({"front": 0.01}, 0.05 * k)
    out.append(("invalid readings (< 2 cm) are ignored, never blocked", not f.blocked()))

    f = RangeFilter(cfg)
    for k in range(n):
        f.update({"front": 0.4}, 0.05 * k)
    out.append((f"{n} close readings in a row start AVOID", f.blocked() == ["front"]))

    f = RangeFilter(cfg)
    for k, r in enumerate([0.4] * (n - 1) + [0.9] + [0.4] * (n - 1)):
        f.update({"front": r}, 0.05 * k)
    out.append(("a broken run of close readings does not start AVOID", not f.blocked()))

    f = RangeFilter(cfg)
    for k in range(n + 2):
        f.update({"front": 0.8}, 0.05 * k)
    f.update({"front": far}, 0.05 * (n + 2))       # one dropout in the middle of a real object
    out.append(("a dropout right after a real reading does not count as clear yet", not f.is_clear("front")))

    f = RangeFilter(cfg)
    for k in range(n):
        f.update({"front": 0.4}, 0.05 * k)
    f.update({"front": far}, 0.05 * n)
    out.append(("a dropout ends a run of close readings (no stale AVOID)", not f.blocked()))

    f = RangeFilter(cfg)
    for k in range(n + 2):
        f.update({"front": 0.8}, 0.05 * k)
    t = 0.05 * (n + 2)
    while t < 0.05 * (n + 2) + cfg.DROPOUT_HOLD_TIME + 0.2:
        f.update({"front": far}, t)
        t += 0.05
    out.append((f"nothing in range for longer than {cfg.DROPOUT_HOLD_TIME} s counts as clear", f.is_clear("front")))

    f = RangeFilter(cfg)
    f.update({"front": far}, 0.0)
    f.update({"front": 0.27}, 0.05)                 # one glitch reading ...
    f.update({"front": far}, 0.10)                  # ... then nothing again
    out.append(("an old glitch does not block that direction for dodging", f.free_space("front") == math.inf))

    # wall 1.5 m ahead, the drone flies towards it at 0.4 m/s: the wall is not "approaching"
    f = RangeFilter(cfg)
    for k in range(10):
        x = 0.04 * k
        f.update({"front": 1.5 - x, "x": x, "y": 0.0, "yaw": 0.0}, 0.1 * k)
    out.append(("flying towards a still wall is not 'approaching'", f.closing_speed("front") < 0.05))

    # person walking at the hovering drone at 0.3 m/s
    f = RangeFilter(cfg)
    for k in range(10):
        f.update({"front": 1.5 - 0.03 * k, "x": 0.0, "y": 0.0, "yaw": 0.0}, 0.1 * k)
    out.append(("a person walking at 0.3 m/s is 'approaching'", f.closing_speed("front") > cfg.APPROACH_SPEED))
    return out


# --------------------------------------------------------------------------

def load_baseline(folder):
    """avoidance.py + config.py from another folder (e.g. a copy of an older version)."""
    folder = Path(folder)
    modules = []
    for name in ("config", "avoidance"):
        spec = importlib.util.spec_from_file_location(f"baseline_{name}", folder / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    base_cfg, base_avoidance = modules
    for key in dir(config):                 # settings the old copy did not have yet
        if key.isupper() and not hasattr(base_cfg, key):
            setattr(base_cfg, key, getattr(config, key))
    return base_cfg, base_avoidance.AvoidanceStateMachine


def verdict(spec, result):
    _text, _people, _walls, ending, min_gap, max_avoids = spec
    if ending is None:
        return "known limitation"
    problems = []
    if result["ending"] != ending:
        problems.append(f"ended '{result['ending']}', expected '{ending}'")
    if min_gap is not None and result["closest"] < min_gap:
        problems.append(f"person came to {result['closest']:.2f} m (limit {min_gap:.2f} m)")
    if max_avoids is not None and result["avoids"] > max_avoids:
        problems.append(f"{result['avoids']} AVOIDs (limit {max_avoids})")
    return "PASS" if not problems else "FAIL: " + "; ".join(problems)


def summary(result):
    gap = "-" if result["closest"] == math.inf else f"{result['closest']:.2f} m"
    return f"{result['ending']:8s} {result['t']:5.1f} s  closest {gap:>6s}  avoid {result['avoids']:2d}  rejoin {result['rejoins']}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plots", action="store_true", help="save a plot per scenario to logs/plots/tests/")
    parser.add_argument("--baseline", metavar="FOLDER", help="also run avoidance.py + config.py from FOLDER")
    parser.add_argument("--only", metavar="LETTERS", help="run only these scenarios, e.g. --only BCK")
    args = parser.parse_args()

    failures = 0
    print("Ranger filter rules:")
    for text, ok in filter_checks(config):
        print(f"  {'PASS' if ok else 'FAIL'}  {text}")
        failures += not ok

    baseline = load_baseline(args.baseline) if args.baseline else None
    print("\nClosed-loop scenarios (simulated drone, current code):")
    for key, spec in scenarios().items():
        if args.only and key not in args.only.upper():
            continue
        text, people, walls = spec[:3]
        result = fly(config, AvoidanceStateMachine, people, walls)
        v = verdict(spec, result)
        failures += v.startswith("FAIL")
        print(f"  {key}  {text}\n       now:      {summary(result)}   {v}")
        if baseline:
            old = fly(baseline[0], baseline[1], people, walls)
            print(f"       baseline: {summary(old)}")
        if args.plots:
            import matplotlib
            matplotlib.use("Agg")
            from dry_run import plot_avoid_run
            out = config.LOG_DIR / "plots" / "tests"
            out.mkdir(parents=True, exist_ok=True)
            plot_avoid_run(result["rec"], result["events"], people, config,
                           f"Scenario {key}: {text}\n{summary(result)}  ->  {v}",
                           out / f"scenario_{key}.png", show=False)
    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{failures} CHECK(S) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
