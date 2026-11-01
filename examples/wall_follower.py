"""Editable virtual micromouse controller.

Inputs are deliberately limited to sensor measurements, not true position or yaw.
Outputs are normalized driver requests, NOT magical forces or wheel velocities.
"""

class Controller:
    def __init__(self):
        self.integral = 0.0
        self.last_log = -1.0

    def step(self, s, dt):
        left = s.tof_mm.get("left")
        right = s.tof_mm.get("right")
        front = s.tof_mm.get("front")

        # Stay roughly centered between corridor walls using raw ToF.
        error = 0 if left is None or right is None else (left-right)
        self.integral = max(-150, min(150, self.integral + error * dt))
        steering = max(-0.15, min(0.15, 0.0012 * error + 0.00015 * self.integral))

        # Stop before the end wall. See examples/ for more advanced routing later.
        throttle = 0.48
        if front is not None:
            if front < 85:
                throttle = 0.0
            elif front < 250:
                throttle *= (front-85)/165

        if s.timestamp_s - self.last_log > 0.75:
            print(f"t={s.timestamp_s:5.2f}s  front={front}mm  steering={steering:+.3f}")
            self.last_log = s.timestamp_s

        return Outputs(left_motor=throttle-steering,
                       right_motor=throttle+steering,
                       fan=0.75)
