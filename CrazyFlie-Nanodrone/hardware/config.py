"""
config.py - every setting used by the hardware scripts, in one place.

Units: metres (m), seconds (s), metres per second (m/s), volts (V).

Positions are in the Crazyflie "world" frame, which the scripts create when they
reset the position estimator just before takeoff:
    origin = the spot where the drone sits on the floor (the takeoff point)
    +X     = the direction the drone's front points at that moment
    +Y     = the drone's left
    +Z     = up
Place the drone at the CENTRE (crossing point) of where you want the figure-8.

Most values can also be overridden on the command line (run a script with --help).
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Radio link
# --------------------------------------------------------------------------
URI = "radio://0/80/2M/E7E7E7E7E7"
CACHE_DIR = HERE / "cache"          # cflib stores the drone's variable list here (faster connect)
LOG_DIR = HERE / "logs"             # flight logs (CSV) and dry-run plots (PNG)
NOTES_FILE = LOG_DIR / "FLIGHT_NOTES.md"   # one line per flight, asked for after landing

# --------------------------------------------------------------------------
# Basic flight
# --------------------------------------------------------------------------
FLIGHT_HEIGHT = 0.5                 # m above the floor (Unity used 2.5 m; scaled down)
TAKEOFF_TIME = 2.5                  # s to climb to FLIGHT_HEIGHT
LANDING_SPEED = 0.25                # m/s downward during landing
HOVER_TIME = 10.0                   # s, used by 01_hover_test.py
CONTROL_RATE_HZ = 20                # how often we send a position setpoint (firmware needs > 2 Hz)
LOG_PERIOD_MS = 50                  # how often the drone sends us its data (50 ms = 20 Hz)
MAX_SPEED = 0.5                     # m/s, scripts refuse settings that need a faster figure-8

# --------------------------------------------------------------------------
# Figure-8 (same shape as Unity's Figure8Controller, scaled down)
#   Unity:    x = R sin(t),  z = R sin(t) cos(t)    with R = 2 m  -> 4 m wide, 2 m deep
#   Here:     y = -R sin(t), x = R sin(t) cos(t)    with R = WIDTH / 2
#   The long side runs left-right (Y), the short side front-back (X).
#   Depth is always half the width, exactly as in the simulation.
# --------------------------------------------------------------------------
FIG8_WIDTH = 1.0                    # m, left-right size (depth = 0.5 m)
FIG8_SPEED = 0.25                   # m/s AVERAGE speed along the path (peak is about 1.46x)
FIG8_LAPS = 2                       # how many figure-8s to fly before landing
FIG8_RAMP_TIME = 3.0                # s to speed up from standstill (and to slow down at the end)
FIG8_HOVER_TIME = 4.0               # s hovering at the centre before the figure-8 starts (03 and 04):
                                    # lets the height settle after takeoff and checks the room

# --------------------------------------------------------------------------
# Person avoidance (04_figure8_avoid.py)
# --------------------------------------------------------------------------
AVOID_BEAMS = ("front", "back", "left", "right")   # the up beam is ignored on purpose
AVOID_DISTANCE = 0.6                # m, a beam closer than this (confirmed) starts AVOID
CLEAR_DISTANCE = 1.0                # m, to return to the path, the beams that saw the person and the
                                    # beam facing the way back must see further than this
AVOID_CONFIRM_COUNT = 3             # consecutive close readings needed before AVOID (glitch filter).
                                    # The sensor measures ~10x per second and each measurement arrives
                                    # twice, so 3 readings = 2 measurements, about 0.15 s.
CLEAR_TIME = 2.0                    # s the area must stay clear before returning to the path
RETREAT_DISTANCE = 0.3              # m, sideways step, and the shortest move away from the person
MAX_RETREAT_DISTANCE = 0.6          # m, longest move away from the person
RETREAT_MARGIN = 0.1                # m, backing away aims for CLEAR_DISTANCE + this from the person
RETREAT_FREE_MARGIN = 0.3           # m, extra free space needed on the side we move towards
AVOID_SPEED = 0.4                   # m/s while moving away
# Someone walking AT the drone: backing away along their line can't work (they are
# faster), and 0.6 m is too late a warning. So when the object itself moves towards
# the drone faster than APPROACH_SPEED, AVOID already starts at EARLY_AVOID_DISTANCE
# and dodges sideways first. The drone's own movement is taken out, so flying towards
# a wall does not count as "approaching". Set it to 99 to switch this off.
APPROACH_SPEED = 0.25               # m/s
EARLY_AVOID_DISTANCE = 1.2          # m
RETURN_SPEED = 0.2                  # m/s while flying back to the figure-8
POSITION_TOLERANCE = 0.10           # m, "close enough" to a target point
SETTLE_TIME = 2.0                   # s, max wait for the drone to settle on a target point
MAX_PAUSE_TIME = 25.0               # s, land if the figure-8 stays paused (avoiding) longer than this

# Multi-ranger reading filter
RANGE_MIN_VALID = 0.02              # m, readings below this are glitches and are ignored
RANGE_MAX_VALID = 4.0               # m, readings at/above this mean "nothing in range"
DROPOUT_HOLD_TIME = 0.5             # s, "nothing in range" this soon after a real reading may be a
                                    # sensor dropout: it does not count as clear until this has passed

# --------------------------------------------------------------------------
# Safety limits (checked many times per second in every flying script)
# --------------------------------------------------------------------------
GEOFENCE_RADIUS = 1.5               # m, max horizontal distance from the takeoff point
GEOFENCE_MAX_HEIGHT = 1.2           # m, max height
GEOFENCE_MARGIN = 0.2               # m, avoidance targets are kept this far inside the fence
MIN_TAKEOFF_VOLTAGE = 3.9           # V, refuse to take off below this (full battery = 4.2 V)
LAND_VOLTAGE = 3.3                  # V, land if the battery stays below this in flight
LOW_BATTERY_TIME = 1.0              # s the voltage must stay low (ignores short sags)
TELEMETRY_TIMEOUT = 0.5             # s without data from the drone -> land
LAND_RESEND_PERIOD = 0.25           # s, while no data arrives during landing, repeat the land command
TAKEOFF_MIN_HEIGHT_FRACTION = 0.5   # after takeoff the drone must be at least this part of the target
                                    # height, or the script stops ("did not take off")
HEIGHT_ERROR_LIMIT = 0.20           # m between target and actual height ...
HEIGHT_ERROR_TIME = 0.5             # ... for this long -> land
MAX_FLIGHT_TIME = 120.0             # s, land after this no matter what
ESTIMATOR_TIMEOUT = 15.0            # s to wait for the position estimate to settle

# --------------------------------------------------------------------------
# Dry run (--dry-run): no drone, everything is simulated on the computer
# --------------------------------------------------------------------------
DRY_RUN_DRONE_LAG = 0.3             # s, how sluggishly the simulated drone follows its setpoint
DRY_RUN_RANGE_NOISE = 0.02          # m, random noise added to fake ranger readings
DRY_RUN_GLITCH_CHANCE = 0.01        # chance per reading of a fake too-short glitch (tests the filter)
DRY_RUN_BEAM_HALF_ANGLE = 13.5      # degrees, half the cone width of one Multi-ranger beam
DRY_RUN_SEED = 1                    # random seed, so a dry run is repeatable

# Fake people for the 04 dry run. Each person walks in a straight line from
# 'start' to 'end' (x, y in metres) at 'speed' m/s, starting at time 'delay' s
# after the figure-8 begins, and leaves the room when they reach 'end'.
# 'radius' is the size of their body as the sensor sees it.
# The figure-8 covers x = -0.25..0.25, y = -0.5..0.5 with the default size.
FAKE_PEOPLE = [
    # walks from the drone's left to its right at a slow walking pace, crossing the
    # front part of the figure-8
    dict(start=(0.35, 2.0), end=(0.35, -2.0), speed=0.8, delay=3.0, radius=0.2),
]
