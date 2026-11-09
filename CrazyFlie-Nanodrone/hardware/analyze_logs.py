"""
analyze_logs.py - turn flight logs (CSV) into plots and a short summary.

No drone needed. Works on every log the scripts write (01 hover, 02 ranger,
03 figure-8, 04 figure-8 with avoidance, and the 04 dry run).

    python analyze_logs.py                       # every log in logs/
    python analyze_logs.py logs/2026-11-08_20-16-42_04_figure8_avoid.csv
    python analyze_logs.py logs/ --out somewhere/else

For each log it saves one PNG into logs/plots/ named after the log:
    figure-8 flights  bird's-eye path (coloured by state) on the planned figure-8,
                      height, every ranger beam, tracking error and battery
    hover flights     position over time, horizontal spread, height and battery
    ranger monitor    every beam over time
It also saves figure8_summary.png (all figure-8 flights against the plan) and
summary.md (the numbers below as a table), and prints a summary per flight.
Your flight notes (logs/FLIGHT_NOTES.md, asked for after each flight) are shown
next to the numbers.

Grey dots in the bird's-eye view are where the ranger beams hit something
(walls, furniture, people): a rough map of the room.
"""

import argparse
import csv
import math
import re
from pathlib import Path

import config
from dry_run import BEAM_STYLES, GRID, INK, MUTED, STATE_COLORS, _pyplot, _top_view
from figure8 import figure8_point

BEAMS = ("front", "back", "left", "right")
BEAM_DIRECTIONS = {"front": (1.0, 0.0), "back": (-1.0, 0.0), "left": (0.0, 1.0), "right": (0.0, -1.0)}
FLIGHT_STATES = ("FOLLOW", "AVOID", "WAIT", "RETURN")
OTHER_STATE_COLOR = "#bdbcb6"       # TAKEOFF, HOVER, LAND, MONITOR
NUMBER_COLUMNS = ("t", "x", "y", "z", "yaw", "sp_x", "sp_y", "sp_z", "vbat", "front", "back", "left",
                  "right", "up", "zrange", "squal", "person_x", "person_y", "supinfo", "rssi", "link")
NAME_PATTERN = re.compile(r"^(\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d)_(.+)\.csv$")


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_log(path):
    """Read one CSV log into a dict of columns (numbers become floats, empty = nan)."""
    path = Path(path)
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    log = {"path": path, "name": path.stem, "rows": len(rows)}
    match = NAME_PATTERN.match(path.name)
    log["stamp"], log["kind"] = (match.group(1), match.group(2)) if match else ("", path.stem)
    for col in NUMBER_COLUMNS:
        log[col] = [float(r[col]) if r.get(col) not in (None, "") else math.nan for r in rows]
    for col in ("state", "event", "beam"):
        log[col] = [r.get(col) or "" for r in rows]
    return log


def read_notes(notes_file=None):
    """{log name: note} from the flight notes file (lines like '- <log name>: text')."""
    notes_file = Path(notes_file or config.NOTES_FILE)
    notes = {}
    if notes_file.exists():
        for line in notes_file.read_text().splitlines():
            match = re.match(r"^\s*-\s*(\S+?):\s*(.*)$", line)
            if match:
                notes[match.group(1)] = match.group(2)
    return notes


def find_logs(paths):
    files = []
    for p in map(Path, paths):
        files += sorted(p.glob("*.csv")) if p.is_dir() else [p]
    return files


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------

def is_dry_run(log):
    return "dry_run" in log["kind"]


def is_figure8(log):
    return log["kind"].startswith(("03", "04"))


def segments(log):
    """[(t_start, t_end, state), ...] for every stretch of the same state."""
    t, states = log["t"], log["state"]
    out = []
    for i, s in enumerate(states):
        end = t[i + 1] if i + 1 < len(t) else t[i] + 0.05
        if out and out[-1][2] == s:
            out[-1][1] = end
        else:
            out.append([t[i], end, s])
    return [tuple(seg) for seg in out]


def events(log):
    """[(row, t, state, text, beam), ...] for every logged event."""
    return [(i, log["t"][i], log["state"][i], text, log["beam"][i])
            for i, text in enumerate(log["event"]) if text]


def infer_width(log):
    """Figure-8 width from the FOLLOW setpoints (x = -y cos(theta) means r^2 = y^4 / (y^2 - x^2))."""
    estimates = []
    for x, y, s in zip(log["sp_x"], log["sp_y"], log["state"]):
        if s == "FOLLOW" and abs(y) > 0.1 and y * y - x * x > 1e-4:
            estimates.append(math.sqrt(y ** 4 / (y * y - x * x)))
    if len(estimates) < 5:
        return config.FIG8_WIDTH
    estimates.sort()
    return round(2 * estimates[len(estimates) // 2], 2)


def planned_curve(width, steps=720):
    return [figure8_point(2 * math.pi * i / steps, width) for i in range(steps + 1)]


def tracking_errors(log, curve):
    """Per row: distance to the setpoint, and distance to the nearest point of the planned figure-8."""
    to_setpoint, to_path = [], []
    for x, y, sx, sy in zip(log["x"], log["y"], log["sp_x"], log["sp_y"]):
        to_setpoint.append(math.hypot(x - sx, y - sy) if not math.isnan(sx) else math.nan)
        to_path.append(min(math.hypot(x - cx, y - cy) for cx, cy in curve) if not math.isnan(x) else math.nan)
    return to_setpoint, to_path


def frozen_telemetry(log, min_duration=0.3):
    """Stretches where the position/battery values did not change at all (no data from the drone)."""
    keys = ("x", "y", "z", "yaw", "vbat")
    out, start = [], None
    t = log["t"]
    for i in range(1, len(t)):
        # identical values on the floor are normal (nothing moves); in the air they mean no new data
        same = (all(log[k][i] == log[k][i - 1] for k in keys) and not math.isnan(log["x"][i])
                and log["z"][i] > 0.05)
        if same and start is None:
            start = i - 1
        if (not same or i == len(t) - 1) and start is not None:
            end = i if same else i - 1
            if t[end] - t[start] >= min_duration:
                out.append((t[start], t[end]))
            start = None
    return out


def mean(values):
    values = [v for v in values if not math.isnan(v)]
    return sum(values) / len(values) if values else math.nan


def stdev(values):
    values = [v for v in values if not math.isnan(v)]
    if len(values) < 2:
        return math.nan
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def maximum(values):
    values = [v for v in values if not math.isnan(v)]
    return max(values) if values else math.nan


def percentile(values, q):
    values = sorted(v for v in values if not math.isnan(v))
    return values[min(len(values) - 1, int(q * len(values)))] if values else math.nan


def analyze(log):
    """All the numbers for the report, as a dict."""
    info = {"name": log["name"], "kind": log["kind"]}
    t = log["t"]
    info["duration"] = t[-1] - t[0] if t else 0.0
    evs = events(log)
    info["events"] = evs
    info["segments"] = segments(log)

    # How did it end?
    ending = "log ends"
    for _i, _t, _s, text, _b in evs:
        if text.startswith("ABORT: "):
            ending = text[len("ABORT: "):]
            break
    else:
        land = [text for _i, _t, s, text, _b in evs if s == "LAND"]
        if land:
            ending = land[0]
        elif is_dry_run(log):
            ending = "dry run finished"
    info["ending"] = ending
    info["note"] = read_notes().get(log["name"], "")
    links = [v for v in log["link"] if not math.isnan(v)]
    info["link_min"] = min(links) if links else None
    crashed = [i for i, v in enumerate(log["supinfo"]) if not math.isnan(v) and int(v) >> 5 & 0b111]
    info["supervisor_alarm"] = log["t"][crashed[0]] if crashed else None
    info["frozen"] = frozen_telemetry(log) if log["kind"] != "02_ranger" else []

    # Did it fly at all?
    z = [v for v in log["z"] if not math.isnan(v)]
    info["max_z"] = max(z) if z else math.nan
    info["took_off"] = is_dry_run(log) or (bool(z) and max(z) > 0.15)

    # Time in each state
    times = {}
    for start, end, s in info["segments"]:
        times[s] = times.get(s, 0.0) + end - start
    info["state_time"] = times
    info["avoid_count"] = sum(1 for _i, _t, s, text, _b in evs if text.startswith("AVOID:"))
    info["rejoin_count"] = sum(1 for _i, _t, s, text, _b in evs if text.startswith("FOLLOW: back on"))

    # Battery
    v = [x for x in log["vbat"] if not math.isnan(x)]
    if v:
        info["vbat_start"], info["vbat_min"], info["vbat_end"] = v[0], min(v), v[-1]

    # Height while flying under our control (skip the first second after takeoff)
    flying = [i for i, s in enumerate(log["state"]) if s in FLIGHT_STATES + ("HOVER",)]
    if flying and info["took_off"]:
        settled = [i for i in flying if t[i] > t[flying[0]] + 1.0] or flying
        zs = [log["z"][i] for i in settled]
        dz = [log["z"][i] - log["sp_z"][i] for i in settled]
        info["z_mean"], info["z_std"] = mean(zs), stdev(zs)
        info["z_min"], info["z_max"] = min(zs), max(zs)
        info["z_err_max"] = maximum([abs(d) for d in dz])

    # Figure-8 tracking
    if is_figure8(log):
        info["width"] = infer_width(log)
        curve = planned_curve(info["width"])
        to_sp, to_path = tracking_errors(log, curve)
        info["to_setpoint"], info["to_path"] = to_sp, to_path
        follow = [i for i, s in enumerate(log["state"]) if s == "FOLLOW" and info["took_off"]]
        if follow:
            info["sp_err_mean"] = mean([to_sp[i] for i in follow])
            info["sp_err_max"] = maximum([to_sp[i] for i in follow])
            info["path_err_mean"] = mean([to_path[i] for i in follow])
            info["path_err_max"] = maximum([to_path[i] for i in follow])

    # Hover spread
    if log["kind"].startswith("01"):
        hover = [i for i, s in enumerate(log["state"]) if s == "HOVER"]
        hover = [i for i in hover if t[i] > t[hover[0]] + 1.0] if hover else []
        if hover:
            r = [math.hypot(log["x"][i] - log["sp_x"][i], log["y"][i] - log["sp_y"][i]) for i in hover]
            info["hover_mean"], info["hover_max"] = mean(r), maximum(r)
            info["hover_p95"] = percentile(r, 0.95)
            info["hover_std_x"] = stdev([log["x"][i] for i in hover])
            info["hover_std_y"] = stdev([log["y"][i] for i in hover])

    # Landing: how far the estimate moved between "land" and the end of the log
    land = [i for i, s in enumerate(log["state"]) if s == "LAND"]
    if land and info["took_off"]:
        a, b = land[0], land[-1]
        info["land_drift"] = math.hypot(log["x"][b] - log["x"][a], log["y"][b] - log["y"][a])
        touchdown = next((i for i in land if log["z"][i] < 0.05), b)
        info["land_drift_air"] = math.hypot(log["x"][touchdown] - log["x"][a],
                                            log["y"][touchdown] - log["y"][a])
    return info


def ranger_hits(log, max_range=3.0):
    """World (x, y) of every valid horizontal beam reading while flying (a rough room map)."""
    pts = []
    for i, s in enumerate(log["state"]):
        if s not in FLIGHT_STATES + ("HOVER",):
            continue
        x, y, yaw = log["x"][i], log["y"][i], math.radians(log["yaw"][i] or 0.0)
        if math.isnan(x):
            continue
        for beam, (bx, by) in BEAM_DIRECTIONS.items():
            d = log[beam][i]
            if config.RANGE_MIN_VALID <= d < min(max_range, config.RANGE_MAX_VALID):
                dx, dy = bx * math.cos(yaw) - by * math.sin(yaw), bx * math.sin(yaw) + by * math.cos(yaw)
                pts.append((x + dx * d, y + dy * d))
    return pts


# --------------------------------------------------------------------------
# Plot pieces
# --------------------------------------------------------------------------

def shade_states(ax, info, label=False):
    """Light background colour per state."""
    done = set()
    for start, end, s in info["segments"]:
        color = STATE_COLORS.get(s, OTHER_STATE_COLOR)
        name = s if s in STATE_COLORS else "takeoff / hover / land"
        ax.axvspan(start, end, color=color, alpha=0.13, lw=0,
                   label=name if label and name not in done else None)
        done.add(name)


def mark_events(ax, info):
    """Thin vertical lines where AVOID started (labelled with the beam)."""
    for _i, t, _s, text, beam in info["events"]:
        if text.startswith("AVOID:"):
            ax.axvline(t, color=STATE_COLORS["AVOID"], lw=0.8)


def plot_beam(ax, log, info, beam, ignored=False):
    color, style = BEAM_STYLES.get(beam, (INK, "-"))
    top = config.RANGE_MAX_VALID + 0.3
    t = log["t"]
    shade_states(ax, info)
    values = [v if config.RANGE_MIN_VALID <= v < config.RANGE_MAX_VALID else math.nan for v in log[beam]]
    ax.plot(t, values, color=color if not ignored else MUTED, lw=1.3)
    far = [tt for tt, v in zip(t, log[beam]) if v >= config.RANGE_MAX_VALID]
    bad = [tt for tt, v in zip(t, log[beam]) if v < config.RANGE_MIN_VALID]
    ax.plot(far, [top - 0.12] * len(far), "|", color=MUTED, ms=5, mew=0.8,
            label="out of range / no reading" if far else None)
    ax.plot(bad, [0.05] * len(bad), "x", color=INK, ms=5, label="invalid (< 2 cm)" if bad else None)
    if not ignored:
        for level, name in ((config.AVOID_DISTANCE, "avoid"), (config.CLEAR_DISTANCE, "clear")):
            ax.axhline(level, color=INK, ls="--" if name == "avoid" else ":", lw=0.9)
            ax.annotate(f"{name} {level} m", (1.0, level), xycoords=("axes fraction", "data"),
                        ha="right", va="bottom", color=INK, fontsize=7)
        for _i, te, _s, text, b in info["events"]:
            if text.startswith("AVOID:") and b == beam:
                ax.plot(te, log[beam][_i] if log[beam][_i] < top else top - 0.3, marker="v", ms=7,
                        color=STATE_COLORS["AVOID"], mec="white", mew=1, ls="none")
    ax.set_ylim(0, top)
    ax.set_ylabel(f"{beam} (m)" + ("\nignored" if ignored else ""))
    if far or bad:
        ax.legend(loc="upper left", frameon=False, fontsize=7, ncol=2)


def plot_height(ax, log, info):
    shade_states(ax, info)
    ax.plot(log["t"], log["zrange"], color=MUTED, lw=0.8, label="down sensor (zrange)")
    ax.plot(log["t"], log["z"], color=INK, lw=1.5, label="estimated height")
    ax.plot(log["t"], log["sp_z"], color=STATE_COLORS["FOLLOW"], lw=1.2, ls="--", label="target")
    ax.axhline(config.GEOFENCE_MAX_HEIGHT, color=STATE_COLORS["AVOID"], lw=0.9, ls=":")
    ax.annotate(f"height limit {config.GEOFENCE_MAX_HEIGHT} m", (1.0, config.GEOFENCE_MAX_HEIGHT),
                xycoords=("axes fraction", "data"), ha="right", va="bottom", color=INK, fontsize=7)
    ax.set_ylim(0, max(config.GEOFENCE_MAX_HEIGHT + 0.25, maximum(log["z"]) + 0.1))
    ax.set_ylabel("height (m)")
    ax.legend(loc="upper left", frameon=False, fontsize=7, ncol=3)


def plot_battery(ax, log, info):
    shade_states(ax, info)
    ax.plot(log["t"], log["vbat"], color=INK, lw=1.2)
    ax.axhline(config.LAND_VOLTAGE, color=STATE_COLORS["AVOID"], ls=":", lw=0.9)
    ax.annotate(f"land below {config.LAND_VOLTAGE} V", (1.0, config.LAND_VOLTAGE),
                xycoords=("axes fraction", "data"), ha="right", va="bottom", color=INK, fontsize=7)
    v = [x for x in log["vbat"] if not math.isnan(x)]
    if v:
        ax.set_ylim(min(min(v), config.LAND_VOLTAGE) - 0.05, max(v) + 0.05)
    ax.set_ylabel("battery (V)")


def mark_frozen(axes, info):
    for start, end in info["frozen"]:
        for ax in axes:
            ax.axvspan(start, end, color=INK, alpha=0.18, lw=0, hatch="//")
        axes[0].annotate("no data from drone", (start, 1.0), xycoords=("data", "axes fraction"),
                         va="top", fontsize=7, color=INK)


def summary_lines(info):
    lines = [f"Ended: {info['ending']}"]
    if info.get("note"):
        lines.append(f"Your note: {info['note']}")
    if info.get("supervisor_alarm") is not None:
        lines.append(f"The drone reported crashed / locked / upside down at {info['supervisor_alarm']:.1f} s")
    if info.get("link_min") is not None:
        lines.append(f"Radio link quality: lowest {info['link_min']:.0f} %")
    if not info["took_off"]:
        lines.append(f"NEVER LEFT THE GROUND (highest z = {info['max_z']:.2f} m)")
    lines.append(f"Duration {info['duration']:.1f} s.  " + ",  ".join(
        f"{s} {v:.1f} s" for s, v in info["state_time"].items()))
    if "vbat_start" in info:
        lines.append(f"Battery {info['vbat_start']:.2f} V at start, lowest {info['vbat_min']:.2f} V")
    if "z_mean" in info:
        lines.append(f"Height {info['z_mean']:.2f} m average, {info['z_min']:.2f}-{info['z_max']:.2f} m, "
                     f"std {info['z_std'] * 100:.1f} cm, worst error {info['z_err_max'] * 100:.0f} cm")
    if "sp_err_mean" in info:
        lines.append(f"FOLLOW: behind setpoint {info['sp_err_mean'] * 100:.0f} cm average "
                     f"({info['sp_err_max'] * 100:.0f} max); off the figure-8 "
                     f"{info['path_err_mean'] * 100:.0f} cm average ({info['path_err_max'] * 100:.0f} max)")
    if info.get("avoid_count"):
        lines.append(f"{info['avoid_count']} AVOID start(s), {info['rejoin_count']} rejoin(s)")
    for start, end in info["frozen"]:
        lines.append(f"No data from the drone from {start:.1f} s to {end:.1f} s (link lost?)")
    return lines


def event_lines(info, limit=22):
    lines = [f"{t:6.1f} s  {text}" for _i, t, _s, text, _b in info["events"]]
    if len(lines) > limit:
        lines = lines[:limit - 1] + [f"   ... {len(lines) - limit + 1} more (see the CSV)"]
    return lines


# --------------------------------------------------------------------------
# Whole figures
# --------------------------------------------------------------------------

def plot_figure8_flight(log, info, out):
    plt = _pyplot()
    fig = plt.figure(figsize=(16, 19))
    fig.suptitle(f"{log['name']}  -  {info['ending']}", fontsize=12)
    grid = fig.add_gridspec(9, 2, width_ratios=[1.05, 1], height_ratios=[1.3] + [1] * 8)
    ax = fig.add_subplot(grid[0:4, 0])
    ax_text = fig.add_subplot(grid[4:, 0])
    ax_h = fig.add_subplot(grid[0, 1])
    beam_axes = [fig.add_subplot(grid[1 + k, 1], sharex=ax_h) for k in range(5)]
    ax_err = fig.add_subplot(grid[6, 1], sharex=ax_h)
    ax_v = fig.add_subplot(grid[7, 1], sharex=ax_h)
    ax_states = fig.add_subplot(grid[8, 1], sharex=ax_h)

    # --- bird's-eye view ----------------------------------------------------
    _top_view(ax, config)
    lim = config.GEOFENCE_RADIUS + 0.9
    ax.set_xlim(lim, -lim)
    ax.set_ylim(-lim, lim)
    hits = ranger_hits(log)
    if hits:
        ax.plot([p[1] for p in hits], [p[0] for p in hits], ".", color=MUTED, ms=2, alpha=0.35,
                label="ranger hits (walls, furniture, people)")
    curve = planned_curve(info["width"])
    ax.plot([p[1] for p in curve], [p[0] for p in curve], color=INK, lw=1.2, ls="--",
            label=f"planned figure-8 ({info['width']:.2f} m wide)")
    t, states = log["t"], log["state"]
    i = 0
    while i < len(t) - 1:
        j = i
        while j < len(t) - 1 and states[j + 1] == states[i]:
            j += 1
        color = STATE_COLORS.get(states[i], OTHER_STATE_COLOR)
        ax.plot(log["y"][i:j + 2], log["x"][i:j + 2], color=color, lw=2 if color != OTHER_STATE_COLOR else 1.2,
                solid_capstyle="round")
        i = j + 1
    for state, color in STATE_COLORS.items():
        if state in info["state_time"]:
            ax.plot([], [], color=color, lw=2, label=f"flown: {state}")
    ax.plot([], [], color=OTHER_STATE_COLOR, lw=1.2, label="flown: takeoff / hover / land")
    ax.plot(log["y"][-1], log["x"][-1], marker="X", ms=10, color=INK, mec="white", ls="none", label="landed")
    for row, te, _s, text, beam in info["events"]:
        y, x = log["y"][row], log["x"][row]
        if text.startswith("AVOID:"):
            ax.plot(y, x, marker="v", ms=9, color=STATE_COLORS["AVOID"], mec="white", mew=1.2)
            ax.annotate(f"{beam} {te:.1f}s", (y, x), xytext=(5, 5), textcoords="offset points", fontsize=7)
        elif text.startswith("FOLLOW: back on"):
            ax.plot(y, x, marker="o", ms=8, color=STATE_COLORS["FOLLOW"], mec="white", mew=1.2)
            ax.annotate(f"rejoined {te:.1f}s", (y, x), xytext=(5, -10), textcoords="offset points", fontsize=7)
    land = next((i for i, s in enumerate(states) if s == "LAND"), None)
    if land is not None:
        ax.plot(log["y"][land], log["x"][land], marker="*", ms=13, color=INK, mec="white", ls="none",
                label="landing started")
    ax.plot([], [], "v", color=STATE_COLORS["AVOID"], label="AVOID started (beam, time)")
    ax.plot([], [], "o", color=STATE_COLORS["FOLLOW"], label="rejoined the figure-8")
    ax.legend(loc="lower left", frameon=True, framealpha=0.9, fontsize=7)
    ax.set_title("Bird's-eye view (estimated position)")

    # --- text ---------------------------------------------------------------
    ax_text.axis("off")
    text = "\n".join(summary_lines(info) + ["", "Events:"] + event_lines(info))
    ax_text.text(0, 1, text, va="top", ha="left", family="monospace", fontsize=8, transform=ax_text.transAxes)

    # --- time series ---------------------------------------------------------
    plot_height(ax_h, log, info)
    ax_h.set_title("Height, ranger beams, tracking error, battery (background = state)")
    for k, beam in enumerate(BEAMS + ("up",)):
        plot_beam(beam_axes[k], log, info, beam, ignored=(beam == "up"))
    shade_states(ax_err, info)
    ax_err.plot(t, info["to_setpoint"], color=INK, lw=1.2, label="distance to setpoint")
    ax_err.plot(t, info["to_path"], color=INK, lw=1.0, ls=":", label="distance to the figure-8 curve")
    ax_err.set_ylim(0, max(0.3, min(1.0, maximum(info["to_setpoint"]) * 1.1)))
    ax_err.set_ylabel("error (m)")
    ax_err.legend(loc="upper left", frameon=False, fontsize=7, ncol=2)
    plot_battery(ax_v, log, info)
    plot_state_bar(ax_states, info)
    mark_frozen([ax_h] + beam_axes + [ax_err, ax_v], info)
    for a in [ax_h] + beam_axes + [ax_err, ax_v]:
        plt.setp(a.get_xticklabels(), visible=False)
    ax_states.set_xlabel("time since takeoff (s)")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(out, dpi=100)
    plt.close(fig)


def plot_state_bar(ax, info):
    names = ["TAKEOFF", "HOVER"] + list(FLIGHT_STATES) + ["LAND"]
    present = [n for n in names if n in info["state_time"]]
    for start, end, s in info["segments"]:
        if s in present:
            ax.broken_barh([(start, end - start)], (present.index(s) - 0.35, 0.7),
                           color=STATE_COLORS.get(s, OTHER_STATE_COLOR))
    for _i, t, _s, text, beam in info["events"]:
        if text.startswith("AVOID:") and "AVOID" in present:
            ax.annotate(beam, (t, present.index("AVOID") + 0.45), fontsize=7, rotation=45, va="top")
    ax.set_yticks(range(len(present)), present)
    ax.set_ylim(len(present) - 0.4, -0.6)
    ax.grid(axis="y", visible=False)
    ax.set_ylabel("state")


def plot_hover_flight(log, info, out):
    plt = _pyplot()
    fig = plt.figure(figsize=(15, 10))
    fig.suptitle(f"{log['name']}  -  {info['ending']}", fontsize=12)
    grid = fig.add_gridspec(4, 2, width_ratios=[1, 1.3])
    ax = fig.add_subplot(grid[0:3, 0])
    ax_text = fig.add_subplot(grid[3, 0])
    ax_xy = fig.add_subplot(grid[0, 1])
    ax_r = fig.add_subplot(grid[1, 1], sharex=ax_xy)
    ax_h = fig.add_subplot(grid[2, 1], sharex=ax_xy)
    ax_v = fig.add_subplot(grid[3, 1], sharex=ax_xy)

    hover = [i for i, s in enumerate(log["state"]) if s == "HOVER"]
    land = [i for i, s in enumerate(log["state"]) if s == "LAND"]
    ax.set_aspect("equal")
    for idx, color, label in ((hover, STATE_COLORS["FOLLOW"], "hovering"),
                              (land, OTHER_STATE_COLOR, "landing")):
        ax.plot([log["y"][i] for i in idx], [log["x"][i] for i in idx], color=color, lw=1.2, label=label)
    for radius in (0.05, 0.10):
        circle = plt.Circle((0, 0), radius, fill=False, ls=":", ec=MUTED)
        ax.add_patch(circle)
        ax.annotate(f"{radius * 100:.0f} cm", (0, radius), xytext=(0, 2), textcoords="offset points",
                    ha="center", fontsize=7, color=MUTED)
    ax.plot(0, 0, "s", color=INK, ms=7, label="takeoff point / target")
    ax.plot(log["y"][-1], log["x"][-1], "X", color=INK, ms=9, mec="white", label="landed")
    span = max(0.15, maximum([abs(v) for v in log["x"] + log["y"]]) + 0.05)
    ax.set_xlim(span, -span)
    ax.set_ylim(-span, span)
    ax.set_xlabel("Y (m)  <- drone's left        drone's right ->")
    ax.set_ylabel("X (m)  drone's front ->")
    ax.set_title("Bird's-eye view of the hover")
    ax.legend(loc="lower left", frameon=False, fontsize=8)

    ax_text.axis("off")
    lines = summary_lines(info)
    if "hover_mean" in info:
        lines.insert(1, f"Hover (after 1 s): {info['hover_mean'] * 100:.1f} cm from target on average, "
                        f"95% within {info['hover_p95'] * 100:.1f} cm, max {info['hover_max'] * 100:.1f} cm")
    if "land_drift" in info:
        lines.append(f"Moved {info['land_drift_air'] * 100:.0f} cm while descending "
                     f"({info['land_drift'] * 100:.0f} cm by the end of the log)")
    ax_text.text(0, 1, "\n".join(lines), va="top", family="monospace", fontsize=8, transform=ax_text.transAxes)

    t = log["t"]
    shade_states(ax_xy, info, label=True)
    ax_xy.plot(t, log["x"], color=INK, lw=1.2, label="x (front)")
    ax_xy.plot(t, log["y"], color=INK, lw=1.2, ls="--", label="y (left)")
    ax_xy.set_ylabel("position (m)")
    ax_xy.legend(loc="upper left", frameon=False, fontsize=7, ncol=5)
    ax_xy.set_title("Position, distance from target, height, battery (background = state)")
    shade_states(ax_r, info)
    r = [math.hypot(x - sx, y - sy) if not math.isnan(sx) else math.nan
         for x, y, sx, sy in zip(log["x"], log["y"], log["sp_x"], log["sp_y"])]
    ax_r.plot(t, r, color=INK, lw=1.2)
    ax_r.set_ylabel("from target (m)")
    plot_height(ax_h, log, info)
    plot_battery(ax_v, log, info)
    mark_frozen([ax_xy, ax_r, ax_h, ax_v], info)
    ax_v.set_xlabel("time since takeoff (s)")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(out, dpi=100)
    plt.close(fig)


def plot_ranger_monitor(log, info, out):
    plt = _pyplot()
    fig, axes = plt.subplots(6, 1, figsize=(12, 11), sharex=True)
    fig.suptitle(f"{log['name']}  -  ranger monitor (no flight)", fontsize=12)
    for ax, beam in zip(axes, BEAMS + ("up",)):
        plot_beam(ax, log, info, beam, ignored=(beam == "up"))
    plot_battery(axes[5], log, info)
    last = log["t"][-1] if log["t"] else 0
    axes[0].set_title(f"Every beam over time. The log stops at {last:.1f} s "
                      "(the monitor only writes a row when new data arrives).")
    axes[-1].set_xlabel("time (s)")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(out, dpi=100)
    plt.close(fig)


def plot_summary(flights, out):
    """All figure-8 flights against the plan: one overlay, then one small panel per flight."""
    plt = _pyplot()
    n = len(flights)
    cols = 4
    rows = 1 + math.ceil(n / cols)
    fig = plt.figure(figsize=(4 * cols, 4.2 * rows))
    fig.suptitle("Figure-8 flights: planned (dashed) vs flown (estimated position, takeoff to landing)", fontsize=12)
    grid = fig.add_gridspec(rows, cols)
    overlay = fig.add_subplot(grid[0, :2])
    width = flights[0][1]["width"]
    lim = 1.0

    def setup(ax, title):
        ax.set_aspect("equal")
        ax.set_xlim(lim, -lim)
        ax.set_ylim(-lim, lim)
        ax.set_title(title, fontsize=8)

    setup(overlay, "All flights on the same axes (FOLLOW parts only)")
    for log, info in flights:
        xs = [x if s == "FOLLOW" else math.nan for x, s in zip(log["x"], log["state"])]
        ys = [y if s == "FOLLOW" else math.nan for y, s in zip(log["y"], log["state"])]
        overlay.plot(ys, xs, color=STATE_COLORS["FOLLOW"], lw=1, alpha=0.45)
    for w in sorted({info["width"] for _log, info in flights}):
        curve = planned_curve(w)
        overlay.plot([p[1] for p in curve], [p[0] for p in curve], color=INK, lw=1.5, ls="--")
    overlay.plot([], [], color=STATE_COLORS["FOLLOW"], label="flown (one line per flight)")
    overlay.plot([], [], color=INK, ls="--", label=f"planned ({width:.2f} m wide)")
    overlay.legend(loc="lower left", frameon=False, fontsize=8)
    overlay.set_xlabel("Y (m)  <- left   right ->")
    overlay.set_ylabel("X (m)  front ->")

    table = fig.add_subplot(grid[0, 2:])
    table.axis("off")
    lines = [f"{'flight':20s} {'avg off path':>12s} {'max':>6s} {'avoid':>6s}  ending"]
    for log, info in flights:
        if "path_err_mean" in info:
            errors = f"{info['path_err_mean'] * 100:10.0f} cm {info['path_err_max'] * 100:4.0f} cm"
        else:
            errors = f"{'-':>13s} {'-':>7s}"
        lines.append(f"{log['stamp'][11:] + ' ' + log['kind'][:2]:20s} {errors} "
                     f"{info['avoid_count']:5d}   {info['ending'][:34]}")
    table.text(0, 1, "\n".join(lines), va="top", family="monospace", fontsize=8, transform=table.transAxes)

    for k, (log, info) in enumerate(flights):
        ax = fig.add_subplot(grid[1 + k // cols, k % cols])
        setup(ax, f"{log['stamp'][11:]} {log['kind']}\n{info['ending'][:45]}")
        curve = planned_curve(info["width"])
        ax.plot([p[1] for p in curve], [p[0] for p in curve], color=INK, lw=1.2, ls="--")
        t, states = log["t"], log["state"]
        i = 0
        while i < len(t) - 1:
            j = i
            while j < len(t) - 1 and states[j + 1] == states[i]:
                j += 1
            ax.plot(log["y"][i:j + 2], log["x"][i:j + 2], color=STATE_COLORS.get(states[i], OTHER_STATE_COLOR),
                    lw=1.4)
            i = j + 1
        if not info["took_off"]:
            ax.annotate("never took off", (0, 0), xytext=(0, 20), textcoords="offset points", ha="center")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(out, dpi=100)
    plt.close(fig)


# --------------------------------------------------------------------------
# Text summary
# --------------------------------------------------------------------------

def markdown_table(results):
    head = ("| log | took off | duration | ending | avoid | FOLLOW/AVOID/WAIT/RETURN (s) | "
            "off path avg/max | height avg, std | battery start/min | your note |")
    lines = [head, "|" + "---|" * 10]
    for log, info in results:
        st = info["state_time"]
        states = "/".join(f"{st.get(s, 0):.0f}" for s in FLIGHT_STATES)
        path = (f"{info['path_err_mean'] * 100:.0f}/{info['path_err_max'] * 100:.0f} cm"
                if "path_err_mean" in info else "-")
        height = f"{info['z_mean']:.2f} m, {info['z_std'] * 100:.1f} cm" if "z_mean" in info else "-"
        batt = f"{info['vbat_start']:.2f}/{info['vbat_min']:.2f} V" if "vbat_start" in info else "-"
        took_off = "-" if log["kind"].startswith("02") else "yes" if info["took_off"] else "**NO**"
        lines.append(f"| {log['name']} | {took_off} | {info['duration']:.1f} s | "
                     f"{info['ending']} | {info['avoid_count']} | {states} | {path} | {height} | {batt} | {info.get('note', '')} |")
    return "\n".join(lines) + "\n"


def main():
    import matplotlib
    matplotlib.use("Agg")       # files only, no windows
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", default=[str(config.LOG_DIR)], help="CSV logs or folders (default: logs/)")
    parser.add_argument("--out", default=str(config.LOG_DIR / "plots"), help="where to save the plots")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for path in find_logs(args.paths):
        try:
            log = load_log(path)
        except (OSError, csv.Error, KeyError, ValueError) as e:
            print(f"SKIPPED {path.name}: {e}")
            continue
        if log["rows"] < 2:
            print(f"SKIPPED {path.name}: empty")
            continue
        info = analyze(log)
        out = out_dir / f"{log['name']}.png"
        if is_figure8(log):
            plot_figure8_flight(log, info, out)
        elif log["kind"].startswith("01"):
            plot_hover_flight(log, info, out)
        elif log["kind"].startswith("02"):
            plot_ranger_monitor(log, info, out)
        else:
            print(f"SKIPPED {path.name}: unknown log type '{log['kind']}'")
            continue
        results.append((log, info))
        print(f"\n{log['name']}  ->  {out}")
        for line in summary_lines(info):
            print("   " + line)

    flights = [(log, info) for log, info in results if is_figure8(log) and not is_dry_run(log)]
    if flights:
        out = out_dir / "figure8_summary.png"
        plot_summary(flights, out)
        print(f"\nSummary plot: {out}")
    if results:
        (out_dir / "summary.md").write_text(markdown_table(results))
        print(f"Summary table: {out_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
