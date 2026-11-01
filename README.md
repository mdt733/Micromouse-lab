# MicroMouse Lab — v0.2 (Git-ready experimental prototype)

A **local HTML/JavaScript workshop + Python simulation backend** for experimenting with micromouse robot configurations and autonomous controllers.

**Important:** This version runs a **custom 2D planar physics approximation**, rendered in a 3D WebGL scene. It **does not yet use MuJoCo**. The physics module is deliberately independent of the controller interface and browser for a future MuJoCo backend. Dynamics are not calibrated to any physical robot. Do not use these results for engineering predictions without measurement and validation.

## What works

- Three-panel browser UI: adjustable **Garage**, real editable Python **controller.py**, interactive **3D world** with **console/telemetry**.
- Camera modes: perspective, top, follow; mouse orbit and scroll zoom.
- Garage settings for mass, wheel track and radius, tyre grip and stiffness, brushed/brushless/ideal motor approximations, Kv/gears/current, battery droop, fan suction and spool-up, ToF range and noise, and run seed/duration. Two editor-loadable controller examples: wall follower and 90° gyro turn.
- Courses: straight corridor, 90° corner, slalom. The yellow dashed route is a viewer-only guide, **not** supplied to the controller.
- Real planar physics calculations at **1 kHz**; **200 Hz** sensor/controller cycles; browser frames at approximately 50 Hz.
- Five noisy ToF distances (computed from course walls), encoder ticks, noisy yaw-rate gyro, battery voltage. Sensor visibility respects line-of-sight and maximum range.
- Python control in a **separate child process** with per-cycle timeout, editable inside the app.
- Save & Run, Pause, Step (20 ms, four controller updates), Reset, Apply settings, Export current run as JSON with code/configuration/telemetry. **Continuous Run now uses a dedicated autonomous simulation clock independent of the browser and its WebSocket.**
- **Flight recorder:** 50 Hz snapshots include pose, speed, forward/lateral acceleration, grip utilisation, fan downforce, motor current, energy, sensor readings and time-stamped logs. Pause or finish a run, drag the slider to inspect any recorded instant; Replay plays it back. Recorded data can be exported as JSON.
- **Connection fallback:** browser polls `/api/status` over ordinary HTTP if the live WebSocket stream is unavailable, so the viewer can keep updating.
- **Git-ready source:** `.gitignore` excludes local virtual environments, runtime files and secrets. The Windows uploader checks Git/GitHub CLI/authentication, prompts for missing Git identity, initialises Git if needed, creates a remote if needed, and asks before committing and pushing.
- Three.js and Monaco load from CDNs; without Monaco, the plain textarea still works. Without Three.js, a top-down 2D canvas fallback still works.

## Start on Windows

1. Unzip somewhere convenient (not inside another project).
2. Double-click `launch-windows.bat`. This sets up `.venv` and installs the Python dependencies on first run.
3. Open **http://127.0.0.1:8000** (the launcher also attempts to open your browser).

Requires Python 3.10+ and an internet connection for the initial package install. Browsers can use the 2D fallback when the Three.js CDN is unavailable.

## What's changed in v0.2

- **Run fix:** simulation time advances on an independent Python clock thread; previously the main loop shared its work with live WebSocket broadcasting. The browser also gets a fallback status poll when its WebSocket cannot connect.
- **Tolerant controller scheduling:** the worker timeout now allows short scheduling stalls. A stalled controller still stops the run and reports an error.
- **Scrubbable timeline:** every 20 ms of simulated time, record full physics measurements and raw simulated sensors. Drag the **Flight Recorder** slider to pause and inspect, click **Replay** for recorded playback, and **Latest** to return to live state. The console is filtered to messages up to the selected replay time. Replay does **not** re-run controller code or physics.
- **Telemetry:** acceleration magnitude, forward/lateral acceleration, grip used, left/right motor current and battery, alongside the existing readings. The graph displays speed, grip and acceleration, with a playhead in replay mode.
- **GitHub uploader:** run `upload-to-github.bat` from the extracted project directory. Default remote creation is **private** unless you explicitly select public.

### Updating from v0.1 without losing your work

**Extract v0.2 to a separate directory**. If you edited `data/controller.py` in v0.1, copy that file into the new `data/` folder before starting. If you adjusted the hardware settings, also copy `data/config.json` (if present). Do not overwrite your existing project directory blindly.

### Upload to GitHub (Windows)

1. Install **Git for Windows** and **GitHub CLI** (`winget install --id GitHub.cli -e`) if needed.
2. Double-click **`upload-to-github.bat`** in the project directory.
3. If GitHub CLI is not signed in, the script opens the official browser login. It checks `gh auth status` and configures Git credential integration. It also asks for a commit author name/email if missing, set locally for this repository.
4. Review the files it stages, approve the commit, choose your repository name and **private** or **public** visibility (private recommended), then approve the push. Existing `origin` remotes are shown and preserved.
5. Subsequent executions commit new changes and push to the same repository; there is no force-push.

The uploader is an ordinary batch file, intended to be **run on your Windows PC**. It cannot log you into GitHub from this chat, and it hasn't been Windows-executed in this environment. Authentication secrets are never requested by the batch file itself. `.gitignore` excludes `.env` files, generated run traces and local settings; still review `git status --short` before approving a public upload.

## Start on Linux / WSL

```bash
cd micromouse-lab-v0.1
./launch-linux.sh
# Open http://127.0.0.1:8000 in Windows or your WSL browser.
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000
```

## Controller contract

The app stores Python controller source in `data/controller.py`; you can also load the bundled **Wall follower** and **90° left turn** examples from the editor dropdown. Every new **Save & Run** resets the environment and starts a fresh worker process. The worker calls either `Controller().step(sensors, dt)` or a top-level `step(sensors, dt)` on every controller tick.

```python
class Controller:
    def step(self, s, dt):
        left_mm = s.tof_mm.get('left')  # float or None (out-of-range)
        return Outputs(left_motor=0.3, right_motor=0.3, fan=0.7)
```

`Sensors`: `tof_mm: dict`, `encoder_ticks: tuple[int,int]`, `gyro_z_rad_s: float`, `battery_v: float`, `timestamp_s: float`. `Outputs`: `left_motor` and `right_motor` in [-1,+1], `fan` in [0,+1]. The outputs are driver requests; the simulator computes actual motor torque and wheel slip separately. `print()` statements are forwarded to the console.

**Local use only:** Executed controller source has normal Python process permissions. The process watchdog prevents a stuck controller from indefinitely blocking the sim, but **is not a security sandbox**. Only run code you trust, keep the server bound to loopback, and never expose it to the public internet.

## Physics status and modelling assumptions

| Subsystem | v0.1 status | Next version |
|---|---|---|
| Chassis dynamics | Planar (x, y, yaw), approximate mass/yaw inertia | MuJoCo rigid bodies, CG, pitch/roll/load transfer |
| Tyres | Slip-velocity longitudinal/lateral stiffness with vector force saturation | Calibrated tyre-slip curves, wheel load, tyre compliance |
| Brushed motor | DC back-EMF/current/gear ratio with current limiting | Measured Kv, Kt, winding inductance, speed-dependent efficiency |
| Brushless | Same simplified DC model with coarse low-speed commutation penalty | BLDC + ESC current control and response |
| Battery | Instantaneous voltage sag and energy accumulation | SOC, battery chemistry, thermal effects |
| Fan | First-order force lag, fixed maximum normal force and electrical power | Fan pressure-flow curve, air leakage, skirt gap and tilt |
| Collisions | Circular robot hull and 2D axis-aligned box walls | True robot/wall contacts in MuJoCo |
| ToF | Planar ray to walls + Gaussian noise + dropout | Beam cone, sensor rate/latency, reflective materials |
| Viewer | True 3D graphics of an approximate 2D state | Pose interpolation + physical geometry + force overlays |

**Time models:** physics ∆t = 1 ms, controller interval = 5 ms, frame frequency target ≈50 Hz. The dedicated simulation thread attempts one 20 ms chunk per 20 ms of wall time. On an overloaded host it may run slower than real time, but physics and controller timestep values remain fixed. Telemetry is timestamped by simulation time.

## Source map

- `backend/physics.py` — physics, parameters, courses, sensors, contact approximation.
- `backend/controller_worker.py` — child process, controller classes, timeouts, log capture.
- `backend/server.py` — FastAPI REST/WebSocket server, simulator lifecycle, persistence, run export.
- `web/index.html`, `web/style.css`, `web/app.js`, `web/viewport.js` — interface, editing, WebGL rendering, charts.
- `data/controller.py` — editable starting controller.
- `data/config.json` — written when hardware settings are applied.
- `tests/test_physics.py`, `tests/test_run_replay.py` — physics and unattended-run/replay contract tests (`python -m pytest -q`).
- `upload-to-github.bat`, `.gitignore`, `.gitattributes` — Git/GitHub upload and platform-neutral source formatting.

## Roadmap

1. Validate the planar kinematics with measured acceleration/braking tests and expose consistent metrics.
2. Add a **MuJoCo backend** with true wheel contacts, torque actuators, and suction applied as external body forces; compare it against the planar baseline, not silently interchange results.
3. Introduce motor model presets with explicit data sheets, torque/speed curves, and ESC modes.
4. Make more complete micromouse 16x16 mazes with exploration and flood-fill; editor can load multiple scripts.
5. Add reproducible benchmarks, ghost runs, slow-motion and advanced telemetry replay, controller safety limits, and physical parameter sweeps.

## Limitations

The 3D render is a visualization of the 2D simulator, **not 3D MuJoCo dynamics**. The current brushless model, suction model, battery and tyre values are exploratory and intentionally not pitched as accurate engineering predictions. Maze exploration and RL are not implemented. Controller process isolation is not an OS security sandbox.

**Replay timing note:** physics snapshots are taken every 20 ms of simulation time (50 Hz); displayed ToF readings are the most recent input to the 200 Hz controller, so their own `timestamp_s` can be up to 5 ms earlier. Continuous run pacing can lag wall-clock time on a busy PC.
