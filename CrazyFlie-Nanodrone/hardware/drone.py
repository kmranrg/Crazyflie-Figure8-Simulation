"""
drone.py - everything that talks to the Crazyflie through cflib:
connecting, pre-flight checks, live data (telemetry), takeoff, sending
positions with safety checks, and landing.

How a flight works (the same pattern as Bitcraze's own cflib examples):
  1. connect, check decks and battery            (drone on the floor)
  2. reset the position estimator and arm motors (drone on the floor)
  3. high-level commander takeoff                (the drone climbs by itself)
  4. stream position setpoints at 20 Hz          (our code is in control)
  5. send_notify_setpoint_stop + high-level land (the drone lands by itself)
In step 5 the landing runs ON THE DRONE, so it finishes even if this program
or the radio link dies afterwards.
"""

import math
import signal
import threading
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.supervisor import BIT_IS_CRASHED, BIT_IS_LOCKED, BIT_IS_TUMBLED
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.syncLogger import SyncLogger

from common import FlightLogger, KeyboardStop, RateKeeper, add_flight_note

RANGE_NAMES = ("front", "back", "left", "right", "up", "zrange")

# pm.state values reported by the firmware
PM_CHARGING, PM_CHARGED, PM_LOW_POWER = 1, 2, 3

# Log variables whose short name would be unclear in the snapshot / CSV
SHORT_NAMES = {"supervisor.info": "supinfo"}


def supervisor_problem(bits):
    """'crashed', 'locked' or 'upside down' from the supervisor.info bit field (None if all is well)."""
    if bits is None:
        return None
    bits = int(bits)
    for bit, text in ((BIT_IS_CRASHED, "crashed"), (BIT_IS_LOCKED, "locked"), (BIT_IS_TUMBLED, "upside down")):
        if bits >> bit & 1:
            return text
    return None


def restart_message(why):
    """The big 'restart the drone' notice shown after a crash or lock."""
    bar = "!" * 72
    return (f"\n{bar}\n"
            f"  RESTART THE DRONE BEFORE THE NEXT FLIGHT ({why}).\n"
            f"  1. Switch it off with the power button, wait 2 s, switch it on again.\n"
            f"  2. Check all four propellers and that it sits flat on the floor.\n"
            f"  3. Then run the script again (if the drone is locked, it refuses to fly until restarted).\n"
            f"{bar}")


class PreflightError(Exception):
    """A check failed before takeoff. The drone never left the ground."""


class AbortFlight(Exception):
    """Something unsafe happened in flight. The caller must land."""


def connect(cfg):
    """Return a SyncCrazyflie; use it as   with connect(config) as scf: ..."""
    cflib.crtp.init_drivers()
    cfg.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Connecting to {cfg.URI} ...")
    return SyncCrazyflie(cfg.URI, cf=Crazyflie(rw_cache=str(cfg.CACHE_DIR)))


def connection_help():
    print("Could not connect. Check that:\n"
          "  - the Crazyflie is switched on (blue LEDs at the back are lit)\n"
          "  - the Crazyradio is plugged in and no other program (e.g. cfclient) is using it\n"
          "  - the URI in config.py matches your drone (scripts/detect_decks.py can scan for it)")


# --------------------------------------------------------------------------
# Live data from the drone
# --------------------------------------------------------------------------

class Telemetry:
    """Keeps the newest position, battery and ranger values sent by the drone.

    The drone streams two "log blocks" (a block can carry at most 26 bytes):
      Pose:   stateEstimate.x/y/z/yaw, pm.vbat, pm.state
      Ranges: range.front/back/left/right/up/zrange, motion.squal,
              supervisor.info (crashed / locked / ... bits), radio.rssi
    plus the radio link quality (0-100 %) measured by cflib on this computer.
    Variables that the drone does not have (e.g. a deck is missing) are skipped.
    """

    def __init__(self, cf, period_ms):
        self.cf = cf
        self._lock = threading.Lock()
        self._data = {}
        self._pose_time = None
        self.range_count = 0          # goes up by one with every new ranger packet
        toc = cf.log.toc

        def block(name, variables):
            conf = LogConfig(name=name, period_in_ms=period_ms)
            for var, ctype in variables:
                if toc.get_element_by_complete_name(var) is not None:
                    conf.add_variable(var, ctype)
            return conf

        self._pose = block("Pose", [("stateEstimate.x", "float"), ("stateEstimate.y", "float"),
                                    ("stateEstimate.z", "float"), ("stateEstimate.yaw", "float"),
                                    ("pm.vbat", "float"), ("pm.state", "int8_t")])
        self._ranges = block("Ranges", [(f"range.{n}", "uint16_t") for n in RANGE_NAMES]
                             + [("motion.squal", "uint8_t"), ("supervisor.info", "uint16_t"),
                                ("radio.rssi", "uint8_t")])

    def start(self):
        self.cf.link_statistics.link_quality_updated.add_callback(self._on_link_quality)
        for conf, callback in ((self._pose, self._on_pose), (self._ranges, self._on_ranges)):
            if not conf.variables:
                continue
            self.cf.log.add_config(conf)
            conf.data_received_cb.add_callback(callback)
            conf.error_cb.add_callback(lambda c, msg: print(f"Log error in {c.name}: {msg}"))
            conf.start()

    def stop(self):
        try:
            self.cf.link_statistics.link_quality_updated.remove_callback(self._on_link_quality)
        except Exception:
            pass
        for conf in (self._pose, self._ranges):
            try:
                conf.stop()
            except Exception:
                pass

    def _on_pose(self, timestamp, data, logconf):
        with self._lock:
            for var, value in data.items():
                self._data[var.split(".")[1]] = value      # "stateEstimate.x" -> "x"
            self._pose_time = time.monotonic()

    def _on_ranges(self, timestamp, data, logconf):
        with self._lock:
            for var, value in data.items():
                key = SHORT_NAMES.get(var, var.split(".")[1])
                self._data[key] = value / 1000.0 if var.startswith("range.") else value   # mm -> m
            self.range_count += 1

    def _on_link_quality(self, quality):
        with self._lock:
            self._data["link"] = quality

    def snapshot(self):
        """A copy of the newest values, plus 'age' = seconds since the last position update."""
        with self._lock:
            snap = dict(self._data)
            snap["age"] = math.inf if self._pose_time is None else time.monotonic() - self._pose_time
            snap["range_count"] = self.range_count
            return snap

    def wait_for_data(self, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.snapshot()["age"] < 1.0:
                return
            time.sleep(0.05)
        raise PreflightError("No data received from the drone. Is the radio link OK?")


# --------------------------------------------------------------------------
# Pre-flight checks (the drone is still on the floor)
# --------------------------------------------------------------------------

def check_decks(cf, need_flow=True, need_ranger=True):
    wanted = []
    if need_flow:
        wanted.append(("bcFlow2", "Flow deck v2", "underneath"))
    if need_ranger:
        wanted.append(("bcMultiranger", "Multi-ranger deck", "on top"))
    deck_params = cf.param.toc.toc.get("deck", {})
    for param, name, where in wanted:
        found = param in deck_params and int(cf.param.get_value(f"deck.{param}")) == 1
        if not found:
            raise PreflightError(f"{name} NOT detected. Make sure it is pressed fully onto the pins "
                                 f"({where}), then switch the drone off and on again.")
        print(f"  OK   {name} detected")


def check_supervisor(cf, telemetry):
    """Refuse to fly when the drone reports it crashed, is locked or upside down."""
    bits = telemetry.snapshot().get("supinfo")
    if bits is None:                      # older firmware without the log variable: ask directly
        bits = cf.supervisor.read_bitfield()
    problem = supervisor_problem(bits)
    if problem:
        print(restart_message(f"the drone reports it is {problem}"))
        raise PreflightError(f"the drone reports it is {problem}. Restart it first.")
    print("  OK   drone ready (not crashed, locked or upside down)")


def configure(cf):
    """Use the Kalman estimator (needed for the Flow deck) and enable the high-level commander."""
    for name, value in (("stabilizer.estimator", "2"), ("commander.enHighLevel", "1")):
        if cf.param.toc.get_element_by_complete_name(name) is not None:
            cf.param.set_value(name, value)


def check_battery(telemetry, cfg):
    samples = []
    for _ in range(10):                 # average 1 s of readings
        v = telemetry.snapshot().get("vbat")
        if v:
            samples.append(v)
        time.sleep(0.1)
    if not samples:
        raise PreflightError("Could not read the battery voltage.")
    voltage = sum(samples) / len(samples)
    state = telemetry.snapshot().get("state")
    if state in (PM_CHARGING, PM_CHARGED):
        raise PreflightError("A USB cable / charger is connected. Unplug it before flying.")
    if voltage < cfg.MIN_TAKEOFF_VOLTAGE:
        raise PreflightError(f"Battery is {voltage:.2f} V, below the {cfg.MIN_TAKEOFF_VOLTAGE:.2f} V "
                             f"needed for takeoff. Charge it first (full = 4.2 V).")
    print(f"  OK   battery {voltage:.2f} V")


def reset_estimator(cf, telemetry, cfg):
    """Reset the Kalman position estimate to (0, 0, 0) and wait until it settles.

    Same method as cflib.utils.reset_estimator, but with a timeout instead of
    waiting forever.
    """
    print("Resetting the position estimator (keep the drone still on the floor) ...")
    cf.param.set_value("kalman.resetEstimation", "1")
    time.sleep(0.1)
    cf.param.set_value("kalman.resetEstimation", "0")

    conf = LogConfig(name="Variance", period_in_ms=100)
    for axis in ("X", "Y", "Z"):
        conf.add_variable(f"kalman.varP{axis}", "float")
    history = {axis: [1000.0] * 10 for axis in ("X", "Y", "Z")}
    deadline = time.monotonic() + cfg.ESTIMATOR_TIMEOUT
    with SyncLogger(cf, conf) as logger:
        for _timestamp, data, _conf in logger:
            for axis, values in history.items():
                values.append(data[f"kalman.varP{axis}"])
                values.pop(0)
            if all(max(v) - min(v) < 0.001 for v in history.values()):
                break
            if time.monotonic() > deadline:
                raise PreflightError("The position estimate did not settle. Check the floor has texture, "
                                     "the room is well lit, and the drone is not moving.")
    time.sleep(0.5)
    snap = telemetry.snapshot()
    if abs(snap.get("x", 9)) > 0.1 or abs(snap.get("y", 9)) > 0.1 or abs(snap.get("z", 9)) > 0.15:
        raise PreflightError(f"Position estimate looks wrong after reset "
                             f"(x={snap.get('x')}, y={snap.get('y')}, z={snap.get('z')}).")
    print("  OK   position estimate settled at the start point")


def confirm_takeoff(plan_lines):
    """Print what the drone is about to do and wait for Enter."""
    print("\n" + "=" * 64)
    for line in plan_lines:
        print("  " + line)
    print("  During flight: SPACE, q or Enter = land now,  k = cut motors,  Ctrl+C = land")
    print("=" * 64)
    input("Stand back. Press Enter to take off (Ctrl+C to cancel): ")


# --------------------------------------------------------------------------
# The flight itself
# --------------------------------------------------------------------------

class Flight:
    """Takeoff, one control tick at a time with safety checks, and landing."""

    def __init__(self, cf, cfg, telemetry, keys, logger):
        self.cf = cf
        self.cfg = cfg
        self.telemetry = telemetry
        self.keys = keys
        self.logger = logger
        self.rate = RateKeeper(cfg.CONTROL_RATE_HZ)
        self.t0 = time.monotonic()
        self.flying = False
        self.landed = False
        self.low_battery_since = None
        self.z_target = None                 # height we asked for (None during takeoff and landing)
        self.control_start = None            # when we started sending our own setpoints
        self.height_error_since = None
        self.needs_restart = None            # set to a reason after a crash, lock or failed takeoff

    def elapsed(self):
        return time.monotonic() - self.t0

    def safety_problem(self, snap):
        """Return a reason to land, or None if everything is fine."""
        cfg = self.cfg
        if self.keys.land_requested.is_set():
            return "land key pressed"
        if snap["age"] > cfg.TELEMETRY_TIMEOUT:
            return f"no position data from the drone for {snap['age']:.1f} s"
        distance = math.hypot(snap["x"], snap["y"])
        if distance > cfg.GEOFENCE_RADIUS:
            return f"GEOFENCE: {distance:.2f} m from the start point (limit {cfg.GEOFENCE_RADIUS} m)"
        if snap["z"] > cfg.GEOFENCE_MAX_HEIGHT:
            return f"GEOFENCE: height {snap['z']:.2f} m (limit {cfg.GEOFENCE_MAX_HEIGHT} m)"
        problem = supervisor_problem(snap.get("supinfo"))
        if problem:
            self.needs_restart = f"the drone reported it {problem} in flight"
            return f"the drone reports it is {problem}"
        if self.z_target is not None and self.elapsed() - self.control_start > 1.0:
            # the first second after takeoff is skipped: the height overshoots a little there
            error = abs(snap["z"] - self.z_target)
            if error > cfg.HEIGHT_ERROR_LIMIT:
                if self.height_error_since is None:
                    self.height_error_since = time.monotonic()
                if time.monotonic() - self.height_error_since > cfg.HEIGHT_ERROR_TIME:
                    return (f"HEIGHT: {snap['z']:.2f} m instead of {self.z_target:.2f} m "
                            f"for {cfg.HEIGHT_ERROR_TIME} s")
            else:
                self.height_error_since = None
        if snap.get("state") == PM_LOW_POWER:
            return "battery low (reported by the drone)"
        if snap.get("vbat", 4.2) < cfg.LAND_VOLTAGE:
            if self.low_battery_since is None:
                self.low_battery_since = time.monotonic()
            if time.monotonic() - self.low_battery_since > cfg.LOW_BATTERY_TIME:
                return f"battery low ({snap['vbat']:.2f} V)"
        else:
            self.low_battery_since = None
        if self.elapsed() > cfg.MAX_FLIGHT_TIME:
            return f"maximum flight time of {cfg.MAX_FLIGHT_TIME:.0f} s reached"
        return None

    def log(self, snap, state, setpoint=None, event="", beam=""):
        row = {k: snap.get(k) for k in ("x", "y", "z", "yaw", "vbat", "squal", "supinfo", "rssi", "link")
               + RANGE_NAMES}
        row.update(t=self.elapsed(), state=state, event=event, beam=beam)
        if setpoint:
            row.update(sp_x=setpoint[0], sp_y=setpoint[1], sp_z=setpoint[2])
        self.logger.write(row)

    def takeoff(self, height):
        cfg = self.cfg
        print(f">>> Arming and taking off to {height:.2f} m ...")
        self.cf.supervisor.send_arming_request(True)
        time.sleep(1.0)
        self.t0 = time.monotonic()
        self.flying = True
        self.cf.high_level_commander.takeoff(height, cfg.TAKEOFF_TIME)
        end = time.monotonic() + cfg.TAKEOFF_TIME + 0.5
        snap = None
        while time.monotonic() < end:
            snap = self.tick("TAKEOFF", None)     # watch safety, but let the drone climb by itself
        if snap["z"] < cfg.TAKEOFF_MIN_HEIGHT_FRACTION * height:
            problem = supervisor_problem(snap.get("supinfo"))
            why = f"the drone reports it is {problem}" if problem else "the motors did not lift it"
            self.needs_restart = f"it did not take off: {why}"
            self.log(snap, "TAKEOFF", event=f"ABORT: did not take off (height {snap['z']:.2f} m, {why})")
            raise AbortFlight(f"DID NOT TAKE OFF: height {snap['z']:.2f} m after {cfg.TAKEOFF_TIME + 0.5:.1f} s ({why})")
        print(f">>> In the air ({snap['z']:.2f} m).")

    def tick(self, state, setpoint, event="", beam=""):
        """One control step: safety check, send the (x, y, z) setpoint, log, wait.

        Raises AbortFlight if something is unsafe. Returns fresh telemetry.
        """
        cfg = self.cfg
        snap = self.telemetry.snapshot()
        problem = self.safety_problem(snap)
        if problem:
            self.log(snap, state, setpoint, f"ABORT: {problem}")
            raise AbortFlight(problem)
        if setpoint is not None:
            x, y, z = setpoint
            # never command a point outside the geofence, whatever the logic asked for
            limit = cfg.GEOFENCE_RADIUS - cfg.GEOFENCE_MARGIN
            distance = math.hypot(x, y)
            if distance > limit:
                x, y = x * limit / distance, y * limit / distance
            z = min(z, cfg.GEOFENCE_MAX_HEIGHT - 0.1)
            setpoint = (x, y, z)
            if self.control_start is None:
                self.control_start = self.elapsed()
            self.z_target = z
            self.cf.commander.send_position_setpoint(x, y, z, 0.0)   # yaw 0 degrees: keep facing +X
        if event:
            print(f"[{self.elapsed():6.1f} s] {event}")
        self.log(snap, state, setpoint, event, beam)
        self.rate.wait()
        return self.telemetry.snapshot()

    def hover_and_check_room(self, height, width, seconds):
        """Hover at the centre before the figure-8, and report how much room there is.

        Prints, per beam, how far the nearest thing is from the figure-8 path, with a
        warning when it is closer than CLEAR_DISTANCE (walls that close make
        avoidance awkward). Returns the last telemetry snapshot.
        """
        cfg = self.cfg
        readings = {b: [] for b in ("front", "back", "left", "right")}
        snap = None
        for _ in range(int(seconds * cfg.CONTROL_RATE_HZ)):
            snap = self.tick("HOVER", (0.0, 0.0, height))
            for beam, values in readings.items():
                d = snap.get(beam)
                if d is not None and cfg.RANGE_MIN_VALID <= d < cfg.RANGE_MAX_VALID:
                    values.append(d)
        reach = {"front": width / 4, "back": width / 4, "left": width / 2, "right": width / 2}
        lines, warnings = [], []
        ticks = max(1, int(seconds * cfg.CONTROL_RATE_HZ))
        for beam, values in readings.items():
            if len(values) < 0.3 * ticks:
                lines.append(f"{beam} nothing within {cfg.RANGE_MAX_VALID:.0f} m")
                continue
            values.sort()
            d = values[len(values) // 2]
            gap = d - reach[beam]
            lines.append(f"{beam} {d:.2f} m ({gap:.2f} m from the path)")
            if gap < cfg.CLEAR_DISTANCE:
                warnings.append(f"{beam}: something {gap:.2f} m from the figure-8 "
                                f"(want at least {cfg.CLEAR_DISTANCE:.1f} m)")
        text = "ROOM: " + ", ".join(lines)
        print(f">>> {text}")
        for w in warnings:
            print(f">>> WARNING {w}. Avoidance will be awkward; move the takeoff point next time.")
        self.log(snap, "HOVER", (0.0, 0.0, height), text + ("; WARNING " + "; ".join(warnings) if warnings else ""))
        return snap

    def kill_motors(self):
        self.cf.commander.send_stop_setpoint()
        self.cf.high_level_commander.stop()
        print(">>> MOTORS CUT.")

    def land(self, reason="flight finished"):
        """Land where the drone is now. Safe to call more than once."""
        if self.landed:
            return
        self.landed = True
        if not self.flying:
            self.cf.supervisor.send_arming_request(False)
            return
        cfg = self.cfg
        # A second Ctrl+C must not interrupt the landing.
        previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            print(f"\n>>> LANDING: {reason}.  (Press k to cut the motors instead.)")
            snap = self.telemetry.snapshot()
            height = snap.get("z") or cfg.FLIGHT_HEIGHT
            duration = max(1.5, height / cfg.LANDING_SPEED)
            # Hand control back from our setpoints to the drone's own high-level commander.
            self.z_target = None
            self.cf.commander.send_notify_setpoint_stop()
            self.cf.high_level_commander.land(0.0, duration)
            end = time.monotonic() + duration + 0.5
            killed = False
            heard_from_drone = False
            last_send = time.monotonic()
            while time.monotonic() < end:
                if self.keys.kill_requested.is_set():
                    self.kill_motors()
                    killed = True
                    break
                snap = self.telemetry.snapshot()
                if snap["age"] > cfg.TELEMETRY_TIMEOUT:
                    # No data: the link may be down. Keep repeating the land command, so it
                    # gets through as soon as the link comes back for a moment.
                    if time.monotonic() - last_send > cfg.LAND_RESEND_PERIOD:
                        self.cf.high_level_commander.land(0.0, duration)
                        last_send = time.monotonic()
                else:
                    heard_from_drone = True
                self.log(snap, "LAND", event=reason if reason else "")
                reason = ""                       # only log the reason once
                time.sleep(0.05)
            self.cf.high_level_commander.stop()
            time.sleep(0.1)
            self.cf.supervisor.send_arming_request(False)
            time.sleep(0.2)                       # let the last packets leave before the link closes
            snap = self.telemetry.snapshot()
            if not heard_from_drone:
                print(">>> NO DATA FROM THE DRONE during the whole landing: the radio link is lost, so")
                print("    the landing could not be checked. The land command was repeated; if it never")
                print("    arrived, the drone's own safety timeout stops the motors and it drops.")
                print("    Check the Crazyradio (USB extension cable, raised, in sight of the drone).")
                self.needs_restart = self.needs_restart or "the radio link was lost; it may have dropped"
            elif supervisor_problem(snap.get("supinfo")):
                self.needs_restart = f"the drone reports it is {supervisor_problem(snap.get('supinfo'))}"
            if not killed and heard_from_drone:
                print(">>> Landed, motors off.")
        finally:
            signal.signal(signal.SIGINT, previous_handler)


# --------------------------------------------------------------------------
# The whole sequence, shared by every flying script
# --------------------------------------------------------------------------

def run_flight(cfg, name, plan_lines, height, fly):
    """Connect, run the pre-flight checks, ask for confirmation, take off,
    call fly(flight), and ALWAYS land afterwards (also on errors and Ctrl+C).
    Afterwards, ask for a one-line flight note.

    fly(flight) holds the script's own logic; it calls flight.tick(...) in a loop.
    """
    logger = None
    scf = connect(cfg)
    try:
        scf.open_link()
    except Exception as e:
        print(f"Connection failed: {e}")
        connection_help()
        return
    try:
        cf = scf.cf
        telemetry = Telemetry(cf, cfg.LOG_PERIOD_MS)
        try:
            print("Pre-flight checks:")
            check_decks(cf)
            configure(cf)
            telemetry.start()
            telemetry.wait_for_data()
            check_battery(telemetry, cfg)
            check_supervisor(cf, telemetry)
            confirm_takeoff(plan_lines)
            reset_estimator(cf, telemetry, cfg)
        except PreflightError as e:
            print(f"\nNOT FLYING: {e}")
            return
        except KeyboardInterrupt:
            print("\nCancelled. The drone did not take off.")
            return

        cf.connection_lost.add_callback(
            lambda uri, message: print(f"\n>>> RADIO LINK LOST ({message}). Landing as soon as possible ..."))
        with FlightLogger(cfg.LOG_DIR, name) as logger, KeyboardStop() as keys:
            flight = Flight(cf, cfg, telemetry, keys, logger)
            reason = "flight finished"
            try:
                flight.takeoff(height)
                fly(flight)
            except AbortFlight as e:
                reason = str(e)
            except KeyboardInterrupt:
                reason = "Ctrl+C pressed"
            except Exception as e:
                reason = f"program error ({e!r})"
                raise                     # the traceback is shown after the landing
            finally:
                flight.land(reason)
                print(f"Flight log saved to {logger.path}")
                if flight.needs_restart:
                    print(restart_message(flight.needs_restart))
        telemetry.stop()
    finally:
        scf.close_link()
    if logger is not None:
        add_flight_note(cfg.NOTES_FILE, logger.path.stem)
