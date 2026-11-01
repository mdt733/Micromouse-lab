"""Sensor-only flood-fill micromouse exploration demo.

Use with the `Demo maze · 6×6` track and the default 12 mm wheel radius.
The controller receives no maze layout, perfect pose, or simulator map.
It discovers walls using FRONT/LEFT/RIGHT ToF at cell centres, derives
heading from the gyro, and moves one maze cell using wheel encoders.

The algorithm assumes the usual micromouse starting facts: 180 mm square
cells, start at cell (0,0), facing east, and the centre 2×2 is the goal.
Motion is deliberately stop-turn-go: this is a baseline solver, not racing MPC.
"""
import math
from collections import deque

SIZE = 6
CELL_M = 0.18
WHEEL_RADIUS_M = 0.012  # Must match Garage wheel radius, currently 12 mm.
TICKS_PER_REV = 360
GOALS = {(2, 2), (2, 3), (3, 2), (3, 3)}
# 0=N, 1=E, 2=S, 3=W. Positive yaw is counterclockwise.
DIRS = ((0, 1), (1, 0), (0, -1), (-1, 0))
ANGLES = (math.pi/2, 0.0, -math.pi/2, math.pi)
OPPOSITE = (2, 3, 0, 1)


def wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def clip(value, low, high):
    return max(low, min(high, value))


class Controller:
    def __init__(self):
        self.cell = (0, 0)
        self.heading = 0.0  # Initial east alignment is a starting condition, not ground truth.
        self.last_enc = None
        self.wheel_velocity = 0.0
        self.walls = [[0] * SIZE for _ in range(SIZE)]  # Confirmed blocked direction bits.
        self.open = [[0] * SIZE for _ in range(SIZE)]   # Confirmed traversable direction bits.
        self.visited = [[0] * SIZE for _ in range(SIZE)]
        self.phase = 'sense'
        self.target_dir = 1
        self.target_cell = None
        self.moved_m = 0.0
        self.settle_s = 0.0
        self.last_message = -1.0
        self.moves = 0
        self.map_version = 0
        self.sense_samples = []

    def neighbor(self, x, y, direction):
        dx, dy = DIRS[direction]
        nx, ny = x + dx, y + dy
        if 0 <= nx < SIZE and 0 <= ny < SIZE:
            return nx, ny
        return None

    def mark_edge(self, x, y, direction, blocked):
        bit = 1 << direction
        before = (self.walls[y][x], self.open[y][x])
        if blocked:
            self.walls[y][x] |= bit
            self.open[y][x] &= ~bit
        else:
            self.open[y][x] |= bit
            self.walls[y][x] &= ~bit
        nb = self.neighbor(x, y, direction)
        if nb is not None:
            nx, ny = nb
            opposite_bit = 1 << OPPOSITE[direction]
            if blocked:
                self.walls[ny][nx] |= opposite_bit
                self.open[ny][nx] &= ~opposite_bit
            else:
                self.open[ny][nx] |= opposite_bit
                self.walls[ny][nx] &= ~opposite_bit
        if before != (self.walls[y][x], self.open[y][x]):
            self.map_version += 1

    def observe_cell(self, readings):
        x, y = self.cell
        self.visited[y][x] += 1
        direction = min(range(4), key=lambda d: abs(wrap(self.heading - ANGLES[d])))
        for angle, name in ((0, 'front'), (1, 'left'), (-1, 'right')):
            d = (direction - angle) % 4  # N=0,E=1,S=2,W=3, CCW is minus.
            reading = readings.get(name)
            # Sensor rays begin 18mm ahead of the chassis centre.
            # At a cell centre: nearby wall ~70-90mm; next wall >=250mm.
            self.mark_edge(x, y, d, reading is not None and reading < 150.0)
        for d in range(4):
            if self.neighbor(x, y, d) is None:
                self.mark_edge(x, y, d, True)

    def distances(self):
        """Optimistic flood-fill: unknown edges are passable until measured closed."""
        dist = [[1000] * SIZE for _ in range(SIZE)]
        q = deque()
        for x, y in GOALS:
            dist[y][x] = 0
            q.append((x, y))
        while q:
            x, y = q.popleft()
            for d in range(4):
                if self.walls[y][x] & (1 << d):
                    continue
                nb = self.neighbor(x, y, d)
                if nb is None:
                    continue
                nx, ny = nb
                if dist[ny][nx] > dist[y][x] + 1:
                    dist[ny][nx] = dist[y][x] + 1
                    q.append(nb)
        return dist

    def choose_direction(self):
        x, y = self.cell
        dist = self.distances()
        options = []
        facing = min(range(4), key=lambda d: abs(wrap(self.heading - ANGLES[d])))
        for d in range(4):
            nb = self.neighbor(x, y, d)
            if nb is None or self.walls[y][x] & (1 << d):
                continue
            nx, ny = nb
            options.append((dist[ny][nx], self.visited[ny][nx],
                            abs(wrap(ANGLES[d] - ANGLES[facing])), d, nb))
        if not options:
            return None
        options.sort()
        return options[0][-2], options[0][-1]

    def debug(self):
        return {'mode': self.phase, 'cell': list(self.cell), 'heading_rad': self.heading,
                'target_cell': list(self.target_cell) if self.target_cell else None,
                'visited': self.visited, 'closed': self.walls, 'open': self.open,
                'distances': self.distances(), 'moves': self.moves,
                'goal_cells': [list(g) for g in sorted(GOALS)]}

    def action(self, left=0.0, right=0.0, finished=False, reason=None):
        return {'left_motor': clip(left, -1, 1), 'right_motor': clip(right, -1, 1),
                'fan': 0.85, 'done': finished, 'reason': reason, 'debug': self.debug()}

    def step(self, sensors, dt):
        if self.last_enc is None:
            self.last_enc = sensors.encoder_ticks
            print('MAZE: Starting cell (0,0), facing east; map initially unknown')
        dl = (sensors.encoder_ticks[0] - self.last_enc[0]) * (2*math.pi*WHEEL_RADIUS_M / TICKS_PER_REV)
        dr = (sensors.encoder_ticks[1] - self.last_enc[1]) * (2*math.pi*WHEEL_RADIUS_M / TICKS_PER_REV)
        self.last_enc = sensors.encoder_ticks
        ds = (dl + dr) / 2
        self.wheel_velocity = .75*self.wheel_velocity + .25*(ds / max(dt, .001))
        self.heading = wrap(self.heading + sensors.gyro_z_rad_s * dt)
        gyro = sensors.gyro_z_rad_s

        if self.phase == 'finished':
            return self.action(finished=True)

        if self.phase == 'sense':
            self.sense_samples.append(dict(sensors.tof_mm))
            if len(self.sense_samples) < 8:
                return self.action()
            readings = {}
            for key in ('front', 'left', 'right'):
                samples = [d[key] for d in self.sense_samples if d.get(key) is not None]
                # A single invalid reading must not erase a real wall.
                readings[key] = sorted(samples)[len(samples)//2] if samples else None
            self.sense_samples = []
            self.observe_cell(readings)
            if self.cell in GOALS:
                self.phase = 'finished'
                print(f'GOAL REACHED at {self.cell} after {self.moves} cells '
                      f'and {sensors.timestamp_s:.2f} simulated seconds!')
                return self.action(finished=True, reason='Centre goal reached')
            selection = self.choose_direction()
            if selection is None:
                print('No open exits. Exploration failed.')
                self.phase = 'finished'
                return self.action(finished=True, reason='No open exits')
            self.target_dir, self.target_cell = selection
            self.moved_m = 0.0
            self.settle_s = 0.0
            self.phase = 'rotate'
            print(f'Cell {self.cell} -> {self.target_cell} | '
                  f'known cells={sum(v>0 for row in self.visited for v in row)} | '
                  f'phase=turn')

        if self.phase == 'rotate':
            error = wrap(ANGLES[self.target_dir] - self.heading)
            if abs(error) < .055 and abs(gyro) < .45:
                self.phase = 'drive'
                self.moved_m = 0.0
            else:
                steer = clip(.55*error - .17*gyro, -.32, .32)
                return self.action(-steer, steer)

        if self.phase == 'drive':
            self.moved_m += ds
            remaining = CELL_M - self.moved_m
            error = wrap(ANGLES[self.target_dir] - self.heading)
            # Slow near cell centre. Reverse throttle is permitted for braking.
            speed_target = min(.30, math.sqrt(max(0., 2*.50*remaining)))
            longitudinal = clip(1.8*(speed_target - self.wheel_velocity), -.25, .40)
            steering = clip(.65*error - .12*gyro, -.13, .13)
            if abs(remaining) < .004 and abs(self.wheel_velocity) < .07:
                self.cell = self.target_cell
                self.moves += 1
                self.phase = 'settle'
                self.settle_s = 0.0
                return self.action()
            return self.action(longitudinal - steering, longitudinal + steering)

        if self.phase == 'settle':
            self.settle_s += dt
            if self.settle_s >= .08:
                self.phase = 'sense'
                self.sense_samples = []
            return self.action()

        return self.action()
