"""End-to-end local service contract, including continuous Run and flight recorder."""
import time
from fastapi.testclient import TestClient
from backend.physics import DEFAULT_CONFIG
from backend.server import app, service


def test_run_advances_without_browser_websocket_and_replays():
    with TestClient(app) as client:
        cfg = dict(DEFAULT_CONFIG, duration_s=1, seed=735)
        r = client.post('/api/config', json={'config': cfg})
        assert r.status_code == 200, r.text
        r = client.post('/api/action', json={'action': 'run'})
        assert r.status_code == 200, r.text
        assert r.json()['running']
        # The independent sim thread must advance without Step or an active WebSocket.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = client.get('/api/status').json()
            if state['complete']:
                break
            time.sleep(.05)
        assert state['complete'], state
        assert not state['running']
        assert .99 <= state['state']['t'] <= 1.001
        recorded = client.get('/api/replay').json()
        frames = recorded['frames']
        assert len(frames) >= 45
        assert frames[0]['state']['t'] == 0
        assert frames[-1]['state']['t'] >= .99
        assert all('accel_ms2' in f['state'] and 'grip_use' in f['state'] for f in frames)
        assert all('tof_mm' in f['sensors'] for f in frames)
        assert recorded['run_id'] == state['run_id']
        exported = client.get('/api/export').json()
        assert len(exported['trace']) == len(frames)
        reset = client.post('/api/action', json={'action':'reset'}).json()
        assert reset['trace_len'] == 1
        assert reset['run_id'] != recorded['run_id']
        assert not reset['complete']


def test_websocket_frames_remain_available_while_running():
    with TestClient(app) as client:
        client.post('/api/config', json={'config': dict(DEFAULT_CONFIG, duration_s=1)})
        with client.websocket_connect('/ws') as ws:
            initial = ws.receive_json()
            assert initial['type'] == 'status'
            r = client.post('/api/action', json={'action': 'run'})
            assert r.status_code == 200, r.text
            times = []
            for _ in range(18):
                frame = ws.receive_json()
                times.append(frame['state']['t'])
                if frame['state']['t'] > .12:
                    break
            assert max(times) > .10, times
            assert all('trace_len' in frame for _ in [0])
        client.post('/api/action', json={'action':'reset'})
