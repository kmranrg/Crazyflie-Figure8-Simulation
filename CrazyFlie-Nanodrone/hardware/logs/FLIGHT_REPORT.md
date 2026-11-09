# Flight report: 8 November 2026

Covers all 14 logs in this folder: 2 hover flights, 3 figure-8 flights, 7 runs of the figure-8 with
avoidance, one ranger-monitor session and one dry run.

The plots are in [plots/](plots/). To make them again, or for future flights:
`python analyze_logs.py` (one PNG per log, plus [figure8_summary.png](plots/figure8_summary.png) and
[summary.md](plots/summary.md)) and `python replay.py` (the replay plots).

> **Update after Phase 2:** the approved changes are now in the flight code. See
> [What changed in Phase 2](#what-changed-in-phase-2) at the end. The sections in
> between describe the analysis as it was done before the changes.

## The short version

1. **Two flights never left the floor, and the script didn't notice** (21-53-30, 21-54-02). The height
   stayed at 0.00 m and the battery never sagged, yet the script printed "In the air" and ran
   the avoidance logic on the floor. This is the most important bug.
2. **21-57-23 sank to 0.17 m, then climbed to 1.62 m.** The climb was real: the up beam and the height
   always add up to the 2.4 m ceiling. The height limit triggered landing at 1.23 m, but the drone kept
   climbing for another 1.8 s. The battery was at 3.46 V under load.
3. **The two "stuck in WAIT" flights have the same cause** (20-16-42, 21-54-45). After the dodge, a
   **wall** was within 1.0 m of the drone (left at 0.74–0.90 m, back at 0.80–0.92 m). To return, *all four*
   beams had to see further than 1.0 m, walls included, so the drone waited until the 25 s limit.
   The box (20-16-42) was **not** what held it.
4. **21-52-18 lost the radio link.** Data stopped arriving at 17.8 s. The script waited 0.5 s, then sent
   the land command once into a dead link. The next two flights couldn't take off.
5. **Path following is excellent**: on average 1–2 cm off the figure-8 shape, 10 cm at most. The hover
   held position to 1.7 cm on average, with 95% of the time within 2.9 cm, which confirms your "within
   ~3 cm".

## Questions only you can answer

The logs can't show these, and your notes for the other flights and the room were still the template
placeholders:

- **21-52-18:** after the link was lost at 0.5 m, did the drone land gently, drop, or tumble? Did you
  restart it before 21-53-30, or only before 21-54-45?
- **21-53-30 / 21-54-02:** did the propellers spin at all? What was 0.35 m to the right of the drone?
- **21-57-23:** what were you doing at 45–57 s? The right beam saw something at 0.29 m and the front at
  0.38 m. Did the drone hit anything, and are all four propellers undamaged?
- **For every flight:** where did you stand, and what did you use (box, cardboard, yourself walking)?
  Per flight I can only see what the beams saw (below).

---

## Flight by flight

Notes on the numbers:

- **Off path** is the distance from the planned figure-8 curve.
- **Behind setpoint** is how far the drone trails the moving target point (normal lag at this speed).
- **Height** figures are measured from 1 s after takeoff.
- **Battery** shows the voltage at rest before takeoff → the lowest under load.

### 20-00-56: 02 ranger monitor (cluttered desk)
![](plots/2026-11-08_20-00-56_02_ranger.png)

- **Duration:** 7.8 s. The log stops at 7.8 s because the link dropped.
- **Readings:** all four beams read 0.07–0.42 m (the desk clutter), so all four showed BLOCKED. This is
  correct.
- **No invalid readings.**
- **Problem:** the monitor has no "no data" check. When the link dropped, the table simply froze
  (problem 6 below).

### 20-03-30: 01 hover → ended with the land key at 11.9 s
[plot](plots/2026-11-08_20-03-30_01_hover.png)

- **Duration:** 14.7 s.
- **Position:** 2.2 cm from target on average, 95% within 5.2 cm, worst 6.2 cm.
- **Height:** 0.56 m average (std 2.8 cm). It overshoots to about 0.59 m after takeoff (see tuning T3).
- **Battery:** 4.08 → 3.67 V.

### 20-04-12: 01 hover → finished normally
![](plots/2026-11-08_20-04-12_01_hover.png)

- **Duration:** 15.6 s.
- **Position:** 1.7 cm from target on average, 95% within 2.9 cm, worst 3.5 cm.
- **Height:** 0.55 m average (std 2.1 cm).
- **Landing:** the drone moved 2 cm while descending. The 34 cm "jump" at the very end is the position
  estimate after touchdown: the Flow deck can't measure that close to the floor. The drone didn't move.
- **Battery:** 4.06 → 3.68 V.

### 20-07-40: 03 figure-8 → land key (Space) during lap 2
[plot](plots/2026-11-08_20-07-40_03_figure8.png)

- **Duration:** 34.3 s, 26.8 s of it following the figure-8.
- **Off path:** 1.2 cm average, 4.4 cm worst. Behind setpoint: 15 cm average.
- **Height:** 0.52 m (std 2.7 cm).
- **Landing:** started where the drone was and drifted 2.5 cm on the way down. The land key works.
- **Battery:** 4.03 → 3.52 V.

### 20-10-56: 03 figure-8 → finished (2 laps)
[plot](plots/2026-11-08_20-10-56_03_figure8.png)

- **Duration:** 37.2 s (FOLLOW 28.7 s).
- **Off path:** 1.5 cm average, 10.3 cm worst (front-right lobe).
- **Height:** 0.52 m (std 3.2 cm).
- **Battery:** 3.92 → 3.51 V.

### 20-12-44: 03 figure-8 → finished (2 laps)
[plot](plots/2026-11-08_20-12-44_03_figure8.png)

- **Duration:** 37.3 s.
- **Off path:** 1.1 cm average, 3.6 cm worst.
- **Height:** 0.52 m (std 2.7 cm).
- **Battery:** 3.87 → 3.49 V.

![](plots/figure8_summary.png)

### 20-13-49: 04 dry run
[plot](plots/2026-11-08_20-13-49_04_dry_run.png)

- **Result:** 2 AVOIDs and 1 rejoin; finished normally.
- **Replay:** reproduces all 6 decisions exactly.

### 20-16-42: 04 avoid (box) → landed after the 25 s pause limit
![](plots/2026-11-08_20-16-42_04_figure8_avoid.png)

- **Duration:** 46.2 s. Time per state: FOLLOW 13.6 s, AVOID 1.7 s, **WAIT 23.3 s**.
- **Avoidance:** 1 AVOID (right beam, 0.58 m, at 18.6 s), then moved 0.3 m left, as you saw. No rejoin.
- **Off path (before the AVOID):** 1.1 cm average.
- **Height:** 0.51 m (std 2.7 cm).
- **Battery:** 3.83 → 3.38 V (that lowest value is a sag during landing; 3.45 V in flight).
- **Why WAIT never ended:** see the diagnosis below.

### 21-52-18: 04 avoid → radio link lost, landing commanded blind
[plot](plots/2026-11-08_21-52-18_04_figure8_avoid.png)

- **Duration:** 20.8 s.
- **Avoidance:** one early AVOID at 16.2 s. The front beam saw something approaching at 1.2 m/s
  (probably a person walking in), and the drone moved 0.3 m right.
- **Link loss:** at **17.8 s** every value froze (shaded "no data from drone" in the plot). At 18.3 s
  the 0.5 s timeout started the landing, and all the later rows are the same frozen values.
- **Unknown:** whether the drone received the land command at all.
- **Battery:** 4.10 → 3.68 V.

### 21-53-30 and 21-54-02: 04 avoid → **never took off**, stopped with Ctrl+C
[plot 21-53-30](plots/2026-11-08_21-53-30_04_figure8_avoid.png) ·
[plot 21-54-02](plots/2026-11-08_21-54-02_04_figure8_avoid.png)

- **The drone stayed on the floor:** z = 0.00 m and zrange = 0.00 m throughout, the position never
  changed, and the battery stayed at 4.02–4.04 V (it always sags to about 3.75 V when the motors run).
- **What the script did anyway:** the takeoff, the figure-8 and 5 + 1 "avoidances" (right beam
  0.34–0.35 m) all ran with the drone on the floor. "It followed us" fired four times because the
  drone never moved, so the object stayed at 0.35 m.
- **Likely cause:** the drone's supervisor refused to arm. It locks the drone after a crash or tumble,
  which fits the link loss just before. The fix is in problem 1.

### 21-54-45: 04 avoid (person) → landed after the 25 s pause limit
[plot](plots/2026-11-08_21-54-45_04_figure8_avoid.png)

- **Duration:** 55.6 s: FOLLOW 23.1 s, AVOID 5.9 s, **WAIT 19.1 s**.
- **Avoidance:** 6 AVOIDs, 0 rejoins.
  - 28.1 s: something approached from the right at 1.3 m/s. The drone stepped back, but the person
    stayed in the right beam.
  - Two "it followed us" dodges moved it further back, until the back beam saw a wall at 0.60 m.
  - It moved forward and then waited 11.2 s: the wall behind read 0.80–0.92 m, so it never counted as
    clear.
- **Off path:** 1.3 cm average. **Height:** 0.51 m (std 3.3 cm).
- **Battery:** 4.05 → 3.56 V.

### 21-56-08: 04 avoid → **finished, 3 rejoins**
[plot](plots/2026-11-08_21-56-08_04_figure8_avoid.png)

- **Duration:** 63.1 s: FOLLOW 32.1 s, AVOID 9.2 s, WAIT 8.0 s, RETURN 5.3 s.
- **Avoidance:** 7 AVOIDs. Three of them were misfires:
  - two false "it followed us" (still inside 0.6 m after backing away only 0.3 m);
  - one early dodge triggered by the drone's own movement (front beam, 1.14 m, at 29.75 s).
- **Off path:** 1.6 cm average. **Height:** 0.51 m (std 2.9 cm).
- **Battery:** 3.92 → 3.47 V.

### 21-57-23: 04 avoid → **height limit (1.23 m)**, then climbed to 1.62 m while landing
![](plots/2026-11-08_21-57-23_04_figure8_avoid.png)

- **Duration:** 62.6 s: FOLLOW 18.3 s, AVOID 13.5 s, WAIT 13.2 s, RETURN 7.3 s.
- **Avoidance:** 11 AVOIDs, 2 rejoins. Objects appeared suddenly at 0.13–0.35 m four times.
- **Height:** normal until 48 s, then a growing oscillation: 0.25 → 0.70 → 0.30 → 1.03 → 0.17 →
  1.23 m (limit) → 1.62 m. Std 10.2 cm overall; worst error 73 cm.
- **Battery:** 3.83 V at start; 3.46–3.47 V under load during the oscillation. The voltage spikes in the
  battery panel match the moments of low thrust.

---

## Diagnosis: why 20-16-42 never left WAIT

![](plots/2026-11-08_20-16-42_04_figure8_avoid_replay_B1_B2_only.png)

The bars under each beam show which beam kept the logic waiting. Light grey is the current logic; dark
is the proposed logic.

| Beam | During WAIT (20.3–43.6 s) | Kept the current logic in WAIT |
|---|---|---|
| **left** | **0.74–0.90 m, every reading valid, no gaps**: a wall about 1.3 m left of the takeoff point (see the room map in the bird's-eye view) | **100% of the time** |
| right (the box) | 87% "out of range"; the rest 0.88–1.05 m (the box, seen only intermittently), until about 30 s | 6% |
| front | 2.4 m (the wall in front) | no |
| back | out of range | no |

- **What happened:** the dodge moved the drone 0.3 m left, from y = 0.19 to y = 0.49 m. That brought
  it **closer to the left wall**: the left beam went from 1.09 m (clear) to 0.78 m (not clear). After that,
  "all four beams > 1.0 m" could never be true while the drone stayed put.
- **Which beam:** the left wall alone held it; the box played almost no part.
- **Invalid readings:** none. No reading in any flight was below 2 cm.

### How "nothing in range" is handled

- **The rule today:** a beam that sees nothing reports 32.766 m. `RangeFilter` turns any reading
  ≥ 4.0 m into "infinitely far" and resets that beam's counters.
- **So yes, "nothing in range" counts as clear**, and that part works.
- **The opposite problem:** that value doesn't always mean "nothing there". The sensor also drops out
  for 1–3 readings in the middle of a real object:
  - with something sitting 0.34 m away, the right beam read `0.34 0.34 -- -- -- -- 0.34`;
  - between two similar close readings, I found 60 one-reading dropouts and 32 two-reading dropouts.

  The filter takes each dropout as "clear", which restarts the count.
- **In 20-16-42** that is why the box at about 0.9 m hardly counted, even though it was well inside 1.0 m.
- **One corner case:** a beam that has *never* given a usable reading (all below 2 cm, e.g. a covered
  sensor) counts as *not* clear. That's the safe choice, and it never happened in these logs.

### The other 04 flights

| Flight | Long WAITs | What held it |
|---|---|---|
| 21-54-45 | 31.2–36.5 s, 40.3–51.5 s | **the back beam: a wall at 0.80–1.11 m**, valid readings, no gaps |
| 21-57-23 | 42.0–45.9 s | the front beam: a wall at 0.97–1.10 m, 29% of the time; it ended with a new AVOID |
| 21-56-08, 21-57-23 | every other WAIT | nothing; each ended with RETURN after exactly 2 s, or with a new AVOID |
| 21-52-18 | 17.5–18.3 s | nothing (the link was lost) |
| 21-53-30 | short | the drone was on the floor |

In every 04 flight, no invalid reading kept the drone waiting, and every "out of range" reading counted
as clear.

---

## The replay tool, and how much to trust it

`replay.py` feeds each recorded tick (ranger readings, position, yaw, time) into the same
`AvoidanceStateMachine` the flight uses. It feeds the filter only when the data actually changed,
like the flight code does.

With the settings used in flight it reproduces **all 77 of the 77 decisions** in the 8 logs, with the
same state in 97.9–100% of the ticks:

| Log | 20-13-49 dry | 20-16-42 | 21-52-18 | 21-53-30 | 21-54-02 | 21-54-45 | 21-56-08 | 21-57-23 |
|---|---|---|---|---|---|---|---|---|
| Decisions reproduced | 6/6 | 2/2 | 2/2 | 9/9 | 1/1 | 11/11 | 20/20 | 26/26 |

**Limit:** the log only knows where the *real* drone went. When a fix decides something different, the
readings after that point belong to a drone that's somewhere else. So for each fix I report the
**first** decision where it differs from the flight: up to that moment the readings are exactly what
the drone saw.

To cover what happens next, I also ran **closed-loop dry runs**: the simulated drone and sensors in rooms
rebuilt from these logs. They used a temporary script that isn't in the repo yet; in Phase 2 it would
become part of `04 --dry-run`.

---

## Problems and proposed improvements, ranked

During Phase 1 every proposed logic change was in a separate `proposals.py`, with a switch for each.
After approval they were merged into `avoidance.py`, `drone.py` and `config.py`, and that file was
removed.

### Real bugs

**1. Takeoff is never checked (safety).**
- **Evidence:** 21-53-30 and 21-54-02 ran a whole "flight" with the drone on the floor.
- **Proposal S1:**
  - **Before takeoff,** read `cf.supervisor`. I confirmed in your installed cflib 0.1.34 that it has
    `is_locked`, `is_crashed`, `is_tumbled` and `can_be_armed`. Refuse to fly with "restart the
    drone" if it is locked, crashed or tumbled.
  - **After takeoff,** check that z ≥ 50% of the target height (0.25 m). If not, disarm and stop:
    "did not take off".
- **Tested on the logs:** it would have stopped both flights at 3.0 s (z = 0.00). Every other flight was
  at 0.34–0.44 m at that moment, so no false alarm.

**2. Nothing watches the height (safety).**
- **Evidence:** in 21-57-23 the height was 0.5 m off for several seconds before the 1.2 m limit
  triggered.
- **Proposal S2:** land if the height is more than **0.20 m** off target for **0.5 s**.
- **Tested on the logs:** it triggers in 21-57-23 at 52.7 s (z ≈ 0.9 m), 4.5 s before the height
  limit did. In the other 9 flights the worst error was 8–12 cm, so no false alarm.
- **Limit:** once the controller has "wound up", even a land command overshoots. So the real fix is
  also the battery margin (T2) and checking the propellers.

**3. WAIT can never end with a wall within 1.0 m.**
- **Evidence:** 20-16-42 and 21-54-45 (see the diagnosis).
- **Proposal B1:** leave WAIT when:
  - the beams that saw the person,
  - **and** the beam facing the way back to the path,

  all see further than 1.0 m for 2 s, **and** nothing is closer than 0.6 m.

  The 0.6/1.0 m hysteresis stays on the person's beam and on the way back. Walls on other sides no
  longer block.
- **Replay, B1 alone:**
  - 20-16-42: RETURN at **26.9 s** (it really waited until the 43.6 s landing);
  - 21-54-45: RETURN at **33.4 s**, where the real flight made a false "followed" dodge.

  In both cases the real drone was holding still in WAIT, so this is exactly what B1 would have decided.
- **Closed loop:** a person standing 0.8 m beside the path lands after 25 s today; with B1 the flight
  finishes.

**4. Sensor dropouts count as "clear" (needs your OK: it changes a rule you set).**
- **Evidence:** in 20-16-42, 87% of the box's readings were "out of range", so the box at about 0.9 m
  barely counted.
- **Proposal B2:** an out-of-range reading **within 0.5 s of a real one** doesn't count as clear yet.
  It does still end a run of "too close" readings, so it can't cause an AVOID.
  - "Nothing in range" still counts as clear, never as blocked; just 0.5 s later.
- **Replay, B1 + B2 on 20-16-42:** RETURN at **32.1 s**, 2 s after the box's last reading. That is the
  behaviour you asked for: wait until the box is gone.
- **What I got wrong first:** my first version also held the "too close" run. In the crossing-walker dry
  run it then dodged *into* the walker (0.22 m instead of 0.41 m). The current version keeps 0.39 m.

**5. Backing away 0.3 m isn't enough when the person is already close.**
- **Evidence:** "it followed us" fired 9 times in the flights that left the floor, mostly when the drone
  was simply still inside 0.6 m after backing away 0.3 m:
  - 21-56-08 at 16.95 s: the reading was *increasing* (0.24 → 0.49 m);
  - 21-57-23 at 11.5, 12.6 and 18.0 s (0.28–0.29 m);
  - 21-54-45 at 30.15 s (0.60 m).

  Each one sent the drone sideways again, and in 21-54-45 straight into the wall behind.
- **Proposal B5:** back away far enough that the person would read beyond 1.0 m (+0.1 m), at most
  0.6 m. The usual free-space and geofence checks still apply.
  - Example: from 0.29 m it moves 0.6 m, so the reading becomes 0.89 m, outside 0.6 m.
  - It also means a wall that triggered AVOID ends up beyond 1.0 m, so it can't cause problem 3 again.
- **Closed loop:** same clearances in every scenario (table below).

**6. Radio link loss: the land command is sent only once.**
- **Evidence:** 21-52-18. The 02 monitor froze without any message.
- **Proposal S3:**
  - **When data stops,** keep sending the land command (4 times a second until the landing time is
    up), print what to check, and log the link quality (`cf.link_statistics`) and `supervisor.info`.
  - **02:** show "NO DATA for X s: link lost?".
- **Can't be tested on the logs.** This is only extra, so nothing gets weaker.

### Tuning

**T1. Closing speed should be the person's speed, not the drone's (B4').**
- **Evidence:** in FOLLOW the drone itself moves at up to 0.37 m/s, and `APPROACH_SPEED` (0.4 m/s) sat
  just above that. Flying towards a wall triggered early dodges: 21-56-08 at 29.75 s (front, 1.14 m,
  "closing at 0.5 m/s") and probably 21-57-23 at 40.45 and 55.95 s.
- **Proposal:** add the drone's own movement along the beam (the telemetry already has x, y, yaw), and
  lower `APPROACH_SPEED` to **0.25 m/s**.
- **Replay, B4' alone:**
  - it removes the 21-56-08 dodge;
  - it keeps the real approach in 21-52-18 (now measured as 1.2 m/s);
  - it changes nothing else up to those points;
  - it doesn't remove the two 21-57-23 front events: the object's own speed there was above 0.25 m/s.
- **Why 0.25 and not 0.4:** with 0.4, a person walking at 0.3 m/s wouldn't count as approaching, and the
  drone backed away along their line. I saw this in the closed-loop head-on run.

**T2. Start every 04 session with more battery (`MIN_TAKEOFF_VOLTAGE` 3.8 → 3.9 V).**
- **Evidence:** the only height instability came in the flight that started at 3.83 V, after 48 s.
- **This is weak evidence:** 20-16-42 also started at 3.83 V and flew fine for 43 s. I recommend it as
  margin, not as a proven fix.
- **Affected flights:** 20-12-44, 20-16-42 and 21-57-23 would have been refused.

**T3. Longer hover before the figure-8 (2 → 4 s).**
- **Evidence:** in every flight the height overshoots to 0.58–0.61 m after takeoff and takes about 5 s
  to settle, so the figure-8 starts about 8 cm high.
- **Small effect.** I'd use the extra hover for the room check (E1).

**T4 (your choice). Count each ranger measurement once.**
- **What happens now:** the sensor updates about 10 times a second, but each value arrives twice (the log
  runs at 20 Hz). So "3 readings in a row" is really **2 measurements (about 0.15 s)**.
- **Proposal B3:** count each measurement once. It matches your rule literally, but reacts about
  0.1 s later.
- **Evidence:** 10 two-measurement dips below 0.6 m in 8,324 measurements; these could trigger an AVOID
  today.
- **My suggestion:** keep today's timing and correct the README wording. You decide.

### Room and setup (no code)

**E1. Keep about 1 m between the path and anything static.**
- **Measured from the logs at flight height:**

  | Session | Left | Right | Front | Behind |
  |---|---|---|---|---|
  | 20:xx | **1.30–1.39 m** | 1.9–2.0 m | 2.3–2.5 m | mostly nothing in range |
  | 21:5x | 2.3–2.7 m | 1.6–2.9 m | **1.3–1.8 m** | **1.4–1.9 m** |

- **The figure-8 reaches** ±0.5 m left/right and ±0.25 m front/back. So:
  - **in the 20:xx session** the left wall was only 0.8–0.9 m from the path. That caused 20-16-42.
  - **in the 21:5x session** the front wall was about 1.0 m from the path, which triggered early dodges.
- **Rule of thumb:** at flight height, at least **1.5 m free to the left and right** of the takeoff
  point and **1.25 m in front and behind**.
- **Proposal S4:** during the hover, print the four distances and warn when something is closer.
- **Not a ground check:** on the floor every beam reads 0.1–0.3 m. That is the floor itself: the beam
  cone reaches it about 0.17 m out.

**E2. Move whatever was 0.35 m to the right of the takeoff point** in 21-53-30 / 21-54-02.

**E3. Radio:**
- Put the Crazyradio on a USB extension cable, raised and in line of sight, not behind the laptop.
- Stay within a few metres.
- Data froze in flight once (21-52-18).

**E4. Battery and propellers:**
- Charge fully before each avoidance session.
- After the 21-52-18 incident and the 21-57-23 climb, check all four propellers and motor mounts before
  the next flight.

**E5. Testing:**
- Objects appeared suddenly at 0.13–0.35 m six times (21-56-08, 21-57-23). That is closer than the
  drone can react to safely.
- As the README says: step in slowly from about 1.5 m, and don't walk straight at it.

### Tested and *not* recommended

| Idea | What happened |
|---|---|
| B4: ignore jumps when measuring closing speed | On 21-57-23, the AVOID at 10.15 s came from a jump to 0.77 m. This was a real fast approach, at about 1.1 m/s. With B4 the drone reacted only at **0.23 m**. |
| B6: count "followed" only if the reading got smaller | After a sideways step a wide person still fills the beam at a steady distance. Head-on dry run: **collision** (−0.15 m), against 0.31 m today. B5 already covers its real-log case. |

### Closed-loop dry runs: current vs proposed (B1 + B2 + B4' + B5)

| Scenario | Current | Proposed |
|---|---|---|
| A: default crossing walker | ok, closest 0.41 m | ok, 0.39 m |
| B: 20-16-42 room (wall 1.3 m left, box removed at 12 s) | ok, 4 AVOIDs | ok, 1 AVOID |
| C: same room, box never removed | lands after 25 s | lands after 25 s (correct: the box is in the path) |
| D: 21-54-45 room (wall 1.4 m behind) + walker | ok, 0.43 m | ok, 0.43 m |
| E: walker stops 0.7 m away for 8 s, then leaves | ok, 0.56 m | ok, 0.56 m |
| F: slow head-on walker (0.3 m/s) | ok, 0.31 m | ok, 0.29 m |
| H: fast head-on walker (0.8 m/s) | ok, 0.14 m | ok, 0.14 m |
| I: walker from behind | ok, 0.45 m | ok, 0.44 m |
| J: crossing walker at 1.2 m/s | ok, 0.26 m | ok, 0.26 m |
| **K: person standing 0.8 m beside the path** | **lands after 25 s** | **finishes** |
| G: fast crossing into a gap between beams, with walls at the sides | **collision** | **collision** |

**G is a limitation of four narrow beams, and it exists today.** Someone crossing diagonally at 1 m/s
falls between the beams until it's too late. The proposals neither cause it nor fix it.

### Before/after replay plots

All logs, recommended set:

- [20-16-42](plots/2026-11-08_20-16-42_04_figure8_avoid_replay.png)
- [21-52-18](plots/2026-11-08_21-52-18_04_figure8_avoid_replay.png)
- [21-53-30](plots/2026-11-08_21-53-30_04_figure8_avoid_replay.png)
- [21-54-02](plots/2026-11-08_21-54-02_04_figure8_avoid_replay.png)
- [21-54-45](plots/2026-11-08_21-54-45_04_figure8_avoid_replay.png)
- [21-56-08](plots/2026-11-08_21-56-08_04_figure8_avoid_replay.png)
- [21-57-23](plots/2026-11-08_21-57-23_04_figure8_avoid_replay.png)
- [dry run](plots/2026-11-08_20-13-49_04_dry_run_replay.png)

B1 + B2 only (the WAIT proofs):

- [20-16-42](plots/2026-11-08_20-16-42_04_figure8_avoid_replay_B1_B2_only.png)
- [21-54-45](plots/2026-11-08_21-54-45_04_figure8_avoid_replay_B1_B2_only.png)

## Housekeeping

- **The stray file `=0.1.34` is deleted.** It was empty (0 bytes), created by your user account just
  before the first log.
  The name fits `pip install cflib>=0.1.34` typed without quotes: the shell reads `>` as "write output to
  a file called `=0.1.34`". Use `pip install -r requirements.txt` or `pip install "cflib>=0.1.34"`.
- **New files:**
  - `analyze_logs.py`, the plots and statistics;
  - `replay.py`, the replay tool;
  - `proposals.py`, Phase 1 only (merged into the flight code in Phase 2, then removed).
- **Unchanged:** the flight scripts, `config.py`, Unity and the venv.

---

## What changed in Phase 2

You approved S1–S4, B1, B2, B4' (with `APPROACH_SPEED` 0.25 m/s), B5, `MIN_TAKEOFF_VOLTAGE` 3.9 V, a
4 s hover before the figure-8, and keeping the current timing (T4) with corrected wording. B3, B4 and
B6 were not adopted.

| Change | Where |
|---|---|
| S1: refuse to fly if the drone reports crashed / locked / upside down; stop with "DID NOT TAKE OFF" if it is below half the target height after takeoff | `drone.py` (`check_supervisor`, `Flight.takeoff`) |
| S2: land if the height is more than 0.20 m off for 0.5 s; also land if the drone reports a crash in flight | `drone.py` (`Flight.safety_problem`) |
| S3: on link loss, repeat the land command 4× per second; say clearly when the landing couldn't be confirmed; log `supervisor.info`, `radio.rssi` and the link quality; 02 shows `NO DATA` | `drone.py`, `common.py`, `02_ranger_monitor.py` |
| S4: room check during the hover, with warnings | `drone.py` (`Flight.hover_and_check_room`), used by 03 and 04 |
| A big "RESTART THE DRONE" notice after a crash, lock, failed takeoff or lost link | `drone.py` (`restart_message`) |
| B1: the new "clear" rule (the person's beams and the beam facing back to the path) | `avoidance.py` (`return_blockers`) |
| B2: dropout hold, changed during Phase 2 (below) | `avoidance.py` (`RangeFilter.update`) |
| B4': the object's own approach speed (the drone's movement taken out), `APPROACH_SPEED` 0.25 | `avoidance.py`, `config.py` |
| B5: back away until the person would be beyond 1.0 m (0.3–0.6 m) | `avoidance.py` (`_start_avoid`) |
| `MIN_TAKEOFF_VOLTAGE` 3.9 V; `FIG8_HOVER_TIME` 4 s | `config.py` |
| A flight-note prompt after landing, shown by `analyze_logs.py` | `common.py`, `drone.py`, `analyze_logs.py` |
| The closed-loop scenarios moved into the repo | `tests.py` |

**One change to B2 that came out of `tests.py`.** As proposed, B2 kept the last distance during a
dropout. In scenario D, a single fake glitch (0.27 m on the front beam) then made "front" look blocked
for 0.5 s. The drone dodged backwards along the walker's line, and the walker came to **0.11 m** (old
logic: 0.38 m). B2 now only does what you approved: during a dropout a "near" beam is not yet clear for
the return decision. For everything else, including the dodge direction, it counts as nothing there.
With that, scenario D is at 0.42 m, and the 20-16-42 replay still waits for the box exactly as before
(RETURN at 32.1 s). `tests.py` now checks for this too.

### Closed-loop results (`python tests.py --baseline <copy of the old code>`)

| Scenario | Old logic | New logic |
|---|---|---|
| A: default crossing walker | finished, closest 0.42 m | finished, 0.42 m |
| B: 20-16-42 room, box removed at 12 s | finished, 4 AVOIDs | finished, **1 AVOID** |
| C: same room, box never removed | lands after 25 s (4 AVOIDs) | lands after 25 s (1 AVOID): correct, the box blocks the path |
| D: wall 1.4 m behind + crossing walker | finished, 0.38 m | finished, **0.42 m** |
| E: walker stops 0.7 m away for 8 s | finished, 0.56 m | finished, **1.06 m** |
| F: slow head-on walker (0.3 m/s) | finished, 0.29 m | finished, 0.28 m |
| G: fast diagonal crossing, walls at the sides (known limitation) | collision (−0.15 m) | collision (−0.09 m) |
| H: fast head-on walker (0.8 m/s) | finished, 0.14 m | finished, 0.14 m |
| I: walker from behind | finished, 0.38 m | finished, **0.44 m** |
| J: fast crossing walker (1.2 m/s) | finished, 0.26 m | finished, 0.26 m |
| K: person standing 0.6 m beyond the path | **lands after 25 s** | **finished** (3 AVOIDs, 3 rejoins) |
| L: wall 1.3 m in front, nobody around | finished, no AVOID | finished, no AVOID |

All 10 filter-rule checks and all 11 scored scenarios pass. Plots: `logs/plots/tests/scenario_A.png` …
`scenario_L.png`.

### Replay of the real flights with the new code (`python replay.py`)

The bar labelled "real flight" is the old logic (what was flown); the bar below it is the new
logic on exactly the same readings:

| Flight | Real flight (old logic) | New logic on the same readings |
|---|---|---|
| 20-16-42 | stuck in WAIT 23 s, landed | backs away 0.52 m; **RETURN at 32.1 s**, 2 s after the box's last reading |
| 21-54-45 | stuck in WAIT, landed | **RETURN at 33.4 s** |
| 21-56-08 | 7 AVOIDs (2 false "it followed us"), finished at 59.6 s | the first AVOID backs away 0.60 m instead of 0.3 m, so no false "it followed us" at 16.95 s; 2 AVOIDs; figure-8 done at 43.0 s* |
| 21-57-23 | height limit at 57.25 s | the avoidance decisions differ from 48.9 s (the height check S2 would have landed at about 52.7 s) |
| 21-52-18, 21-54-02 | – | identical decisions (nothing in them is affected) |
| a new dry run made with the new code | – | 6 of 6 decisions reproduced: the replay matches the new code too |

\* After the first different decision the readings belong to the real drone's path, so later
times are only a hint.

Plots: `logs/plots/<log name>_replay.png`.

### Checks on the flight code (mock drone, no radio)

Every safety path was run against a simulated Crazyflie. In every run the motors were off at the end:

- **Drone reports locked:** refused before takeoff, with the restart notice.
- **Motors don't lift:** "DID NOT TAKE OFF" at 3.0 s, disarmed, restart notice.
- **Height runaway:** landed after 0.5 s at 0.87 m.
- **Crash reported in flight:** landed, restart notice.
- **Radio link lost:** the land command was sent 10 times instead of once; "landing could not be
  confirmed" and the restart notice were shown.
- **Unchanged paths still work:** the low-battery landing, the 3.85 V refusal (new 3.9 V limit),
  geofence, land key, Ctrl+C twice, kill key, missing deck and USB connected.
- **Room check:** warned about an object 0.25 m from the path.
- **Flight-note prompt:** saved the note.

**Not tested on real hardware yet.** The first real check after this change: `01_hover_test.py`, then
`03_figure8.py`. The `ROOM:` line should appear in 03, and you should get a note prompt after each flight.
