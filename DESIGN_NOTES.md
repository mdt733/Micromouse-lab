# Engineering notebook — MicroMouse Lab

## Principles worth preserving

1. **Physics is authoritative; the browser is a viewer.** Controller output changes driver commands; it never changes pose directly. Viewer positions/guide routes are never injected into onboard observations.
2. **Keep a hardware-independent controller interface.** A mouse policy sees timestamped ToF distances, encoders, IMU and optional pack data; it emits normalized motor and fan commands.
3. **Two fidelity levels, one task protocol.** A fast planar dynamics model for exploration/optimisation, later a high-fidelity MuJoCo model for testing body contact, skid/roll and fan effects. Don't mix their measured results without labelling fidelity.
4. **Run the physics on simulation time**, at a fixed integration step, with separate controller and viewer rates. Code changes reset the controller process so an experiment is reproducible.
5. **Make imperfections explicit.** Motor torque limits, gear losses, battery voltage sag, sensor latency/noise, tyre slip, suction response, and energy should have measured or defensible models before making design claims.
6. **Experiments are first-class outputs.** Save the code, robot settings, course geometry, seed and a compact telemetry trace for every benchmark. Compare improvements via consistent course/seed/budget, not just a race time.
7. **Controller code is trusted local Python, not sandboxed user content.** Protect the simulator from accidental hangs with a worker and watchdog; stronger OS isolation is a separate security project.

## Physics equations / concepts

- Motor circuit first approximation: `I = clamp((u·V_batt - K_e·ω_motor)/R, -I_max,+I_max)`; `τ_wheel = K_t I · G · η`.
- Longitudinal slip: `F_x = clamp(k_x (r ω - v_contact), ±F_traction)`.
- Combined longitudinal/lateral tyre load: `sqrt(F_x²+F_y²) <= μ·N` per wheel. v0.1 splits load equally and has no suspension/load transfer.
- Suction: `N = mg + F_fan` for the flat 2D approximation, with first-order response. Real fan force depends on pressure/airflow and body/ground geometry; this approximation is intentionally simplistic.
- Available corner acceleration upper bound on ideal flat plane: `a_y <= μ(g+F_fan/m)`; this is a traction budget, not a guarantee of achievable acceleration.
- All test cases should record measured acceleration, wheel slip, yaw error, controller update budget, battery sag, energy and wall contacts.

## Next technical milestone: MuJoCo parity

Build `MujocoPhysics` with the *same* `reset`, `step`, `set_command`, `sample_sensors`, `snapshot`, `scene` contract as `PlanarPhysics`:

- `freejoint` chassis with explicit mass/inertia and two hinged wheel bodies; actuator commands are physical torques obtained from the chosen motor model.
- Wheel/floor, wheel/wall and chassis/wall geometries with declared contact parameters, not assumed no-slip.
- Apply normal suction to a chassis body with `mjData.xfrc_applied` before `mj_step`; use fan rise/fall dynamics. Add skirt gap/leakage only after there is a measured or validated response curve.
- Account for pitch/roll, wheel load, cornering load transfer and tyre compliance where available; keep the planar model as a unit-test and speed-optimisation baseline.
- Render actual rigid-body world positions at browser frame rate; keep controller blind to the true state.
- Compare straight-line acceleration, spin-in-place, turning radius and wall contact against this planar model, and log discrepancies instead of quietly tuning to match.

## Experiment sequence

**A. Minimum verifiable mechanics:** straight-line voltage/torque-speed, coast-down, braking distance, constant-radius turning; no fan. Then repeat with suction and with battery droop.

**B. Control quality:** PID wall follower, gyro-based corner turn, pose estimate via encoders/IMU, trapezoidal speed planning; quantify error, corner time and safety margin.

**C. Maze racing:** true cell grid, explored/unknown walls, flood fill, route smoothing, physically admissible curvature and jerk profile, fastest feasible second run.

**D. Optimisation:** batch runs across gear ratio, wheel radius, fan suction and controller gains, score time/energy/collisions/robustness. Domain randomisation before policy learning.

## Status (v0.1)

- [x] Local FastAPI server, WebSocket state, editable Python code worker
- [x] Parametric 2D physics with approximate motors, contact, battery, fan and ToF
- [x] Browser garage, code editor fallback, 3D-renderer implementation/fallback, console and graph
- [x] Straight, corner and slalom maps; simple example controllers
- [x] Config persistence and trace export
- [ ] MuJoCo backend and actual 3D chassis/wheel dynamics
- [ ] Calibration/validation against physical measurements
- [ ] Maze exploration, mapping and fastest-path planning
- [ ] Saved benchmark runner and ghost replay
- [ ] ESC-specific motor behavior and measured fan curve
- [ ] Device-code/HIL compatibility layer


## v0.2 handover: run reliability, replay, Git (2026-11-01)

- `backend/server.py`: physics runs in `micromouse-physics` thread, broadcaster now only sends snapshots. All mutations are behind `SimService.lock`; `/api/status` can be polled without a WebSocket. Every 20 ms tick stores `{state,sensors}` in `trace`, starting at t=0. `GET /api/replay` returns in-memory recording. Export is `micromouse-lab-run-v2`. Reset increments `run_id` and clears the recording and logs. Duration limit marks `complete=True`.
- `backend/physics.py`: stores acceleration magnitude and body-forward/body-lateral accelerations and total normal force in snapshots. These derive from the simplified planar dynamics, not a calibrated measurement.
- `web/app.js`: flight-recorder slider enters replay and pauses backend, replays recorded frames and filters console by time. Latest returns to active view. In-browser graph plots speed/grip/acceleration. HTTP fallback polling updates the viewer if WebSockets fail.
- `web/viewport.js`: replay trail is rebuilt to the selected time, so scrubbing backward hides future trajectory.
- `backend/controller_worker.py`: timeout raised from .12 s to .5 s to tolerate Windows scheduling spikes; still not a sandbox.
- `upload-to-github.bat`: local GitHub CLI auth/status check and browser sign-in, Git identity, safe repository creation, explicit choice of privacy and push confirmation, no force-push. Does not actually upload until invoked on user's computer.
- **Validation:** `python -m pytest -q`: 5 tests, including unattended continuous Run through configured time limit, export/replay and reset consistency. `node --check web/app.js` validates JS syntax. A real browser end-to-end check was attempted but Chromium navigation to local web servers is restricted in this build environment. Windows batch script was reviewed but cannot be executed on Windows in this environment.
- **Next:** MuJoCo contact and suction model with validation benchmarks, then real wheel-load effects, better sensor models, optimised steering and maze exploration. Stay on feature branches once remote exists; don't publish runtime secrets or overwrite a user's edited controller during upgrades.
