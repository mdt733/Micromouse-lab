"""Deterministic planar micromouse physics prototype.

Not a calibrated tyre or fan model. Kept behind a stable sensor/action interface
so that MuJoCo can replace it without changing the UI or controller code.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, asdict
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "course": "straight", "seed": 735,
    "mass_g": 40.0, "track_mm": 68.0, "wheel_radius_mm": 12.0,
    "grip": 0.95, "tire_stiffness": 180.0,
    "motor_type": "brushed", "motor_kv": 4500.0,
    "motor_resistance_ohm": 3.0, "motor_current_limit_a": 1.2,
    "gear_ratio": 8.0, "motor_efficiency": 0.78,
    "battery_v": 4.1, "battery_internal_ohm": 0.18,
    "fan_force_n": 0.7, "fan_time_constant_s": 0.15, "fan_max_w": 5.0,
    "sensor_noise_mm": 1.2, "sensor_range_mm": 800.0,
    "duration_s": 20.0,
}
LIMITS: dict[str, tuple[float,float]] = {
    "mass_g":(15,150), "track_mm":(35,120), "wheel_radius_mm":(5,30),
    "grip":(.1,2.0), "tire_stiffness":(20,1000),
    "motor_kv":(500,20000), "motor_resistance_ohm":(.1,30),
    "motor_current_limit_a":(.1,10), "gear_ratio":(1,25),
    "motor_efficiency":(.3,1), "battery_v":(2,8.4),
    "battery_internal_ohm":(0,.9), "fan_force_n":(0,5),
    "fan_time_constant_s":(.01,2), "fan_max_w":(0,30),
    "sensor_noise_mm":(0,30), "sensor_range_mm":(80,1500),
    "duration_s":(1,600), "seed":(0,1_000_000)
}

def validate_config(values: dict[str,Any]) -> dict[str,Any]:
    result = dict(DEFAULT_CONFIG)
    for key, value in values.items():
        if key not in result: raise ValueError(f"Unknown parameter: {key}")
        if key == "course":
            if value not in COURSES: raise ValueError("Invalid course")
        elif key == "motor_type":
            if value not in ("brushed", "brushless", "ideal"): raise ValueError("Invalid motor type")
        elif key == "seed":
            if type(value) not in (int,float): raise ValueError("Invalid seed")
            value = int(value)
        else:
            if type(value) not in (int,float) or not math.isfinite(value): raise ValueError(f"Invalid {key}")
            value = float(value)
        if key in LIMITS and not LIMITS[key][0] <= value <= LIMITS[key][1]:
            raise ValueError(f"{key} outside range {LIMITS[key]}")
        result[key] = value
    return result

# (center x, center y, x half-size, y half-size), metres.
# All walls are derived from these rectangles for both contact and raycasting.
def wall(cx:float,cy:float,length:float,width:float) -> tuple[float,float,float,float]:
    return (cx,cy,length/2,width/2)

def make_demo_maze():
    """Deterministic 6x6 competition-style maze: connected passages and dead ends.

    True maze edges are used only to construct the physical walls and renderer.
    They are never included in a controller sensor packet.
    """
    n, cell = 6, .18
    rng = random.Random(140)
    direction = ((0, 1), (1, 0), (0, -1), (-1, 0))  # N, E, S, W
    opposite = (2, 3, 0, 1)
    masks = [[15 for _ in range(n)] for _ in range(n)]
    seen = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        x, y = stack[-1]
        options = []
        for d, (dx, dy) in enumerate(direction):
            xy = (x + dx, y + dy)
            if 0 <= xy[0] < n and 0 <= xy[1] < n and xy not in seen:
                options.append((d, xy))
        if not options:
            stack.pop()
            continue
        d, (nx, ny) = rng.choice(options)
        masks[y][x] &= ~(1 << d)
        masks[ny][nx] &= ~(1 << opposite[d])
        seen.add((nx, ny))
        stack.append((nx, ny))
    # Open a few additional internal walls to create loops rather than a pure tree.
    choices = []
    for y in range(n):
        for x in range(n):
            for d in (0, 1):
                dx, dy = direction[d]
                nx, ny = x + dx, y + dy
                if nx < n and ny < n and masks[y][x] & (1 << d):
                    choices.append((x, y, d, nx, ny))
    rng.shuffle(choices)
    for x, y, d, nx, ny in choices[:5]:
        masks[y][x] &= ~(1 << d)
        masks[ny][nx] &= ~(1 << opposite[d])
    offset = -n * cell / 2
    walls = []
    for y in range(n):
        for x in range(n):
            cx = offset + (x + .5) * cell
            cy = offset + (y + .5) * cell
            if masks[y][x] & 1:  # N
                walls.append(wall(cx, offset + (y + 1) * cell, cell + .012, .012))
            if masks[y][x] & 2:  # E
                walls.append(wall(offset + (x + 1) * cell, cy, .012, cell + .012))
            if x == 0 and masks[y][x] & 8:  # W boundary
                walls.append(wall(offset, cy, .012, cell + .012))
            if y == 0 and masks[y][x] & 4:  # S boundary
                walls.append(wall(cx, offset, cell + .012, .012))
    return {
        'title': 'Demo maze · 6×6',
        'start': (offset + .5 * cell, offset + .5 * cell, 0.),
        'route': [],  # No true solution path is shown as a driving guide.
        'walls': walls,
        'maze': {'width': n, 'height': n, 'cell_m': cell, 'origin': (offset, offset),
                 'goal_cells': [(2, 2), (2, 3), (3, 2), (3, 3)]},
    }

COURSES:dict[str,dict[str,Any]] = {
    "straight":{
        "title":"Straight sprint", "start":(-.67,0,0),
        "route":[[-.67,0],[.73,0]],
        "walls":[wall(0,-.14,1.95,.025),wall(0,.14,1.95,.025),wall(-.99,0,.025,.3),wall(.99,0,.025,.3)]
    },
    "corner":{
        "title":"90° left bend", "start":(-.66,0,0),
        "route":[[-.66,0],[-.10,0],[.14,0],[.29,.12],[.29,.7]],
        "walls":[wall(-.38,-.125,1.26,.025),wall(-.44,.125,1.13,.025),
                 wall(.17,.49,.025,.74),wall(.43,.365,.025,1.0),
                 wall(.30,.86,.26,.025),wall(-1,0,.025,.28)]
    },
    "slalom":{
        "title":"Slalom course", "start":(-.76,0,0),
        "route":[[-.76,0],[-.48,.18],[-.18,-.17],[.15,.18],[.53,-.17],[.8,0]],
        "walls":[wall(0,-.38,2.04,.025),wall(0,.38,2.04,.025),
                 wall(-1,0,.025,.78),wall(1,0,.025,.78),
                 wall(-.37,-.12,.05,.27),wall(.06,.13,.05,.27),wall(.47,-.12,.05,.27)]
    }
}

COURSES["maze_demo"] = make_demo_maze()

# Historic classic competition layouts: source .maze files are stored in mazes/.
from .competition import load_competition_courses
COURSES.update(load_competition_courses())

SENSOR_ANGLES = {"front":0, "front_left":math.pi/4, "left":math.pi/2,
                 "front_right":-math.pi/4, "right":-math.pi/2}

def clamp(x:float,a:float,b:float)->float: return max(a,min(b,x))

def ray_box(x:float,y:float,dx:float,dy:float, rect:tuple[float,float,float,float], maximum:float) -> float:
    cx,cy,hx,hy=rect
    lo,hi=0.,maximum
    for origin,direction,a,b in ((x,dx,cx-hx,cx+hx),(y,dy,cy-hy,cy+hy)):
        if abs(direction)<1e-10:
            if origin<a or origin>b: return maximum
        else:
            t1,t2=(a-origin)/direction,(b-origin)/direction
            lo,hi=max(lo,min(t1,t2)),min(hi,max(t1,t2))
            if hi<lo: return maximum
    return lo if hi>=0 else maximum

@dataclass
class State:
    x:float=0
    y:float=0
    yaw:float=0
    vx:float=0
    vy:float=0
    yaw_rate:float=0
    wheel_l:float=0
    wheel_r:float=0
    encoder_l:float=0
    encoder_r:float=0
    fan:float=0
    charge_ah:float=0
    t:float=0
    distance_m:float=0
    collisions:int=0
    energy_j:float=0

class PlanarPhysics:
    """2D dynamics: force-saturated tyre slips, DC motor back EMF, battery sag, fan lag."""
    DT = .001
    def __init__(self, config:dict[str,Any]):
        self.config=validate_config(config)
        self.course=COURSES[self.config['course']]
        self.walls=self.course['walls']
        self.rng=random.Random(self.config['seed'])
        self.reset()

    def reset(self):
        x,y,yaw=self.course['start']
        self.s=State(x=x,y=y,yaw=yaw)
        self.cmd={'left_motor':0.,'right_motor':0.,'fan':0.}
        self.motor_current=[0.,0.]
        self.voltage=self.config['battery_v']
        self.grip_use=0.
        self.accel=0.
        self.accel_forward=0.
        self.accel_lateral=0.
        self._last_impact_t=-999.
        self.last_tof={k:None for k in SENSOR_ANGLES}
        self.sample_sensors()

    def set_command(self, command:dict[str,float]):
        for key in self.cmd:
            value=float(command.get(key,0.))
            self.cmd[key]=clamp(value, 0 if key=='fan' else -1.,1.) if math.isfinite(value) else 0.

    def sample_sensors(self)->dict[str,Any]:
        c=self.config;s=self.s
        max_range=c['sensor_range_mm']/1000.
        values={}
        for key,offset in SENSOR_ANGLES.items():
            a=s.yaw+offset
            # Placing rays just ahead of the centre improves meaningful near-wall readings.
            ox=s.x+.018*math.cos(s.yaw);oy=s.y+.018*math.sin(s.yaw)
            distance=min((ray_box(ox,oy,math.cos(a),math.sin(a),r,max_range) for r in self.walls),default=max_range)
            if distance>=max_range or self.rng.random()<.003:
                values[key]=None
            else:
                values[key]=round(max(0.,distance*1000+self.rng.gauss(0,c['sensor_noise_mm'])),1)
        self.last_tof=values
        ticks_per_rev=360
        return {"tof_mm":values,"encoder_ticks":(round(s.encoder_l*ticks_per_rev/(2*math.pi)),round(s.encoder_r*ticks_per_rev/(2*math.pi))),
                "gyro_z_rad_s":s.yaw_rate+self.rng.gauss(0,.01),"battery_v":round(self.voltage,3),
                "timestamp_s":round(s.t,6)}

    def step(self):
        c=self.config;s=self.s;dt=self.DT;m=c['mass_g']/1000
        r=c['wheel_radius_mm']/1000;half_track=c['track_mm']/2000
        fan_tgt=self.cmd['fan']
        s.fan+=(fan_tgt-s.fan)*clamp(dt/c['fan_time_constant_s'],0,1)
        # Suction applied normally to the floor. Constant-force approximation with first order fan lag.
        normal=m*9.81+c['fan_force_n']*s.fan
        grip_per_wheel=c['grip']*normal/2
        km=60/(2*math.pi*c['motor_kv']) # SI Kt=Ke for an ideal permanent magnet motor
        gear=c['gear_ratio']
        wheel_omegas=[s.wheel_l,s.wheel_r]
        inputs=[self.cmd['left_motor'],self.cmd['right_motor']]
        # Solve coarse voltage droop using previous current estimates; bounded one-step feedback.
        total_abs_current=sum(abs(i) for i in self.motor_current)
        self.voltage=max(1.0,c['battery_v']-c['battery_internal_ohm']*(total_abs_current + s.fan*c['fan_max_w']/max(c['battery_v'],1)))
        torque=[];new_current=[]
        for u,omega in zip(inputs,wheel_omegas):
            if c['motor_type']=='ideal':
                tau=.007*u; current=0.
            else:
                motor_speed=omega*gear
                terminal=u*self.voltage
                current=clamp((terminal-km*motor_speed)/c['motor_resistance_ohm'],
                              -c['motor_current_limit_a'],c['motor_current_limit_a'])
                drive=1.0 if c['motor_type']=='brushed' else (0.72+0.28*math.tanh(abs(motor_speed)/15.))
                tau=km*current*gear*c['motor_efficiency']*drive
            torque.append(tau);new_current.append(current)
        self.motor_current=new_current
        heading=math.cos(s.yaw),math.sin(s.yaw)
        forward=s.vx*heading[0]+s.vy*heading[1]
        sideways=-s.vx*heading[1]+s.vy*heading[0]
        forces=[];moment=0.;util=0.;wheel_new=[]
        wheel_inertia=max(1.2e-6, .5*(m*.1)*r*r + (m*.1)*(r*r)*.06)
        for idx,(omega,drive_tau) in enumerate(zip(wheel_omegas,torque)):
            lateral_pos=half_track if idx==0 else -half_track
            surface_v=forward-s.yaw_rate*lateral_pos
            # Stiffness is experimental, in N per (m/s) of slip velocity.
            fx=c['tire_stiffness']*(omega*r-surface_v)
            fy=-c['tire_stiffness']*.55*sideways
            magnitude=math.hypot(fx,fy)
            if magnitude>grip_per_wheel:
                scale=grip_per_wheel/max(magnitude,1e-8)
                fx*=scale;fy*=scale
            util=max(util,math.hypot(fx,fy)/max(grip_per_wheel,1e-9))
            forces.append((fx,fy));moment-=lateral_pos*fx
            # Wheel angular acceleration with wheel inertia and viscous bearing drag.
            next_omega=omega+((drive_tau-fx*r-0.000002*omega)/max(wheel_inertia,1e-8))*dt
            wheel_new.append(clamp(next_omega,-2000,2000))
        fx=sum(f[0] for f in forces);fy=sum(f[1] for f in forces)
        drag_forward=0.06*forward*abs(forward)+.015*forward
        drag_side=.004*sideways
        fx-=drag_forward;fy-=drag_side
        # Chassis dimensions affect yaw inertia roughly as a short rectangular plate.
        length=.072
        inertia=m*(length*length+(2*half_track)**2)/12
        yaw_alpha=(moment-.00022*s.yaw_rate)/max(inertia,1e-7)
        ax=(fx*heading[0]-fy*heading[1])/m
        ay=(fx*heading[1]+fy*heading[0])/m
        s.vx+=ax*dt;s.vy+=ay*dt
        s.yaw_rate=clamp(s.yaw_rate+yaw_alpha*dt,-55,55)
        s.yaw=(s.yaw+s.yaw_rate*dt+math.pi)%(2*math.pi)-math.pi
        oldx,oldy=s.x,s.y
        s.x+=s.vx*dt;s.y+=s.vy*dt
        s.wheel_l,s.wheel_r=wheel_new
        s.encoder_l+=wheel_new[0]*dt;s.encoder_r+=wheel_new[1]*dt
        self._resolve_collisions()
        s.t+=dt;s.distance_m+=math.hypot(s.x-oldx,s.y-oldy)
        amps=sum(abs(i) for i in new_current)
        fan_w=c['fan_max_w']*s.fan**2
        power=self.voltage*amps+fan_w
        s.energy_j+=power*dt;s.charge_ah+=(amps+fan_w/max(self.voltage,1))/3600*dt
        self.grip_use=util
        self.accel=math.hypot(ax,ay)
        self.accel_forward=ax*heading[0]+ay*heading[1]
        self.accel_lateral=-ax*heading[1]+ay*heading[0]

    def _resolve_collisions(self):
        s=self.s
        # Conservative circular hull; deliberately approximates contact geometry.
        hull=math.hypot(.036,self.config['track_mm']/2000)
        for cx,cy,hx,hy in self.walls:
            nearest_x=clamp(s.x,cx-hx,cx+hx)
            nearest_y=clamp(s.y,cy-hy,cy+hy)
            dx=s.x-nearest_x;dy=s.y-nearest_y
            dist=math.hypot(dx,dy)
            if dist<hull:
                if dist<1e-9:
                    dx,dy=s.x-cx,s.y-cy
                    if abs(dx)/max(hx,1e-7)>abs(dy)/max(hy,1e-7):nx,ny=(1 if dx>=0 else -1),0
                    else:nx,ny=0,(1 if dy>=0 else -1)
                else:nx,ny=dx/dist,dy/dist
                s.x+=nx*(hull-dist);s.y+=ny*(hull-dist)
                vn=s.vx*nx+s.vy*ny
                if vn<0:
                    s.vx-=1.05*vn*nx;s.vy-=1.05*vn*ny
                s.yaw_rate*=.88
                if vn < -.05 and s.t-self._last_impact_t>.12:
                    s.collisions+=1
                    self._last_impact_t=s.t

    def snapshot(self)->dict[str,Any]:
        c=self.config;s=self.s
        forward=s.vx*math.cos(s.yaw)+s.vy*math.sin(s.yaw)
        return {"t":round(s.t,4),"x":s.x,"y":s.y,"yaw":s.yaw,"vx":s.vx,"vy":s.vy,
                "speed":math.hypot(s.vx,s.vy),"forward_speed":forward,"yaw_rate":s.yaw_rate,
                "fan_actual":s.fan,"fan_force_n":s.fan*c['fan_force_n'],
                "battery_v":self.voltage,"current_a":self.motor_current,
                "grip_use":self.grip_use,"accel_ms2":self.accel,
                "accel_forward_ms2":self.accel_forward,"accel_lateral_ms2":self.accel_lateral,
                "normal_force_n":(c["mass_g"]/1000*9.81+c["fan_force_n"]*s.fan),"energy_j":s.energy_j,
                "collisions":s.collisions,"distance_m":s.distance_m,
                "tof_mm":self.last_tof,"commands":dict(self.cmd)}

    def scene(self):
        return {"walls":self.walls,"course":self.config['course'],"route":self.course['route'],
                "start":self.course['start'],"title":self.course['title'],
                "maze":self.course.get('maze'),
                "robot":{"track_m":self.config['track_mm']/1000,"wheel_radius_m":self.config['wheel_radius_mm']/1000}}
