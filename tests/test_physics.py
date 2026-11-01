import math
from backend.physics import PlanarPhysics,DEFAULT_CONFIG,validate_config

def test_initial_sensors_and_motion():
    m=PlanarPhysics(DEFAULT_CONFIG)
    s=m.sample_sensors()
    assert 100<s['tof_mm']['left']<200
    assert 100<s['tof_mm']['right']<200
    m.set_command({'left_motor':.4,'right_motor':.4,'fan':.5})
    for _ in range(400):m.step()
    assert m.s.x>-.67, (m.s.x,m.s.vx)
    assert math.isfinite(m.s.energy_j)
    assert m.s.energy_j>0

def test_opposite_drive_rotates():
    m=PlanarPhysics(DEFAULT_CONFIG)
    m.set_command({'left_motor':-.3,'right_motor':.3,'fan':0})
    for _ in range(250):m.step()
    assert abs(m.s.yaw)>.05

def test_config_validates():
    try:validate_config({'mass_g':-50})
    except ValueError:pass
    else:assert False

def test_same_seed_same_measurement():
    a=PlanarPhysics(DEFAULT_CONFIG)
    b=PlanarPhysics(DEFAULT_CONFIG)
    assert a.sample_sensors()==b.sample_sensors()
