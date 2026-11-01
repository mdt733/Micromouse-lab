"""Structural checks for historical competition layouts and their API presets."""

import pytest
from backend.competition import SOURCES, parse_maze, reachable, load_competition_courses
from backend.physics import COURSES, PlanarPhysics, DEFAULT_CONFIG


def test_historic_files_have_walls_and_connected_goals():
    courses = load_competition_courses()
    assert len(courses) == 4
    for key, course in courses.items():
        maze = course['maze']
        assert maze['width'] == maze['height'] == 16
        assert not course['route']  # Never leak ground-truth solution to the robot
        assert len(course['walls']) > 30
        assert len(maze['goal_cells']) == 4
        assert key in COURSES
        assert maze['source_url'].endswith('.maze')
        masks=parse_maze((__import__('pathlib').Path(__file__).parent.parent/'mazes'/SOURCES[key][0]).read_text())
        assert reachable(masks, set(map(tuple, maze['goal_cells'])))
        engine=PlanarPhysics({**DEFAULT_CONFIG,'course':key})
        data=engine.sample_sensors()
        assert 'maze' not in data and 'x' not in data
        assert engine.s.yaw > 1.5


def test_bad_maze_rejected():
    with pytest.raises(ValueError):
        parse_maze('not a maze')
    with pytest.raises(ValueError):
        parse_maze('+---+\n|   |\n+   +\n')  # Missing south wall


def test_competition_endpoint_presets():
    from fastapi.testclient import TestClient
    from backend.server import app
    with TestClient(app) as client:
        listing=client.get('/api/competition-mazes').json()
        assert len(listing)==4
        for key in SOURCES:
            response=client.get('/api/presets/competition/'+key.removeprefix('competition_'))
            assert response.status_code == 200
            config=response.json()['config']
            assert config['course']==key
            assert config['duration_s'] == 300
            assert 'SIZE = 16' in response.json()['controller']
        assert client.get('/api/presets/competition/unknown').status_code==404


def test_speed_setting_and_sensor_only_first_move():
    from fastapi.testclient import TestClient
    from backend.server import app
    from backend.controller_worker import Sensors
    from examples.classic_competition_solver import Controller
    with TestClient(app) as client:
        assert client.post('/api/speed',json={'factor':4}).json()['speed_factor'] == 4
        assert client.get('/api/status').json()['speed_factor'] == 4
        assert client.post('/api/speed',json={'factor':99}).status_code == 400
        # Restore global singleton setting so other tests are unaffected.
        client.post('/api/speed',json={'factor':1})
    solver = Controller()
    sim = PlanarPhysics({**DEFAULT_CONFIG,'course':'competition_apec_2018'})
    output = None
    for tick in range(12000):
        if tick % 5 == 0:
            output=solver.step(Sensors(**sim.sample_sensors()),.005)
            sim.set_command(output)
        sim.step()
    assert solver.moves >= 6
    assert sim.s.collisions <= 1
    assert len(solver.visited)==16
    assert solver.cell[0]==0
