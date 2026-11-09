"""
avoidance.py - the person-avoidance logic used by 04_figure8_avoid.py.

There is no cflib in this file: it only works with numbers (positions and
ranger distances in metres). That is why the real flight, the --dry-run,
replay.py and tests.py all use exactly the same code.

The drone is always in one of four states:

    FOLLOW  fly the figure-8.
            -> AVOID when a beam is confirmed closer than AVOID_DISTANCE
               (or closer than EARLY_AVOID_DISTANCE while the object itself moves
               towards the drone faster than APPROACH_SPEED).
    AVOID   the figure-8 is paused and its current point is remembered.
            Move away from the person: to the opposite side if that side is free
            (far enough that the person would be beyond CLEAR_DISTANCE, at most
            MAX_RETREAT_DISTANCE), otherwise RETREAT_DISTANCE sideways, otherwise
            just hold position.
            If the person is walking towards the drone (approaching, or the same
            beam fires again right after moving away), sideways is tried first:
            backing away along someone's walking line only works if the drone is
            faster than them.
            -> WAIT when the move is finished.
    WAIT    hold position.
            -> AVOID again if someone comes close again.
            -> RETURN once, for CLEAR_TIME, the beams that saw the person AND the
               beam facing the way back to the path see further than CLEAR_DISTANCE.
               (Walls on the other sides do not matter, as long as nothing is
               closer than AVOID_DISTANCE.)
    RETURN  fly slowly back to the remembered figure-8 point.
            -> AVOID if someone comes close.
            -> FOLLOW when back on the path (the figure-8 continues where it left off).

If the figure-8 stays paused longer than MAX_PAUSE_TIME (someone keeps
standing in the way), the logic asks the drone to land.

Hysteresis: it takes < 0.6 m to start avoiding but > 1.0 m to count as clear, so
a person standing at about 0.6 m cannot make the drone flip back and forth.
"""

import math

FOLLOW, AVOID, WAIT, RETURN = "FOLLOW", "AVOID", "WAIT", "RETURN"

# Direction each horizontal beam points, in the drone's own frame (x forward, y left).
BEAM_DIRECTIONS = {"front": (1.0, 0.0), "back": (-1.0, 0.0), "left": (0.0, 1.0), "right": (0.0, -1.0)}
OPPOSITE = {"front": "back", "back": "front", "left": "right", "right": "left"}
SIDEWAYS = {"front": ("left", "right"), "back": ("left", "right"),
            "left": ("front", "back"), "right": ("front", "back")}


def beam_direction(beam, yaw_deg):
    """The beam's direction rotated from the drone's frame into the world frame."""
    bx, by = BEAM_DIRECTIONS[beam]
    yaw = math.radians(yaw_deg)
    return bx * math.cos(yaw) - by * math.sin(yaw), bx * math.sin(yaw) + by * math.cos(yaw)


class RangeFilter:
    """Cleans up the Multi-ranger readings.

    - Readings below RANGE_MIN_VALID are glitches: ignored completely.
    - Readings at or above RANGE_MAX_VALID mean "nothing in range": stored as
      infinity, which counts as clear. But the sensor also reports that value for
      a reading or two in the middle of a real object (a dropout). So within
      DROPOUT_HOLD_TIME of a real reading, a beam that was "near" stays near for
      the return-to-path decision (is_clear). Everything else treats the reading
      as "nothing there": it ends a run of "too close" readings and frees that
      direction for dodging (an old glitch must not block an escape route).
    - A reading is "close" when it is below AVOID_DISTANCE, or below
      EARLY_AVOID_DISTANCE while the object approaches faster than APPROACH_SPEED.
      The approach speed is the object's own speed: the drone's own movement
      along the beam is taken out (flying towards a wall is not "approaching").
    - A beam only counts as blocked after AVOID_CONFIRM_COUNT close readings in a
      row, so one bad sample cannot trigger AVOID. (Each sensor measurement
      arrives in two packets, so 3 readings = 2 measurements, about 0.15 s.)
    Call update() once per NEW set of readings (not once per control tick).
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.distance = {b: None for b in cfg.AVOID_BEAMS}    # None = no usable reading yet
        self.close_count = {b: 0 for b in cfg.AVOID_BEAMS}
        self.near_count = {b: 0 for b in cfg.AVOID_BEAMS}     # readings in a row within CLEAR_DISTANCE
        self.history = {b: [] for b in cfg.AVOID_BEAMS}       # recent (time, distance, object position)
        self.last_valid_time = {b: None for b in cfg.AVOID_BEAMS}
        self._pose = (None, None, None)

    def update(self, readings, t):
        """readings: dict like {"front": 1.23, ...} in metres (None = missing); t: time in s.

        If readings also has the drone's "x", "y" and "yaw" (the flight telemetry
        does), the approach speed is measured relative to the room.
        """
        cfg = self.cfg
        self._pose = (readings.get("x"), readings.get("y"), readings.get("yaw"))
        for beam in self.distance:
            r = readings.get(beam)
            if r is None or r < cfg.RANGE_MIN_VALID:
                continue
            if r >= cfg.RANGE_MAX_VALID:
                last = self.last_valid_time[beam]
                if last is not None and t - last < cfg.DROPOUT_HOLD_TIME:
                    # maybe a dropout: keep near_count (not "clear" yet), the rest as "nothing there"
                    self.close_count[beam] = 0
                    self.distance[beam] = math.inf
                    continue
                r = math.inf
            else:
                self.last_valid_time[beam] = t
            self.distance[beam] = r
            history = self.history[beam]
            history.append((t, r, r + self._drone_along(beam)))
            while history and t - history[0][0] > 0.5:     # keep the last half second
                history.pop(0)
            # Too close, or still a bit further away but coming at us fast?
            close = r < cfg.AVOID_DISTANCE or (r < cfg.EARLY_AVOID_DISTANCE and
                                               self.closing_speed(beam) > cfg.APPROACH_SPEED)
            self.close_count[beam] = self.close_count[beam] + 1 if close else 0
            self.near_count[beam] = self.near_count[beam] + 1 if r <= cfg.CLEAR_DISTANCE else 0

    def _drone_along(self, beam):
        """How far the drone is along this beam's direction in the room (0 if unknown)."""
        x, y, yaw = self._pose
        if x is None or y is None or math.isnan(x) or math.isnan(y):
            return 0.0
        dx, dy = beam_direction(beam, yaw or 0.0)
        return x * dx + y * dy

    def closing_speed(self, beam):
        """How fast the object in this beam moves towards the drone, in m/s (0 if unknown or moving away)."""
        history = [(t, s) for t, r, s in self.history[beam] if r != math.inf]
        if len(history) < 3 or history[-1][0] - history[0][0] < 0.2:
            return 0.0
        (t0, s0), (t1, s1) = history[0], history[-1]
        return max(0.0, (s0 - s1) / (t1 - t0))

    def blocked(self):
        """Beams confirmed closer than AVOID_DISTANCE, closest first."""
        beams = [b for b, n in self.close_count.items() if n >= self.cfg.AVOID_CONFIRM_COUNT]
        return sorted(beams, key=lambda b: self.distance[b])

    def is_clear(self, beam):
        """True when this beam does not see anything within CLEAR_DISTANCE.

        Like blocked(), a beam only counts as "not clear" after AVOID_CONFIRM_COUNT
        near readings in a row, so a single glitch does not restart the wait.
        A beam that never gave a usable reading counts as not clear (safe side).
        """
        return self.distance[beam] is not None and self.near_count[beam] < self.cfg.AVOID_CONFIRM_COUNT

    def free_space(self, beam):
        """How far a beam can see (0 if we have no reading yet: unknown is not free)."""
        d = self.distance.get(beam)
        return 0.0 if d is None else d


class AvoidanceStateMachine:
    """Decides where the drone should be, one control tick at a time.

    on_event(text, beam) is called on every state change so the caller can print
    and log it.
    """

    def __init__(self, cfg, figure8, on_event):
        self.cfg = cfg
        self.fig8 = figure8
        self.on_event = on_event
        self.filter = RangeFilter(cfg)
        self.state = FOLLOW
        self.setpoint = figure8.position()    # (x, y) we are currently commanding
        self.goal = self.setpoint             # where the setpoint is heading in AVOID/RETURN
        self.rejoin = None                    # figure-8 point to come back to
        self.move_beam = None                 # the beam pointing where we are moving in AVOID
        self.trigger_beam = None              # the beam that started the current AVOID
        self.pause_beams = set()              # every beam that started an AVOID during this pause
        self.state_start = 0.0
        self.settle_start = None
        self.clear_since = None
        self.paused_since = 0.0               # when the figure-8 was paused
        self.land_reason = None               # set when the logic wants the drone to land

    def step(self, t, dt, pos, yaw_deg):
        """Advance by one tick. pos = estimated (x, y). Returns the (x, y) setpoint."""
        cfg = self.cfg
        blocked = self.filter.blocked()

        if self.state != FOLLOW and t - self.paused_since > cfg.MAX_PAUSE_TIME:
            self.land_reason = f"could not get back to the figure-8 within {cfg.MAX_PAUSE_TIME:.0f} s"

        if self.state == FOLLOW:
            if blocked:
                self.rejoin = self.fig8.position()   # the figure-8 clock stops here
                self.paused_since = t
                self._start_avoid(t, pos, yaw_deg, blocked[0])
            else:
                self.fig8.advance(dt)
                self.setpoint = self.fig8.position()

        elif self.state == AVOID:
            if self.move_beam in blocked:
                # Something is now in the way where we are going (or we dodged towards
                # the person): plan again from that beam, which also checks its opposite side.
                self._start_avoid(t, pos, yaw_deg, self.move_beam)
            self._move_towards(cfg.AVOID_SPEED * dt)
            if self._arrived(t, pos):
                self._set_state(t, WAIT, f"waiting for {cfg.CLEAR_TIME:.0f} s of clear readings")

        elif self.state == WAIT:
            if blocked:
                self._start_avoid(t, pos, yaw_deg, blocked[0])
            elif not self.return_blockers(pos, yaw_deg):
                if self.clear_since is None:
                    self.clear_since = t
                if t - self.clear_since >= cfg.CLEAR_TIME:
                    self.goal = self.rejoin
                    self._set_state(t, RETURN, "all clear, flying back to the figure-8")
            else:
                self.clear_since = None

        elif self.state == RETURN:
            if blocked:
                self._start_avoid(t, pos, yaw_deg, blocked[0])
            else:
                self._move_towards(cfg.RETURN_SPEED * dt)
                if self._arrived(t, pos):
                    self.fig8.restart_ramp()
                    self._set_state(t, FOLLOW, "back on the path, continuing the figure-8")

        return self.setpoint

    def return_blockers(self, pos, yaw_deg):
        """Beams that must see further than CLEAR_DISTANCE before returning, but don't.

        Those are the beams that saw the person during this pause, and the beam
        that faces the way back to the figure-8.
        """
        needed = set(self.pause_beams)
        way_back = self._beam_towards(self.rejoin, pos, yaw_deg)
        if way_back:
            needed.add(way_back)
        return sorted(b for b in needed if not self.filter.is_clear(b))

    # ------------------------------------------------------------------

    def _beam_towards(self, target, pos, yaw_deg):
        """The beam that points most directly at target (None if we are already there)."""
        if target is None or math.dist(target, pos) < 2 * self.cfg.POSITION_TOLERANCE:
            return None
        dx, dy = target[0] - pos[0], target[1] - pos[1]
        return max(BEAM_DIRECTIONS, key=lambda b: sum(a * c for a, c in zip(beam_direction(b, yaw_deg), (dx, dy))))

    def _start_avoid(self, t, pos, yaw_deg, beam):
        """Choose where to move away from the obstacle seen by `beam`."""
        cfg = self.cfg
        distance = self.filter.distance[beam]
        self.pause_beams.add(beam)

        def side_score(b):
            # More free space first (anything beyond 2 m counts as equally free);
            # on a tie, the side that brings us back towards the takeoff point.
            dx, dy = beam_direction(b, yaw_deg)
            return min(self.filter.free_space(b), 2.0), -(dx * pos[0] + dy * pos[1])

        # Normally: straight away from the person first, then the better of the two sides.
        # But if the person is walking towards us (approaching, or the same beam fired
        # again right after we moved away), backing away along their walking line
        # cannot work, so step sideways first.
        sides = sorted(SIDEWAYS[beam], key=side_score, reverse=True)
        closing = self.filter.closing_speed(beam)
        followed = self.state in (AVOID, WAIT) and beam == self.trigger_beam
        if followed and self.move_beam == sides[1]:
            sides.reverse()                    # keep stepping the same way until we are out of the beam
        approaching = closing > cfg.APPROACH_SPEED or followed
        options = sides + [OPPOSITE[beam]] if approaching else [OPPOSITE[beam]] + sides
        self.trigger_beam = beam

        # Backing away: far enough that the person would be beyond CLEAR_DISTANCE
        # (so we do not end up waiting next to them), within limits.
        retreat = cfg.RETREAT_DISTANCE
        if distance != math.inf:
            retreat = max(retreat, min(cfg.MAX_RETREAT_DISTANCE, cfg.CLEAR_DISTANCE + cfg.RETREAT_MARGIN - distance))

        self.move_beam = None
        self.goal = pos                        # default: hold where we are
        action = "both ways blocked, holding position"
        for option in options:
            step = retreat if option == OPPOSITE[beam] else cfg.RETREAT_DISTANCE
            if self.filter.free_space(option) < step + cfg.RETREAT_FREE_MARGIN:
                continue
            dx, dy = beam_direction(option, yaw_deg)
            gx, gy = pos[0] + step * dx, pos[1] + step * dy
            if math.hypot(gx, gy) > cfg.GEOFENCE_RADIUS - cfg.GEOFENCE_MARGIN:
                continue                       # would get too close to the geofence
            self.move_beam, self.goal = option, (gx, gy)
            action = f"moving {step:.2f} m towards {option}"
            break

        moving = " (it followed us)" if followed else f" (closing at {closing:.1f} m/s)" if approaching else ""
        self._set_state(t, AVOID, f"{beam} beam sees {distance:.2f} m{moving}, {action}", beam)

    def _set_state(self, t, state, text, beam=""):
        if state == FOLLOW:
            self.pause_beams.clear()
        self.state = state
        self.state_start = t
        self.settle_start = None
        self.clear_since = None
        self.on_event(f"{state}: {text}", beam)

    def _move_towards(self, max_step):
        """Slide the setpoint towards self.goal by at most max_step metres."""
        dx = self.goal[0] - self.setpoint[0]
        dy = self.goal[1] - self.setpoint[1]
        d = math.hypot(dx, dy)
        if d <= max_step:
            self.setpoint = self.goal
        else:
            self.setpoint = (self.setpoint[0] + dx / d * max_step, self.setpoint[1] + dy / d * max_step)

    def _arrived(self, t, pos):
        """True once the setpoint reached the goal and the drone is there (or had time to settle)."""
        if self.setpoint != self.goal:
            return False
        if self.settle_start is None:
            self.settle_start = t
        close = math.dist(pos, self.goal) < self.cfg.POSITION_TOLERANCE
        return close or t - self.settle_start > self.cfg.SETTLE_TIME
