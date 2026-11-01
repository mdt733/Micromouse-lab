"""Regression checks: real maze geometry, sensor-only map, and autonomous solve."""
import math

from backend.physics import COURSES, DEFAULT_CONFIG, PlanarPhysics, ray_box
from backend.controller_worker import Sensors
from examples.maze_solver import Controller


def test_maze_has_walled_boundaries_and_reachable_centre():
    scene = COURSES['maze_demo']
    assert scene['maze']['width'] == scene['maze']['height'] == 6
    assert not scene['route']  # Do not show a perfect solution guide.
    assert len(scene['walls']) >= 35
    engine = PlanarPhysics({**DEFAULT_CONFIG, 'course': 'maze_demo', 'sensor_noise_mm': 0})
    # Starting cell is physically bounded below and left; robot knows only rays.
    boundary = min(ray_box(-.45, -.45, 0, -1, wall, .8) for wall in engine.walls)
    assert .075 < boundary < .095
    readings = engine.sample_sensors()
    assert 'x' not in readings and 'maze' not in readings
    assert 'tof_mm' in readings


def test_floodfill_reaches_centre_with_noisy_sensors():
    for seed in (735, 25, 101, 333):
        engine = PlanarPhysics({**DEFAULT_CONFIG, 'course': 'maze_demo',
                                'seed': seed, 'duration_s': 60})
        solver = Controller()
        assert not any(v for row in solver.visited for v in row)
        outcome = None
        for tick in range(60000):
            if tick % 5 == 0:
                out = solver.step(Sensors(**engine.sample_sensors()), .005)
                engine.set_command(out)
                if out['done']:
                    outcome = out
                    break
            engine.step()
        assert outcome is not None, f'No solution with seed {seed}'
        assert outcome['reason'] == 'Centre goal reached'
        assert solver.cell in {(2,2), (2,3), (3,2), (3,3)}
        assert solver.moves >= 10  # Includes exploration and a wrong turn.
        assert sum(v > 0 for row in solver.visited for v in row) >= 10
        x0 = -.54 + (solver.cell[0]+.5)*.18
        y0 = -.54 + (solver.cell[1]+.5)*.18
        assert math.hypot(engine.s.x-x0, engine.s.y-y0) < .065
        assert engine.s.collisions <= 3


def test_web_controller_worker_streams_discovered_map(tmp_path, monkeypatch):
    """Run the actual subprocess controller through the HTTP/recording contract."""
    import time
    from fastapi.testclient import TestClient
    import backend.server as web

    preset_code = (web.EXAMPLES / 'maze_solver.py').read_text(encoding='utf-8')
    temporary_controller = tmp_path / 'controller.py'
    temporary_controller.write_text(preset_code, encoding='utf-8')
    monkeypatch.setattr(web, 'CODE_PATH', temporary_controller)
    with TestClient(web.app) as client:
        preset = client.get('/api/presets/maze_demo').json()
        assert preset['config']['course'] == 'maze_demo'
        assert 'class Controller' in preset['controller']
        applied = client.post('/api/config', json={'config': preset['config']})
        assert applied.status_code == 200
        started = client.post('/api/action', json={'action': 'run'})
        assert started.status_code == 200, started.text
        deadline = time.monotonic() + 4
        status = None
        while time.monotonic() < deadline:
            status = client.get('/api/status').json()
            if status.get('debug', {}).get('visited'):
                break
            time.sleep(.06)
        assert status is not None and status['state']['t'] > 0
        assert status['debug']['visited'][0][0] >= 1
        client.post('/api/action', json={'action': 'pause'})
        replay = client.get('/api/replay').json()
        assert any(frame.get('debug') and frame['debug']['visited'][0][0] for frame in replay['frames'])
