"""
dry_run.py - pieces for --dry-run: a simulated drone, fake people, a fake
Multi-ranger, and the plots. Nothing here talks to the real drone.
"""

import math
import random

from avoidance import BEAM_DIRECTIONS

# Colours: states and beams each get their own fixed colour; beams also differ
# by line style so the plot still reads without colour.
STATE_COLORS = {"FOLLOW": "#2a78d6", "AVOID": "#eb6834", "WAIT": "#1baf7a", "RETURN": "#eda100"}
BEAM_STYLES = {"front": ("#e87ba4", "-"), "back": ("#008300", "--"),
               "left": ("#6250d6", "-."), "right": ("#e34948", ":")}
INK, MUTED, GRID = "#2b2b2b", "#77766f", "#e4e3dd"
OUT_OF_RANGE = 8.0      # what our fake sensor reports when it sees nothing (like the real one)


class SimDrone:
    """A very simple drone: it moves towards its setpoint with a short lag and a speed limit."""

    def __init__(self, lag, max_speed=1.0):
        self.lag = lag
        self.max_speed = max_speed
        self.pos = (0.0, 0.0)

    def step(self, setpoint, dt):
        vx = (setpoint[0] - self.pos[0]) / self.lag
        vy = (setpoint[1] - self.pos[1]) / self.lag
        speed = math.hypot(vx, vy)
        if speed > self.max_speed:
            vx, vy = vx * self.max_speed / speed, vy * self.max_speed / speed
        self.pos = (self.pos[0] + vx * dt, self.pos[1] + vy * dt)


class FakePerson:
    """Waits at start, walks in a straight line to end at a fixed speed, then leaves.

    A person with speed 0 just stands at start the whole time.
    """

    def __init__(self, start, end, speed, delay, radius=0.2):
        self.start, self.end = start, end
        self.speed, self.delay, self.radius = speed, delay, radius
        self.length = math.dist(start, end)

    def position(self, t):
        """(x, y), or None once they have left."""
        if self.speed <= 0 or self.length == 0:
            return self.start
        walked = max(0.0, t - self.delay) * self.speed
        if walked >= self.length:
            return None
        f = walked / self.length
        return (self.start[0] + f * (self.end[0] - self.start[0]),
                self.start[1] + f * (self.end[1] - self.start[1]))


def fake_ranges(pos, yaw_deg, people, t, cfg, rng):
    """What the Multi-ranger would read. Returns (readings, glitched_beams).

    Each beam is a narrow cone (DRY_RUN_BEAM_HALF_ANGLE to each side). A person
    is a circle; the beam reports the distance to the nearest edge of anyone
    inside its cone. Noise and random short "glitch" readings are added so you
    can see the filter ignore them.
    """
    half = math.radians(cfg.DRY_RUN_BEAM_HALF_ANGLE)
    yaw = math.radians(yaw_deg)
    readings, glitched = {}, []
    for beam, (bx, by) in BEAM_DIRECTIONS.items():
        dx, dy = bx * math.cos(yaw) - by * math.sin(yaw), bx * math.sin(yaw) + by * math.cos(yaw)
        best = OUT_OF_RANGE
        for person in people:
            where = person.position(t)
            if where is None:
                continue
            vx, vy = where[0] - pos[0], where[1] - pos[1]
            d = math.hypot(vx, vy)
            if d <= person.radius:
                best = min(best, 0.05)
                continue
            angle = math.acos(max(-1.0, min(1.0, (vx * dx + vy * dy) / d)))
            if angle <= half + math.asin(person.radius / d):
                best = min(best, d - person.radius)
        if best < cfg.RANGE_MAX_VALID:
            best = max(0.0, best + rng.gauss(0.0, cfg.DRY_RUN_RANGE_NOISE))
        if rng.random() < cfg.DRY_RUN_GLITCH_CHANCE:
            best = rng.uniform(0.1, 0.5)
            glitched.append(beam)
        readings[beam] = best
    readings["up"] = OUT_OF_RANGE
    return readings, glitched


def make_rng(cfg):
    return random.Random(cfg.DRY_RUN_SEED)


# --------------------------------------------------------------------------
# Plots
# --------------------------------------------------------------------------

def _pyplot():
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise SystemExit("matplotlib is not installed. Run:  pip install -r requirements.txt")
    plt.rcParams.update({"axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                         "ytick.color": MUTED, "text.color": INK, "axes.grid": True,
                         "grid.color": GRID, "grid.linewidth": 0.8, "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False})
    return plt


def _top_view(ax, cfg):
    """Set up a bird's-eye view: drone's front points UP the page, its left is to the LEFT."""
    import matplotlib.patches as patches
    ax.add_patch(patches.Circle((0, 0), cfg.GEOFENCE_RADIUS, fill=False, ls="--", lw=1, ec=MUTED))
    ax.annotate("geofence", (0, cfg.GEOFENCE_RADIUS), xytext=(0, 4), textcoords="offset points",
                ha="center", color=MUTED)
    ax.plot(0, 0, marker="s", ms=8, color=INK, ls="none", label="start / takeoff point")
    ax.set_aspect("equal")
    lim = cfg.GEOFENCE_RADIUS + 0.2
    ax.set_xlim(lim, -lim)              # Y axis reversed so the drone's left is on the left
    ax.set_ylim(-lim, lim)
    ax.set_xlabel("Y (m)  <- drone's left        drone's right ->")
    ax.set_ylabel("X (m)  drone's front ->")


def _finish(plt, fig, save_path, show):
    fig.savefig(save_path, dpi=120)
    print(f"Plot saved to {save_path}")
    if show:
        plt.show()
    plt.close(fig)


def plot_figure8_plan(times, points, speeds, cfg, title, save_path, show=True):
    """03 dry run: the planned path from above, and the speed over time."""
    plt = _pyplot()
    fig, (ax, ax_speed) = plt.subplots(1, 2, figsize=(12, 5.5), gridspec_kw={"width_ratios": [1.1, 1]})
    fig.suptitle(title)
    _top_view(ax, cfg)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    ax.plot(ys, xs, color=STATE_COLORS["FOLLOW"], lw=2, label="planned path")
    step = max(1, int(round(1.0 / (times[1] - times[0]))))      # one dot per second
    ax.plot(ys[::step], xs[::step], "o", ms=4, color=STATE_COLORS["FOLLOW"], label="1 s apart")
    if len(xs) > 5:
        ax.annotate("", xy=(ys[5], xs[5]), xytext=(ys[0], xs[0]),
                    arrowprops=dict(arrowstyle="->", color=INK, lw=1.5))
    ax.legend(loc="lower left", frameon=False)

    ax_speed.plot(times, speeds, color=STATE_COLORS["FOLLOW"], lw=2)
    ax_speed.axhline(cfg.MAX_SPEED, color=MUTED, ls="--", lw=1)
    ax_speed.annotate(f"speed limit {cfg.MAX_SPEED} m/s", (times[-1], cfg.MAX_SPEED), ha="right",
                      va="bottom", color=MUTED)
    ax_speed.set_ylim(0, cfg.MAX_SPEED * 1.2)
    ax_speed.set_xlabel("time (s)")
    ax_speed.set_ylabel("speed along the path (m/s)")
    ax_speed.set_title("Planned speed")
    fig.tight_layout()
    _finish(plt, fig, save_path, show)


def plot_avoid_run(rec, events, people, cfg, title, save_path, show=True):
    """04 dry run: path coloured by state, ranger readings, and state timeline.

    rec: dict of lists  t, state, x, y, plan_x, plan_y, <beam readings>, glitch (list of beams)
    events: list of (t, state, beam, x, y, text)
    """
    plt = _pyplot()
    fig = plt.figure(figsize=(14, 7.5))
    fig.suptitle(title)
    grid = fig.add_gridspec(2, 2, width_ratios=[1, 1.25], height_ratios=[1.6, 1])
    ax = fig.add_subplot(grid[:, 0])
    ax_r = fig.add_subplot(grid[0, 1])
    ax_s = fig.add_subplot(grid[1, 1], sharex=ax_r)

    # --- bird's-eye view -----------------------------------------------------
    _top_view(ax, cfg)
    ax.plot(rec["plan_y"], rec["plan_x"], color=MUTED, lw=1, ls=":", label="figure-8 (no person)")
    t, states = rec["t"], rec["state"]
    i = 0
    while i < len(t) - 1:                       # one line piece per stretch of the same state
        j = i
        while j < len(t) - 1 and states[j + 1] == states[i]:
            j += 1
        ax.plot(rec["y"][i:j + 2], rec["x"][i:j + 2], color=STATE_COLORS[states[i]], lw=2.2,
                solid_capstyle="round")
        i = j + 1
    for state, color in STATE_COLORS.items():
        ax.plot([], [], color=color, lw=2.2, label=f"drone: {state}")
    for n, person in enumerate(people):
        (x0, y0), (x1, y1) = person.start, person.end
        ax.plot([y0, y1], [x0, x1], color=INK, alpha=0.5, lw=1,
                label="fake person's walk" if n == 0 else None)
        if person.length > 0:                  # arrowhead near the middle shows the walking direction
            ax.annotate("", xy=((y0 + y1) / 2, (x0 + x1) / 2),
                        xytext=((y0 + y1) / 2 - 0.15 * (y1 - y0) / person.length,
                                (x0 + x1) / 2 - 0.15 * (x1 - x0) / person.length),
                        arrowprops=dict(arrowstyle="-|>", color=INK, alpha=0.6))
    for (te, state, beam, x, y, _text) in events:
        if state == "AVOID" and beam:
            ax.plot(y, x, marker="v", ms=9, color=STATE_COLORS["AVOID"], mec="white", mew=1.5)
            ax.annotate(f"{beam} @ {te:.1f}s", (y, x), xytext=(6, 6), textcoords="offset points",
                        color=INK)
            for person in people:
                where = person.position(te)
                if where is not None:
                    ax.plot(where[1], where[0], marker="o", ms=10, mfc="none", mec=INK)
    ax.legend(loc="lower left", frameon=False, fontsize=8)
    ax.set_title("Bird's-eye view (circles = person when AVOID started)")

    # --- ranger readings -----------------------------------------------------
    shown_max = 2.0
    for beam, (color, style) in BEAM_STYLES.items():
        # glitch samples are left out of the line and drawn as crosses instead
        values = [math.nan if beam in g else min(v, shown_max) for v, g in zip(rec[beam], rec["glitch"])]
        ax_r.plot(t, values, color=color, ls=style, lw=1.6, label=beam)
    gt = [tt for tt, g in zip(t, rec["glitch"]) for _ in g]
    gv = [min(rec[b][k], shown_max) for k, g in enumerate(rec["glitch"]) for b in g]
    ax_r.plot(gt, gv, "x", color=INK, ms=6, label="fake glitch (filtered out)")
    for level, label in ((cfg.AVOID_DISTANCE, "avoid"), (cfg.CLEAR_DISTANCE, "clear")):
        ax_r.axhline(level, color=MUTED, ls="--", lw=1)
        ax_r.annotate(f"{label} {level} m", (t[-1], level), ha="right", va="bottom", color=MUTED)
    ax_r.set_ylim(0, shown_max + 0.45)
    ax_r.set_ylabel(f"ranger reading (m, {shown_max} = nothing near)")
    ax_r.set_title("Multi-ranger (fake) readings")
    ax_r.legend(loc="upper left", ncol=5, frameon=False, fontsize=8)

    # --- state timeline ------------------------------------------------------
    names = list(STATE_COLORS)
    dt = t[1] - t[0] if len(t) > 1 else 0.05
    for row, state in enumerate(names):
        spans, start = [], None
        for tt, s in zip(t, states):
            if s == state and start is None:
                start = tt
            elif s != state and start is not None:
                spans.append((start, tt - start))
                start = None
        if start is not None:
            spans.append((start, t[-1] + dt - start))
        ax_s.broken_barh(spans, (row - 0.35, 0.7), color=STATE_COLORS[state])
    for (te, state, beam, _x, _y, _text) in events:
        if state == "AVOID" and beam:
            ax_s.annotate(beam, (te, names.index("AVOID") - 0.4), ha="left", va="bottom", color=INK,
                          fontsize=8, rotation=45)
    ax_s.set_yticks(range(len(names)), names)
    ax_s.set_ylim(len(names) - 0.4, -0.6)
    ax_s.set_xlabel("time (s)")
    ax_s.set_title("State (label = beam that fired)")
    ax_s.grid(axis="y", visible=False)
    fig.tight_layout()
    _finish(plt, fig, save_path, show)
