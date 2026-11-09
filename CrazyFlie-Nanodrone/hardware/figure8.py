"""
figure8.py - the figure-8 path, shared by 03, 04 and their dry runs.

This is the same curve as Unity's Figure8Controller (a "lemniscate of Gerono"),
converted from Unity's frame (X right, Y up, Z forward) to the Crazyflie frame
(X forward, Y left, Z up) with   x_cf = z_unity,   y_cf = -x_unity:

    Unity:      x_u = R sin(t)            z_u = R sin(t) cos(t)
    Crazyflie:  x   = R sin(t) cos(t)     y   = -R sin(t)

t = 0 is the crossing point in the middle, where the drone takes off. The first
move is forward and to the right, just like in the simulation.

Unlike Unity, the speed setting here is a real speed in m/s (the average along
the path), not an angle rate.
"""

import math


def figure8_point(theta, width):
    """(x, y) of the figure-8 at curve angle theta (radians)."""
    r = width / 2
    return r * math.sin(theta) * math.cos(theta), -r * math.sin(theta)


def path_length(width, steps=2000):
    """Length of one full figure-8 in metres (measured numerically)."""
    total = 0.0
    prev = figure8_point(0.0, width)
    for i in range(1, steps + 1):
        p = figure8_point(2 * math.pi * i / steps, width)
        total += math.dist(prev, p)
        prev = p
    return total


class Figure8:
    """Moves a target point along the figure-8 at a chosen average speed.

    Call advance(dt) every control tick and read position(). Not calling
    advance() pauses the figure-8; this is how 04 "stops the clock" during avoidance.
    Speed ramps up smoothly from zero at the start (and after each restart_ramp()),
    and down again before the last lap ends.
    """

    def __init__(self, width, avg_speed, laps, ramp_time):
        self.width = width
        self.ramp_time = ramp_time
        self.length = path_length(width)
        self.omega = 2 * math.pi * avg_speed / self.length    # curve angle per second
        self.end_theta = 2 * math.pi * laps
        self.theta = 0.0
        self.ramp_elapsed = 0.0

    @property
    def period(self):
        """Seconds for one lap at full speed."""
        return 2 * math.pi / self.omega

    @property
    def peak_speed(self):
        """Fastest speed along the path (at the crossing point), m/s."""
        return (self.width / 2) * self.omega * math.sqrt(2)

    @property
    def done(self):
        return self.theta >= self.end_theta

    @property
    def laps_done(self):
        return self.theta / (2 * math.pi)

    def position(self):
        return figure8_point(self.theta, self.width)

    def restart_ramp(self):
        """Start again from standstill (used after rejoining the path)."""
        self.ramp_elapsed = 0.0

    def advance(self, dt):
        self.ramp_elapsed += dt
        factor = 1.0
        if self.ramp_time > 0:
            speed_up = self.ramp_elapsed / self.ramp_time
            # slow down over the last half ramp-time worth of path, but never stop completely
            slow_down = (self.end_theta - self.theta) / (self.omega * self.ramp_time / 2)
            factor = max(0.15, min(1.0, speed_up, slow_down))
        self.theta = min(self.theta + self.omega * factor * dt, self.end_theta)


# --------------------------------------------------------------------------
# Command-line options shared by 03_figure8.py and 04_figure8_avoid.py
# --------------------------------------------------------------------------

def add_figure8_args(parser, cfg):
    parser.add_argument("--width", type=float, default=cfg.FIG8_WIDTH,
                        help="left-right size in m (depth is half of this)")
    parser.add_argument("--speed", type=float, default=cfg.FIG8_SPEED, help="average speed in m/s")
    parser.add_argument("--laps", type=int, default=cfg.FIG8_LAPS, help="number of figure-8s")
    parser.add_argument("--height", type=float, default=cfg.FLIGHT_HEIGHT, help="flight height in m")
    parser.add_argument("--dry-run", action="store_true", help="simulate and plot only, do not connect")
    parser.add_argument("--no-show", action="store_true", help="with --dry-run: save the plot, don't open it")


def check_figure8_args(parser, args, cfg):
    """Refuse settings that are unsafe or don't fit the geofence. Returns a Figure8."""
    if not 0.2 <= args.height <= cfg.GEOFENCE_MAX_HEIGHT - 0.1:
        parser.error(f"--height must be between 0.2 and {cfg.GEOFENCE_MAX_HEIGHT - 0.1:.1f} m")
    if args.laps < 1 or args.speed <= 0 or args.width <= 0:
        parser.error("--laps must be at least 1, --speed and --width above 0")
    if args.width / 2 > cfg.GEOFENCE_RADIUS - cfg.GEOFENCE_MARGIN - cfg.RETREAT_DISTANCE:
        parser.error("--width is too big for the geofence (it must leave room for avoidance moves)")
    fig8 = Figure8(args.width, args.speed, args.laps, cfg.FIG8_RAMP_TIME)
    if fig8.peak_speed > cfg.MAX_SPEED:
        parser.error(f"the peak speed would be {fig8.peak_speed:.2f} m/s, above MAX_SPEED = {cfg.MAX_SPEED} m/s")
    return fig8


def describe(fig8, args, cfg):
    """Lines printed before takeoff (and in dry runs) explaining the plan."""
    return [f"Figure-8: {args.width:.2f} m wide (left-right) x {args.width / 2:.2f} m deep (front-back), "
            f"{args.laps} lap(s) at {args.height:.2f} m height.",
            f"Average speed {args.speed:.2f} m/s, peak {fig8.peak_speed:.2f} m/s at the crossing point, "
            f"{fig8.period:.1f} s per lap.",
            f"Geofence: {cfg.GEOFENCE_RADIUS} m around the start, max height {cfg.GEOFENCE_MAX_HEIGHT} m."]
