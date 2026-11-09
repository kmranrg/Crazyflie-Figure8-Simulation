# Crazyflie hardware scripts: figure-8 with person avoidance

These scripts make the real Crazyflie 2.1 do what the Unity simulation does:
fly a figure-8 at a fixed height, notice a person with the Multi-ranger deck,
move out of the way, and go back to the figure-8 when the person has gone.

You build up to it in four small steps. **Do them in order, and only move on
when the current step works.**

| Step | Script | Flies? | What it checks |
|---|---|---|---|
| 0 | `03_figure8.py --dry-run`, `04_figure8_avoid.py --dry-run` | no | The planned path and the avoidance logic, drawn as a plot. No drone needed. |
| 1 | `01_hover_test.py` | yes | Takeoff, hovering in place for 10 s, landing |
| 2 | `02_ranger_monitor.py` | **no** | That the Multi-ranger sees you, and from which side |
| 3 | `03_figure8.py` | yes | The figure-8 on its own, no avoidance |
| 4 | `04_figure8_avoid.py` | yes | The full behaviour: figure-8 + avoidance + return |

Other files:

| File | What it is |
|---|---|
| `config.py` | **Every setting**: radio address, height, figure-8 size and speed, avoidance distances, safety limits |
| `figure8.py` | The figure-8 maths (the same curve as Unity's `Figure8Controller`) |
| `avoidance.py` | The avoidance state machine (FOLLOW / AVOID / WAIT / RETURN) and the ranger filter |
| `drone.py` | Everything that talks to the drone: checks, takeoff, safety, landing |
| `common.py` | Flight log writer and the emergency-stop keys |
| `dry_run.py` | Fake drone, fake people and fake ranger for `--dry-run`, plus the plots |
| `analyze_logs.py` | Plots and numbers for every flight log (§9) |
| `replay.py` | Runs recorded ranger readings through the avoidance logic again (§9) |
| `tests.py` | Checks the avoidance logic in simulated rooms; run it after every change (§9) |
| `logs/` | Created on the first run: one CSV per flight, the dry-run plots, `FLIGHT_NOTES.md` (your notes) and `FLIGHT_REPORT.md` (the analysis of the first flights) |

---

## 1. Installation

From the repository root (`Crazyflie-Figure8-Simulation/`):

```bash
source venv/bin/activate
pip install -r CrazyFlie-Nanodrone/hardware/requirements.txt   # adds matplotlib for the plots
cd CrazyFlie-Nanodrone/hardware
```

Everything else is the Python standard library plus cflib (0.1.34 is already in
your venv), and works with Python 3.10 to 3.14. Always run the scripts from
inside the `hardware/` folder.

---

## 2. Hardware setup

**Decks**
- **Flow deck v2: underneath** the Crazyflie, with the small camera and the
  height sensor facing the floor. Nothing may hang in front of them (cables,
  tape, the battery strap).
- **Multi-ranger deck: on top**, with nothing blocking its five sensors.
- Push both decks fully onto the pins, with each deck's markings facing the same
  way as the Crazyflie's front. The **front** of the Crazyflie is the side
  *opposite* the two blue LEDs.
- Check the orientation with step 2 (`02_ranger_monitor.py`): a hand in front of
  the drone must change the **front** reading, not another one.

**Battery**
- Use a fully charged battery (4.2 V). The scripts refuse to take off below 3.9 V
  and land by themselves below 3.3 V. (A nearly empty battery may still pass 3.9 V
  at rest, then sag; in the first test flights the one height wobble happened on a
  battery that started at 3.83 V.)
- Expect **about 4–5 minutes** of flight per charge with both decks fitted.
- Strap it down so it can't slide, and keep it away from the propellers and
  sensors.

**Radio**
- Plug the Crazyradio 2.0 into the computer and switch the drone on.
- The address is in `config.py` (`URI = "radio://0/80/2M/E7E7E7E7E7"`).
- Close the cfclient app if it is open: only one program can use the radio at a time.

**Placing the drone before each flight**
- Put it **on the floor at the centre of the figure-8**, on a flat spot.
- Point its front (opposite the blue LEDs) in the direction you want to be
  "forward" (**+X**). Positions are measured from this spot, in metres:
  **+X** = the drone's front, **+Y** = the drone's left, **+Z** = up.
  The figure-8 runs mostly left–right.

---

## 3. A safe flying space

- **Floor space:** clear at least **4 m × 4 m** around the start point. The
  geofence lets the drone go 1.5 m from the start in any direction; add room
  for overshoot.
- **Walls and furniture at flight height:** keep at least **1.5 m free to the
  left and right** of the start point and **1.25 m in front and behind**. That
  leaves 1 m between the figure-8 and anything else. Closer than that, the drone
  reacts to the wall instead of to people. During the hover before the figure-8,
  steps 3 and 4 print what each beam sees and warn when something is too close:

  ```
  >>> ROOM: front 2.38 m (2.13 m from the path), back nothing within 4 m, left 1.32 m (0.82 m from the path), ...
  >>> WARNING left: something 0.82 m from the figure-8 (want at least 1.0 m). ...
  ```
- **Floor surface:** it must have **texture and must not be shiny**. The Flow
  deck navigates by watching the floor move under it, like an optical mouse.
  - Good: patterned rugs, wood with visible grain, a mat with tape stripes or newspaper on it.
  - Bad: glossy tiles, polished concrete, plain single-colour carpet, glass,
    reflections, sunlight patches.
  - On a bad floor the drone drifts or slides away.
- **Lighting:** a bright room. Dim light makes the Flow deck unreliable.
- **No obstacles under the path:** a table or box under the drone looks to it as
  if the floor suddenly rose.
- **Ceiling:** at least 2 m (the scripts never go above 1.2 m).
- **People:** in steps 1 and 3, **nobody within 2 m** of the flight area. In
  step 4 only the "test person" comes closer, slowly, and the operator stays back
  (see §5).
- Propeller guards are a good idea. Keep pets out of the room. Wear glasses if
  you have them.

---

## 4. Before every session, and after every flight

### Before every session

- [ ] **Power-cycle the drone if anything went wrong last time:** a crash, a tumble,
      a hard landing, a lost radio link, or a "RESTART THE DRONE" message. After a
      crash the drone locks itself and won't take off until it is switched off and on.
- [ ] **Propellers:** undamaged (no cracks, chips or bends), firmly on, each on the
      correct motor (see Bitcraze's assembly guide). Check again after any crash.
- [ ] **Battery fully charged** (4.2 V), strapped down, USB cable **unplugged**.
- [ ] Flow deck underneath and Multi-ranger on top, both pushed fully onto the pins.
- [ ] `../scripts/detect_decks.py` lists both decks (the scripts also check this before every takeoff).
- [ ] Floor textured and not shiny, room well lit, area clear (§3).
- [ ] **Room clearance:** 1.5 m free left and right of the start point, 1.25 m in
      front and behind, at flight height (§3). Watch for the `ROOM:` warning.
- [ ] Drone on the floor at the centre of the figure-8, front pointing the way you want.
- [ ] You know how to stop it (try the keys once in `02_ranger_monitor.py`):
      **SPACE**, **q** or **Enter** = land now, **Ctrl+C** = land, **k** = cut the motors.
- [ ] The terminal window running the script has keyboard focus, so key presses reach it.
- [ ] For a new script, the matching `--dry-run` plot looked right.
- [ ] You are standing in the operator spot (§5), and nobody else is inside 2 m.

Every flying script runs these checks automatically, in this order, and refuses
to fly (with a message saying why) if one fails:
1. Flow deck and Multi-ranger detected.
2. Battery at least 3.9 V, and not charging.
3. The drone does not report that it crashed, is locked or is upside down.
4. It prints exactly what it is about to do and waits for **Enter**.
5. It resets the position estimator and waits for it to settle; the drone must be still.
6. It arms the motors and takes off.
7. **After takeoff it checks the drone really is in the air** (at least half the
   target height). If not, it stops: "DID NOT TAKE OFF".

During the flight it lands by itself if any of these happen:
- you press a land key or Ctrl+C;
- the drone goes more than **1.5 m** from the start or higher than **1.2 m**;
- **the height is more than 0.2 m off target for 0.5 s** (e.g. sinking, or climbing
  on its own);
- the drone reports it crashed, is locked or is upside down;
- the battery stays below 3.3 V for 1 s;
- the radio data stops for 0.5 s;
- the flight lasts longer than 120 s;
- (step 4 only) it cannot get back to the figure-8 within 25 s.

**"RESTART THE DRONE".** After a crash, a lock, a failed takeoff or a lost radio
link, the terminal shows a big notice in exclamation marks. Switch the drone off
and on, check the propellers, then fly again.

### After every flight: one line of notes

When the drone has landed, the script asks:

```
Flight note, one line: what you did, what the drone did (Enter to skip):
>
```

Write one short line, for example *"walked slowly into the right beam at 1 m,
it moved left, returned after I stepped back"* or *"box on the right lobe;
stayed in WAIT; landed after 25 s"*. It is saved in `logs/FLIGHT_NOTES.md`
next to the log's name, and `analyze_logs.py` shows it on that flight's plot.
The logs record what the drone measured, but not what you did or saw, and a
week later nobody remembers. Notes are what make later analysis possible.
You can also edit `FLIGHT_NOTES.md` by hand (one line per flight:
`- <log name>: text`).

> **How landing works.** The landing runs *on the drone itself*, so once it has
> started it finishes even if the program crashes or the radio is lost. If the
> radio is already lost when the landing starts, the script keeps repeating the
> land command (4× per second) in case the link comes back for a moment. If it
> never gets through, the drone's own safety timeout stops the motors and it
> drops; the terminal then says the landing could not be confirmed.
> Pressing Ctrl+C again during landing is ignored on purpose. Use **k** only in
> an emergency: it switches the motors off and the drone **drops**.

---

## 5. Where to stand

The Multi-ranger has **five narrow beams**: front, back, left, right and up.
Each one sees a cone only about **27° wide**, out to about 4 m. It sees nothing
at the diagonals in between, and it can't tell a person from a wall.

```
                 front (+X)
                    ^
       blind        |        blind
          \      .--|--.      /
            \   /   |   \   /
   left  <------ [drone] ------>  right
   (+Y)         \   |   /        (-Y)
                 '--|--'
           OPERATOR |
           stands   v
           here   back
          (diagonal, 2.5 m+)
```

- **The operator (you, at the keyboard):** stand **diagonally behind** the
  drone (45° between "back" and "left" or "right"), **at least 2.5 m from the
  start point**.
  - At a diagonal you sit in the blind spot between two beams, so the drone does
    not react to you.
  - At 2.5 m you are outside the 1.5 m geofence plus the 1 m "clear" distance,
    even when the drone is at the edge of its area.
  - Don't stand straight behind, in front, or to the side: that is where the beams point.
- **The test person (step 4):** start about 2 m away and walk **slowly** (about
  0.3 m/s, a slow shuffle) so that you cross **in front of or beside** the drone,
  into one beam at a time. Don't push things suddenly into a beam close to the
  drone (closer than about 0.5 m): it has no time to react.
- **Never walk straight at the drone.** See §11 for why.
- **Everyone else:** further away than the operator, also at a diagonal.

---

## 6. Running each step

### Step 0: dry runs (no drone)

```bash
python 03_figure8.py --dry-run
python 04_figure8_avoid.py --dry-run
```

These draw the plan and save it as `logs/03_figure8_dry_run.png` and
`logs/04_figure8_avoid_dry_run.png`.

- **03 plot:** a 1 m × 0.5 m figure-8 around the start point, well inside the
  geofence circle. On the right, the speed: starting from zero, peaks of 0.36 m/s,
  never above the 0.5 m/s limit.
- **04 plot:**
  - Left: the drone's path from above, coloured by state. The fake person's walk
    is the grey arrow; triangles mark where AVOID started and which beam fired.
  - Top right: the fake ranger readings. **×** marks are fake glitches that the
    filter correctly ignores.
  - Bottom right: the state timeline.
  - The terminal prints every state change and the **closest the person came to
    the drone**.
- **Your own fake person:** walking from (X0, Y0) to (X1, Y1) at SPEED m/s,
  starting DELAY s into the figure-8:

  ```bash
  python 04_figure8_avoid.py --dry-run --person 0.35 2 0.35 -2 0.8 3
  python 04_figure8_avoid.py --dry-run --person 1.5 0.2 -1.5 0.2 0.3 5 --person 0.45 -0.6 0.45 -0.6 0 0
  ```

  - Use `--person` more than once for several people.
  - SPEED 0 means a person standing still at (X0, Y0).
  - You can also edit `FAKE_PEOPLE` in `config.py`.
  - The `--width`, `--speed`, `--laps` and `--height` options work in dry runs too.

### Step 1: hover test

```bash
python 01_hover_test.py                 # 0.5 m, 10 s
python 01_hover_test.py --height 0.4 --time 5
```

**Expect:** a calm climb to about knee height, hovering with only small
movements, then a soft landing. The terminal prints the position once per second.

**It worked if** x and y stay within about ±0.1–0.2 m, z stays near 0.5, and it
lands within about 20 cm of where it took off.

### Step 2: Multi-ranger monitor (does not fly)

```bash
python 02_ranger_monitor.py
```

- Put the drone on a stool or box at roughly flight height, then walk around it
  slowly. A table of distances updates live.
  - `BLOCKED` means "would start avoiding".
  - `near` means between 0.6 m and 1.0 m.
  - `clear` means further than 1.0 m, or nothing seen.
- Press **q** to stop.
- If the radio link drops, the last line says `NO DATA for X s` (the numbers
  above it are then old).
- On the floor every beam may show 0.1–0.3 m: that is the floor itself (each beam
  is a cone that touches the floor about 0.17 m away). Lift the drone to flight
  height to see the room.

**It worked if:**
- each side reacts only when you are on that side;
- you can be seen from about 2–3 m away;
- you get `BLOCKED` at about 0.6 m;
- at the diagonals you are not seen (that is normal).
- Also check: walls, furniture and the operator's spot are **not** `BLOCKED`
  from where the drone will fly.

### Step 3: figure-8, no avoidance

```bash
python 03_figure8.py --dry-run          # look at the plan first
python 03_figure8.py                    # 1.0 m wide, 0.25 m/s, 2 laps
python 03_figure8.py --width 0.6 --speed 0.2 --laps 1    # even gentler first try
```

**Expect:**
- takeoff and a 4 s hover, with the `ROOM:` printout;
- two figure-8s, about 12 s each, that start slowly and end slowly at the centre;
- landing.

**It worked if:**
- the shape is recognisable and smooth, with no jerks;
- the drone ends up within about 20–30 cm of where it started (the rest is Flow
  deck drift, which is normal);
- the log's `x`/`y` track the `sp_x`/`sp_y` setpoints within a few centimetres.

### Step 4: figure-8 with avoidance

```bash
python 04_figure8_avoid.py --dry-run    # look at the plan first
python 04_figure8_avoid.py
```

What happens during the flight:
1. The drone flies the figure-8 (FOLLOW).
2. The test person steps slowly into one beam at about 1 m and keeps moving
   closer. Below 0.6 m the terminal prints `AVOID: front beam sees 0.55 m, ...`
   and the drone backs away, far enough that the person would be about 1.1 m
   away (0.3–0.6 m). If that side is blocked it goes 0.3 m sideways, or it holds
   position. Someone walking *at* the drone (the object itself approaching faster
   than 0.25 m/s) makes it react from 1.2 m and step sideways first. The drone's
   own movement doesn't count, so flying towards a wall is not "approaching".
3. It holds there (WAIT) until, for 2 s, the beams that saw the person **and**
   the beam facing back to the figure-8 see more than 1.0 m, and nothing is
   closer than 0.6 m. The person must step back out of range. A wall on another
   side doesn't keep it waiting.
4. It flies slowly back to the exact point where it left the figure-8 (RETURN)
   and carries on from there (FOLLOW).

**Start gently:** first just step into the side beam at about 0.8 m and stop. A
good first goal is one clean FOLLOW → AVOID → WAIT → RETURN → FOLLOW cycle.

---

## 7. Changing the settings

Everything is in `config.py`, with a comment on each line. The most useful ones:

| Setting | Default | Meaning |
|---|---|---|
| `FLIGHT_HEIGHT` | 0.5 m | Flight height |
| `FIG8_WIDTH` | 1.0 m | Left–right size of the figure-8 (front–back is half) |
| `FIG8_SPEED` | 0.25 m/s | Average speed (peak is about 1.46×) |
| `FIG8_LAPS` | 2 | Laps before landing |
| `FIG8_HOVER_TIME` | 4 s | Hover (and room check) before the figure-8 |
| `AVOID_DISTANCE` / `CLEAR_DISTANCE` | 0.6 / 1.0 m | Start avoiding below / count as clear above |
| `AVOID_CONFIRM_COUNT` | 3 | Readings in a row needed (glitch filter). Each measurement arrives twice, so 3 readings = **2 measurements, about 0.15 s** |
| `APPROACH_SPEED` / `EARLY_AVOID_DISTANCE` | 0.25 m/s / 1.2 m | Someone approaching faster than this is avoided from this distance |
| `RETREAT_DISTANCE` / `MAX_RETREAT_DISTANCE` | 0.3 / 0.6 m | Sideways step / longest move away from the person |
| `DROPOUT_HOLD_TIME` | 0.5 s | "Nothing in range" this soon after a real reading may be a sensor dropout; it doesn't count as clear yet |
| `CLEAR_TIME` | 2 s | How long it must be clear before returning |
| `GEOFENCE_RADIUS` / `GEOFENCE_MAX_HEIGHT` | 1.5 / 1.2 m | Safety box |
| `HEIGHT_ERROR_LIMIT` / `HEIGHT_ERROR_TIME` | 0.2 m / 0.5 s | Land if the height is this far off for this long |
| `MIN_TAKEOFF_VOLTAGE` / `LAND_VOLTAGE` | 3.9 / 3.3 V | Battery limits |

- `--height`, `--width`, `--speed` and `--laps` override the defaults for one run.
- The scripts refuse settings that would be too fast (over `MAX_SPEED` = 0.5 m/s)
  or too big for the geofence.
- **Change one thing at a time**, and run `python tests.py` and the dry run after
  each change (§9).

---

## 8. Flight logs

Every run writes `logs/<date>_<time>_<script>.csv`. Dry runs write one too, so
real and simulated runs can be compared column for column. One row is written
per control step (20 per second):

| Column | Meaning |
|---|---|
| `t` | seconds since takeoff |
| `state` | `TAKEOFF`, `HOVER`, `FOLLOW`, `AVOID`, `WAIT`, `RETURN`, `LAND` (or `MONITOR` in step 2) |
| `event` | text of any state change or abort, e.g. `AVOID: left beam sees 0.52 m, ...` |
| `beam` | which beam fired at that moment |
| `x, y, z, yaw` | where the drone *thinks* it is (m, degrees) |
| `sp_x, sp_y, sp_z` | where we told it to be |
| `vbat` | battery voltage |
| `front, back, left, right, up` | raw ranger readings in m (32.766 on the real drone, 8 in dry runs, means nothing seen) |
| `zrange` | height measured by the Flow deck |
| `squal` | Flow deck surface quality, 0–255. **Low values (< ~30) mean a bad floor.** |
| `person_x, person_y` | dry runs only: where the fake person was |
| `supinfo` | the drone's supervisor bits (bit 5 upside down, 6 locked, 7 crashed) |
| `rssi`, `link` | radio signal strength reported by the drone, and link quality (0–100 %) |

The CSV files open in any spreadsheet program. To compare with Unity, convert
positions using §11. Logs and plots stay on your computer: `.gitignore` keeps
`logs/*.csv`, the plots and the `cache/` folder out of git (`FLIGHT_NOTES.md` and
`FLIGHT_REPORT.md` can be committed).

---

## 9. Analysing flights and testing changes

All three tools work without a drone.

**`analyze_logs.py`: a plot and a summary for every flight**

```bash
python analyze_logs.py                     # every log in logs/
python analyze_logs.py logs/2026-11-08_20-16-42_04_figure8_avoid.csv
```

- Saves one PNG per log into `logs/plots/`, named after the log.
- **Figure-8 flights:** the path from above on top of the planned figure-8,
  coloured by state, with markers for AVOID (and which beam), rejoin and landing.
  Grey dots are where the beams hit something: a rough map of the room. On the
  right: height, every beam over time (avoid/clear lines, dashes at the top where
  there was no reading), tracking error, battery and the state timeline.
- **Hover flights:** position over time and the spread around the target.
- Also writes `figure8_summary.png` (all figure-8 flights against the plan) and
  `summary.md` (one table row per flight, with your flight note).

**`replay.py`: what would the avoidance logic decide on a real flight?**

```bash
python replay.py                           # every 04 log
python replay.py --set CLEAR_DISTANCE=0.8  # the same, with a setting changed
```

It feeds the recorded ranger readings of each 04 log through `avoidance.py`
again and plots the real flight next to the replay (`logs/plots/<log>_replay.png`).
- **Logs flown with the current code:** the replay should make the same decisions
  as the log, and the terminal says so.
- **After you change `avoidance.py` or a setting:** you see exactly where the new
  logic decides differently, on real data.
- **Careful:** after the first different decision, the real drone was somewhere
  else than the new logic would have sent it. From there on the replay is only a
  hint.

**`tests.py`: run after every change to the avoidance logic or its settings**

```bash
python tests.py              # prints PASS / FAIL for each check
python tests.py --plots      # also a plot per scenario in logs/plots/tests/
```

- **Rules of the ranger filter:** e.g. "nothing in range counts as clear",
  "a dropout does not count as clear straight away", "flying towards a wall is not
  'approaching'".
- **Closed-loop scenarios A–L:** the simulated drone flies the figure-8 with the
  real logic, in rooms rebuilt from the first test flights (a wall 1.3 m to the
  left with a box in the path, a wall 1.4 m behind, a wall 1.3 m in front), with
  walkers crossing, approaching head-on or from behind, stopping, or standing
  still. Each scenario checks how the flight ends and how close a person came.
- Scenario G (a fast walker crossing between two beams, with walls at the sides)
  is a known limitation: it is shown but not counted as a failure.
- `python tests.py --baseline <folder>` also runs an older copy of `avoidance.py`
  and `config.py` from that folder, for a before/after comparison.

---

## 10. Common problems

| Problem | Likely cause and fix |
|---|---|
| **"Connection failed"** | Drone off, radio unplugged, cfclient still open, or the wrong `URI`. Run `../scripts/detect_decks.py` (it scans for the drone). |
| **"... deck NOT detected"** | Deck not pushed fully onto the pins. Reseat it, then switch the drone off and on. |
| **"Battery ... below 3.8 V"** or **"charger is connected"** | Charge it / unplug USB. |
| **"Position estimate did not settle"** | The drone was moved during the reset, or the floor is too plain or too dark. Improve the floor or the light and keep the drone still. |
| **"DID NOT TAKE OFF"**, **"the drone reports it is locked / crashed"**, or **"RESTART THE DRONE"** | The drone locked itself after a crash, tumble or lost link. Switch it off and on. Check the battery, and that the props aren't damaged or touching anything. |
| **"HEIGHT: ... instead of 0.50 m"** | It sank or climbed on its own. Usually a weak battery, or a damaged propeller or motor. Charge, check the props, try `01_hover_test.py`. |
| **"NO DATA FROM THE DRONE during the whole landing"** | The radio link was lost. Put the Crazyradio on a USB extension cable, raised, in sight of the drone; stay within a few metres. Restart the drone before the next flight. |
| **Takes off, then slides away in one direction (drift)** | Floor texture or lighting is poor (check `squal` in the log), a deck isn't straight, or the drone moved during the estimator reset. Some drift (10–30 cm per minute) is normal with the Flow deck alone. |
| **Circles in a growing spiral ("toilet-bowling")** | Usually a bad yaw estimate or a mechanical problem: a damaged or wrong propeller, a weak motor, or a deck not mounted flat. Land, check the props are on the right motors and undamaged, and check the decks sit flat. A shiny floor can also cause it. |
| **Jerky or wobbly figure-8** | Too fast for the conditions: lower `--speed` or `--width`. |
| **Avoids when nobody is there (false detection)** | A wall, furniture or the operator is inside a beam. Use step 2 to find it, clear the area, or stand at a diagonal. Strong sunlight can also disturb the sensors. |
| **Doesn't react to a person (missed detection)** | The person is in a diagonal blind spot, below or above the beams, wearing very dark or shiny clothes, or moving too fast. Approach slowly, straight into one beam. |
| **"could not get back to the figure-8 within 25 s"** | Someone (or something) stayed within 1 m of the drone on the side it was avoiding, or on its way back. That is intended: it lands rather than hover forever. |
| **`ROOM:` warning** | A wall or furniture is less than 1 m from the figure-8. Move the start point (§3). |
| **Lands on its own with "GEOFENCE"** | It drifted or was pushed more than 1.5 m. Check the floor and the drift (above). |
| **Keys do nothing** | The terminal window isn't focused, or the script runs inside an IDE "run" panel. Run it from a normal terminal. Ctrl+C always works. |

---

## 11. Simulation vs. real drone

The scripts reproduce the simulation's behaviour, but several things change on
real hardware. Expect real flights to look different from Unity because of these.

| | Unity simulation | Real drone (these scripts) | Effect |
|---|---|---|---|
| Figure-8 size | 4 m × 2 m at 2.5 m height | 1 m × 0.5 m at 0.5 m (adjustable) | Fits a room, stays where the Flow deck works best |
| Speed | 0.66–1.41 m/s | 0.17–0.36 m/s (average 0.25) | Slower, but gentle on the Flow deck and the sensors |
| Path following | A virtual spring and brake pulling the drone toward a target that never stops | Position setpoints to the drone's own controller | Much tighter tracking; the drone can follow the setpoint closely |
| Position | Exact (read from the physics engine) | **Estimated** by the Flow deck from floor movement | Drifts slowly; the figure-8 can "walk" across the room over many laps |
| Height | Absolute Unity Y | Measured from the floor below by the Flow deck | Over furniture the drone thinks the floor rose |
| Person detection | Exact headset position, all directions, 3 m sphere, through walls | 5 narrow beams, ~4 m, blind diagonals, sees walls too | Can miss people at a diagonal; may react to furniture |
| Sensor quality | Perfect, instant | Noisy, glitches and short dropouts, ~10 measurements/s per beam (each arrives twice), radio delay | Hence the 3-readings-in-a-row filter (2 measurements), the dropout hold and the 0.6 / 1.0 m hysteresis |
| Avoidance | Smooth push away from the head (potential field); the figure-8 target keeps moving | State machine; the figure-8 is **paused** and resumed where it left off | Predictable; no cutting across the figure-8 after avoiding |
| Avoidance speed | Up to several m/s, ~45 g of push | 0.4 m/s maximum | Cannot escape someone walking straight at it (§5) |
| Tilt | Never tilts | Tilts to move, which tilts the beams | Hard moves can make a beam see the floor |
| Battery | Infinite | ~4–5 min; voltage sags under load | Short sessions; auto-land when low |
| Takeoff / landing | Spawns in mid-air | Real takeoff and landing | Extra seconds at the start and end of the logs |

**Converting coordinates** (Unity: X right, Y up, Z forward, left-handed;
Crazyflie: X forward, Y left, Z up, right-handed):

```
Crazyflie -> Unity:   x_unity = -y_cf     y_unity = z_cf + floor_height     z_unity = x_cf
Unity -> Crazyflie:   x_cf    =  z_unity  y_cf    = -x_unity               z_cf    = y_unity - floor_height
velocities: the same, without the floor term          yaw: yaw_cf = -yaw_unity
```

**Known limitations, found with the dry run:**
- **Someone walking straight at the drone.** With only five beams the drone
  cannot tell which side of the beam the person is on. With a safe top speed of
  0.4 m/s it cannot outrun them. People walking *across* the path were avoided
  in every dry-run case tried, up to 1.2 m/s. People walking *straight at* the
  drone faster than about 0.3 m/s could still reach it. **People must not walk
  directly at the drone.** The drone gets an earlier warning (from 1.2 m) and
  steps sideways when someone approaches, but this is a help, not a guarantee.
- **Someone crossing fast at a diagonal.** Between two beams the drone is blind,
  so a fast walker crossing diagonally can reach it before any beam sees them
  (`tests.py` scenario G).
- **Someone standing still right next to the path.** The drone avoids, returns,
  meets them again and repeats, slowly working its way around the figure-8 until
  the person moves or the 120 s flight-time limit lands it.
