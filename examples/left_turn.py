"""Simple sensor-triggered 90° left turn, using only ToF and gyro.

Try the '90° left bend' course with this controller.
No perfect position or simulator yaw is exposed to the controller.
"""
import math

class Controller:
    def __init__(self):
        self.mode = 'approach'
        self.yaw_in_turn = 0.0
        self.last_log = -1.0

    def step(self, s, dt):
        front = s.tof_mm['front']
        if self.mode == 'approach' and front is not None and front < 190:
            self.mode = 'turn'
            self.yaw_in_turn = 0.0
            print('Obstacle ahead — initiating measured left turn')

        if self.mode == 'turn':
            # Integrating gyro, not using the true pose.
            self.yaw_in_turn += s.gyro_z_rad_s * dt
            error = math.pi/2 - self.yaw_in_turn
            if abs(error) < 0.10 and abs(s.gyro_z_rad_s) < 1.0:
                self.mode = 'exit'
                print('Turn complete. Accelerating out.')
            else:
                # Gentle differential pivot with damping near the target.
                steer = max(-.10, min(.10, .35*error - .14*s.gyro_z_rad_s))
                return Outputs(left_motor=-steer, right_motor=steer, fan=.9)

        # Drive forwards with an exploratory slow-down when facing a wall.
        forward=.42 if self.mode=='approach' else .38
        if front is not None:
            if front < 80:forward=0
            elif front < 240:forward*=max(0.,min(1.,(front-80)/160))
        if s.timestamp_s-self.last_log>=.7:
            print(f't={s.timestamp_s:.2f} mode={self.mode} front={front}mm')
            self.last_log=s.timestamp_s
        return Outputs(forward,forward,.9)
