"""
replay.py - feed the ranger readings recorded in a 04 log back through the
avoidance logic and see what it decides. No drone needed.

    python replay.py                         # every 04 log in logs/ (real flights and dry runs)
    python replay.py logs/2026-11-08_20-16-42_04_figure8_avoid.csv
    python replay.py --set CLEAR_DISTANCE=0.8 --set CLEAR_TIME=1.5    # try other settings
    python replay.py --compare my_idea       # also run another version of the logic (see below)

Each control tick of the log gives the readings, the estimated position, the
yaw and the time; they go through the same AvoidanceStateMachine as in flight
(04_figure8_avoid.py). If the log was flown with the same code and settings,
the replay makes the same decisions as the log; replay.py checks and prints this.
After a change to avoidance.py, the plot shows before (the log) and after (the
replay) on the same readings.

--compare MODULE runs a second version of the logic next to it: a file
MODULE.py with a class StateMachine (same interface as AvoidanceStateMachine)
and a function make_config(*overrides) returning the settings. Use it to try
an idea before changing avoidance.py.

Important limit: the log only knows where the REAL drone went. Once a replay
decides something different (say, it returns to the path while the real drone
kept waiting), the following readings belong to a drone that is somewhere else.
Everything after the first difference ("diverges at ...") is only a hint. The
point where it diverges is still a real answer: "this logic would have done X
at time T with exactly these readings".

Saves logs/plots/<log name>_replay.png for each log.
"""

import argparse
import importlib
import math
import re
from pathlib import Path
from types import SimpleNamespace

import config
from analyze_logs import BEAMS, FLIGHT_STATES, find_logs, infer_width, is_dry_run, load_log
from avoidance import AvoidanceStateMachine
from dry_run import BEAM_STYLES, INK, MUTED, STATE_COLORS, _pyplot
from figure8 import Figure8


def settings(overrides=()):
    """A copy of config with NAME=VALUE overrides applied (config.py itself is not changed)."""
    values = {k: getattr(config, k) for k in dir(config) if k.isupper()}
    for item in overrides:
        name, _, value = item.partition("=")
        if name not in values:
            raise SystemExit(f"--set: unknown setting {name}")
        values[name] = type(values[name])(value) if not isinstance(values[name], tuple) else eval(value)
    return SimpleNamespace(**values)


def first_row(log):
    """Index of the first row the state machine produced."""
    if is_dry_run(log):
        return 0
    for i, text in enumerate(log["event"]):
        if text.startswith("FOLLOW: starting"):
            return i + 1
    return None


# Everything in the drone's "Ranges" log packet. The flight only feeds the filter when a NEW
# packet arrived; the log has no packet counter, so a change in any of these marks a new packet.
PACKET_COLUMNS = BEAMS + ("up", "zrange", "squal")


def new_packet(log, i):
    return i == 0 or is_dry_run(log) or any(log[c][i] != log[c][i - 1] for c in PACKET_COLUMNS)


def replay(log, cfg, machine=AvoidanceStateMachine, width=None, speed=None, laps=None):
    """Run the state machine over the log. Returns a dict with one entry per replayed row."""
    start = first_row(log)
    result = {"rows": [], "state": [], "sp": [], "events": [], "holding": [], "land": None, "start": start}
    if start is None:
        return result
    fig8 = Figure8(width or infer_width(log), speed or cfg.FIG8_SPEED, laps or cfg.FIG8_LAPS, cfg.FIG8_RAMP_TIME)
    now = {"t": 0.0}
    sm = machine(cfg, fig8, lambda text, beam: result["events"].append((now["t"], text, beam)))
    dt = 1.0 / cfg.CONTROL_RATE_HZ
    for i in range(start, log["rows"]):
        if log["state"][i] not in FLIGHT_STATES:
            break                                   # the real flight stopped here (landing)
        t = now["t"] = log["t"][i]
        if new_packet(log, i):
            # the flight passes the whole telemetry snapshot (readings + x, y, yaw)
            sm.filter.update({k: log[k][i] for k in BEAMS + ("x", "y", "yaw")}, t)
        pos, yaw = (log["x"][i], log["y"][i]), log["yaw"][i] or 0.0
        sp = sm.step(t, dt, pos, yaw)
        result["rows"].append(i)
        result["state"].append(sm.state)
        result["sp"].append(sp)
        result["holding"].append(return_blockers(sm, pos, yaw) if sm.state == "WAIT" else [])
        if sm.land_reason:
            result["land"] = (t, sm.land_reason)
            break
        if fig8.done and sm.state == "FOLLOW":
            break
    return result


def return_blockers(sm, pos, yaw):
    """Beams that stop the logic from leaving WAIT right now."""
    if hasattr(sm, "return_blockers"):
        return sm.return_blockers(pos, yaw)
    f, n = sm.filter, sm.cfg.AVOID_CONFIRM_COUNT      # logic versions before November 2026
    return [b for b in f.distance if f.distance[b] is None or f.near_count[b] >= n]


def divergence(log, result, ticks=3):
    """Time where the replay's state first differs from the logged state for `ticks` ticks in a row.

    (A difference of a tick or two is timing jitter: the log stores times rounded to the tick.)
    """
    run = 0
    for i, state in zip(result["rows"], result["state"]):
        run = run + 1 if state != log["state"][i] else 0
        if run == ticks:
            return log["t"][i - ticks + 1]
    return None


def logged_events(log):
    """Events the state machine made in flight (ABORTs come from the safety checks, not from it)."""
    return [(t, text, beam) for t, text, beam, s in zip(log["t"], log["event"], log["beam"], log["state"])
            if text and s in FLIGHT_STATES and not text.startswith(("FOLLOW: starting", "ABORT"))]


def describe(log, result, name):
    lines = [f"  {name}:"]
    for t, text, beam in result["events"]:
        lines.append(f"    {t:6.2f} s  {text}")
    if result["land"]:
        lines.append(f"    {result['land'][0]:6.2f} s  LAND: {result['land'][1]}")
    elif result["rows"]:
        last = result["rows"][-1]
        lines.append(f"    {log['t'][last]:6.2f} s  (end of the recorded flight, state {result['state'][-1]})")
    return lines


def fidelity(log, result):
    """How well a replay with the flight settings matches the log: (events matched, events, % ticks same).

    Events count as matched within two ticks, ignoring the numbers in the text (the
    closing speed may differ in its last digit because the log rounds the times).
    """
    def plain(text):
        return re.sub(r"\d+\.\d+", "#", text)       # numbers may differ in the last digit
    real = logged_events(log)
    same = sum(1 for (t1, x1, _), (t2, x2, _) in zip(real, result["events"])
               if plain(x1) == plain(x2) and abs(t1 - t2) < 0.11)
    ticks = sum(1 for i, s in zip(result["rows"], result["state"]) if s == log["state"][i])
    return same, len(real), 100.0 * ticks / max(1, len(result["rows"]))


# --------------------------------------------------------------------------
# Plot
# --------------------------------------------------------------------------

def plot(log, runs, out, title):
    """runs: [(label, result, divergence time)]: state bars, then one panel per beam."""
    plt = _pyplot()
    fig, axes = plt.subplots(1 + len(BEAMS), 1, figsize=(14, 3 + 2.1 * len(BEAMS)), sharex=True,
                             gridspec_kw={"height_ratios": [0.9 + 0.35 * len(runs)] + [1] * len(BEAMS)})
    fig.suptitle(title, fontsize=11)
    ax = axes[0]
    labels = ["real flight (log)"] + [f"replay: {label}" for label, _r, _d in runs]
    rows_t = [log["t"]] + [[log["t"][i] for i in r["rows"]] for _l, r, _d in runs]
    states = [log["state"]] + [r["state"] for _l, r, _d in runs]
    for k, (ts, ss) in enumerate(zip(rows_t, states)):
        for i, (t, s) in enumerate(zip(ts, ss)):
            end = ts[i + 1] if i + 1 < len(ts) else t + 0.05
            if s in STATE_COLORS:
                ax.broken_barh([(t, end - t)], (k - 0.35, 0.7), color=STATE_COLORS[s], lw=0)
    for k, (label, r, div) in enumerate(runs, start=1):
        for t, text, beam in r["events"]:
            if text.startswith("AVOID"):
                ax.plot(t, k, "v", color=INK, ms=6)
        if r["land"]:
            ax.plot(r["land"][0], k, "X", color=INK, ms=9)
            ax.annotate("would land", (r["land"][0], k), xytext=(4, -12), textcoords="offset points", fontsize=7)
        if div is not None:
            for a in axes:
                a.axvline(div, color=INK, lw=0.8, ls=(0, (4, 3)))
            ax.annotate(f"{label} differs from the real flight from here", (div, k), xytext=(4, 9),
                        textcoords="offset points", fontsize=7)
    for state, color in STATE_COLORS.items():
        ax.plot([], [], color=color, lw=6, label=state)
    ax.plot([], [], "v", color=INK, label="AVOID started")
    ax.legend(loc="upper right", ncol=6, frameon=False, fontsize=7, bbox_to_anchor=(1, 1.25))
    ax.set_yticks(range(len(labels)), labels)
    ax.set_ylim(len(labels) - 0.4, -0.6)
    ax.grid(axis="y", visible=False)

    top = config.RANGE_MAX_VALID + 0.3
    band_colors = [MUTED, INK]
    for ax, beam in zip(axes[1:], BEAMS):
        color, _style = BEAM_STYLES[beam]
        values = [v if config.RANGE_MIN_VALID <= v < config.RANGE_MAX_VALID else math.nan for v in log[beam]]
        ax.plot(log["t"], values, color=color, lw=1.3)
        far = [t for t, v in zip(log["t"], log[beam]) if v >= config.RANGE_MAX_VALID]
        ax.plot(far, [top - 0.12] * len(far), "|", color=MUTED, ms=5, label="out of range / no reading")
        for level, name in ((config.AVOID_DISTANCE, "avoid"), (config.CLEAR_DISTANCE, "clear")):
            ax.axhline(level, color=INK, ls="--" if name == "avoid" else ":", lw=0.9)
            ax.annotate(f"{name} {level} m", (1.0, level), xycoords=("axes fraction", "data"),
                        ha="right", va="bottom", fontsize=7)
        # where this beam keeps each logic in WAIT (a bar along the bottom of the panel)
        for k, (label, r, _d) in enumerate(runs):
            ts = [log["t"][i] for i, h in zip(r["rows"], r["holding"]) if beam in h]
            y0 = 0.02 + 0.13 * k
            ax.broken_barh([(t, 0.05) for t in ts], (y0, 0.1), color=band_colors[k % 2], lw=0)
            ax.plot([], [], color=band_colors[k % 2], lw=5, label=f"keeps the {label} in WAIT")
        ax.set_ylim(0, top)
        ax.set_ylabel(f"{beam} (m)")
        ax.legend(loc="upper left", frameon=False, fontsize=7, ncol=3)
    axes[-1].set_xlabel("time since takeoff (s)")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out, dpi=100)
    plt.close(fig)


def main():
    import matplotlib
    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", default=[str(config.LOG_DIR)], help="04 logs or folders (default: logs/)")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                        help="change a config.py setting for this replay only (repeatable)")
    parser.add_argument("--compare", metavar="MODULE",
                        help="also replay MODULE.StateMachine with MODULE.make_config()")
    parser.add_argument("--compare-set", action="append", default=[], metavar="NAME=VALUE",
                        help="change a setting of the --compare logic only (repeatable)")
    parser.add_argument("--tag", default="", help="added to the plot file names")
    parser.add_argument("--out", default=str(config.LOG_DIR / "plots"))
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = settings(args.set)
    other = importlib.import_module(args.compare) if args.compare else None
    label = "current logic"
    for path in find_logs(args.paths):
        if "_04_" not in path.name:
            continue
        log = load_log(path)
        current = replay(log, cfg)
        print(f"\n=== {log['name']}")
        if not current["rows"]:
            print("  nothing to replay (the figure-8 never started)")
            continue
        same, total, ticks = fidelity(log, current)
        div = divergence(log, current)
        print(f"  Replay with the current code{' and changed settings' if args.set else ''}: "
              f"{same} of {total} logged decisions reproduced, same state in {ticks:.1f}% of ticks"
              + (f"; first different decision at {div:.2f} s" if div is not None else ""))
        lines = describe(log, current, "current logic")
        runs = [(label, current, div)]
        if other:
            proposed = replay(log, other.make_config(*args.set, *args.compare_set), other.StateMachine)
            pdiv = divergence(log, proposed)
            name = getattr(other, "LABEL", args.compare)
            runs.append((name, proposed, pdiv))
            lines += describe(log, proposed, name
                              + (f" (differs from the real flight from {pdiv:.2f} s)" if pdiv is not None else ""))
        print("\n".join(lines))
        out = out_dir / f"{log['name']}_replay{'_' + args.tag if args.tag else ''}.png"
        changed = ", ".join(args.set + args.compare_set)
        plot(log, runs, out, f"{log['name']}: what the logic decides with the recorded readings"
             + (f"\n(settings changed: {changed})" if changed else ""))
        print(f"  plot: {out}")


if __name__ == "__main__":
    main()
