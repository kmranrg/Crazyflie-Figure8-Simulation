"""
avoidance.py - the person-avoidance logic used by 04_figure8_avoid.py.

There is no cflib in this file: it only works with numbers (positions and
ranger distances in metres). That is why the real flight and the --dry-run use
exactly the same code.

The drone is always in one of four states:

    FOLLOW  fly the figure-8.
            -> AVOID when a beam is confirmed closer than AVOID_DISTANCE
               (or closer than EARLY_AVOID_DISTANCE and approaching fast).
    AVOID   the figure-8 is paused and its current point is remembered.
            Move RETREAT_DISTANCE away from the person: to the opposite side if
            that side is free, otherwise sideways, otherwise just hold position.
            If the person is walking towards the drone (reading shrinking faster
            than APPROACH_SPEED, or the same beam fires again right after backing
            away), sideways is tried first: backing away along someone's walking
            line only works if the drone is faster than them.
            -> WAIT when the move is finished.
    WAIT    hold position.
            -> AVOID again if someone comes close again.
            -> RETURN once every beam sees further than CLEAR_DISTANCE for CLEAR_TIME.
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


class RangeFilter:
    """Cleans up the Multi-ranger readings.

    - Readings below RANGE_MIN_VALID are glitches: ignored completely.
    - Readings at or above RANGE_MAX_VALID mean "nothing in range": stored as infinity.
    - A reading is "close" when it is below AVOID_DISTANCE, or below
      EARLY_AVOID_DISTANCE while the object approaches faster than APPROACH_SPEED
      (someone walking at the drone needs an earlier warning).
    - A beam only counts as blocked after AVOID_CONFIRM_COUNT close readings in a
      row, so one bad sample cannot trigger AVOID.
    Call update() once per NEW set of readings (not once per control tick).
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.distance = {b: None for b in cfg.AVOID_BEAMS}    # None = no usable reading yet
        self.close_count = {b: 0 for b in cfg.AVOID_BEAMS}
        self.near_count = {b: 0 for b in cfg.AVOID_BEAMS}     # readings in a row within CLEAR_DISTANCE
        self.history = {b: [] for b in cfg.AVOID_BEAMS}       # recent (time, distance) pairs

    def update(self, readings, t):
        """readings: dict like {"front": 1.23, ...} in metres (None = missing); t: time in s."""
        for beam in self.distance:
            r = readings.get(beam)
            if r is None or r < self.cfg.RANGE_MIN_VALID:
                continue
            if r >= self.cfg.RANGE_MAX_VALID:
                r = math.inf
            self.distance[beam] = r
            history = self.history[beam]
            history.append((t, r))
            while history and t - history[0][0] > 0.5:     # keep the last half second
                history.pop(0)
            # Too close, or still a bit further away but coming at us fast?
            close = r < self.cfg.AVOID_DISTANCE or (r < self.cfg.EARLY_AVOID_DISTANCE and
                                                    self.closing_speed(beam) > self.cfg.APPROACH_SPEED)
            self.close_count[beam] = self.close_count[beam] + 1 if close else 0
            self.near_count[beam] = self.near_count[beam] + 1 if r <= self.cfg.CLEAR_DISTANCE else 0

    def closing_speed(self, beam):
        """How fast the object in this beam is getting closer, in m/s (0 if unknown or moving away)."""
        history = [(t, r) for t, r in self.history[beam] if r != math.inf]
        if len(history) < 3 or history[-1][0] - history[0][0] < 0.2:
            return 0.0
        (t0, r0), (t1, r1) = history[0], history[-1]
        return max(0.0, (r0 - r1) / (t1 - t0))

    def blocked(self):
        """Beams confirmed closer than AVOID_DISTANCE, closest first."""
        beams = [b for b, n in self.close_count.items() if n >= self.cfg.AVOID_CONFIRM_COUNT]
        return sorted(beams, key=lambda b: self.distance[b])

    def all_clear(self):
        """True when no beam sees anything within CLEAR_DISTANCE.

        Like blocked(), a beam only counts as "not clear" after AVOID_CONFIRM_COUNT
        near readings in a row, so a single glitch does not restart the wait.
        """
        return all(self.distance[b] is not None and self.near_count[b] < self.cfg.AVOID_CONFIRM_COUNT
                   for b in self.distance)

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
            elif self.filter.all_clear():
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

    # ------------------------------------------------------------------

    def _start_avoid(self, t, pos, yaw_deg, beam):
        """Choose where to move away from the obstacle seen by `beam`."""
        cfg = self.cfg
        needed = cfg.RETREAT_DISTANCE + cfg.RETREAT_FREE_MARGIN
        yaw = math.radians(yaw_deg)

        def world_direction(b):
            """The beam's direction rotated from the drone's frame into the world frame."""
            bx, by = BEAM_DIRECTIONS[b]
            return bx * math.cos(yaw) - by * math.sin(yaw), bx * math.sin(yaw) + by * math.cos(yaw)

        def side_score(b):
            # More free space first (anything beyond 2 m counts as equally free);
            # on a tie, the side that brings us back towards the takeoff point.
            dx, dy = world_direction(b)
            return min(self.filter.free_space(b), 2.0), -(dx * pos[0] + dy * pos[1])

        # Normally: straight away from the person first, then the better of the two sides.
        # But if the person is walking towards us (closing fast, or the same beam fired
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

        self.move_beam = None
        self.goal = pos                        # default: hold where we are
        action = "both ways blocked, holding position"
        for option in options:
            if self.filter.free_space(option) < needed:
                continue
            dx, dy = world_direction(option)
            gx = pos[0] + cfg.RETREAT_DISTANCE * dx
            gy = pos[1] + cfg.RETREAT_DISTANCE * dy
            if math.hypot(gx, gy) > cfg.GEOFENCE_RADIUS - cfg.GEOFENCE_MARGIN:
                continue                       # would get too close to the geofence
            self.move_beam, self.goal = option, (gx, gy)
            action = f"moving {cfg.RETREAT_DISTANCE:.1f} m towards {option}"
            break

        moving = " (it followed us)" if followed else f" (closing at {closing:.1f} m/s)" if approaching else ""
        self._set_state(t, AVOID, f"{beam} beam sees {self.filter.distance[beam]:.2f} m{moving}, {action}", beam)

    def _set_state(self, t, state, text, beam=""):
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
