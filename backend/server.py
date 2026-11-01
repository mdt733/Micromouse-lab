"""Local browser front end for MicroMouse Lab.

Physics advances on its own thread, independently from browser/WebSocket traffic.
Controller code executes in a separate local process (not a security sandbox).
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .controller_worker import ControllerRunner
from .physics import DEFAULT_CONFIG, PlanarPhysics, validate_config

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'
DATA = ROOT / 'data'
CODE_PATH = DATA / 'controller.py'
CONFIG_PATH = DATA / 'config.json'
EXAMPLES = ROOT / 'examples'
DATA.mkdir(exist_ok=True)


class SimService:
    def __init__(self):
        stored = json.loads(CONFIG_PATH.read_text(encoding='utf-8')) if CONFIG_PATH.exists() else DEFAULT_CONFIG
        self.config = validate_config(stored)
        self.engine = PlanarPhysics(self.config)
        self.worker = ControllerRunner()
        self.lock = threading.RLock()
        self.shutdown = threading.Event()
        self.thread: threading.Thread | None = None
        self.running = False
        self.loaded = False
        self.complete = False
        self.run_id = 0
        self.logs = deque(maxlen=12000)
        self.trace = deque(maxlen=8000)
        self.clients: set[WebSocket] = set()
        self.sample_count = 0
        self.latest_sensors = self.engine.sample_sensors()
        self.record()
        self.log('Lab ready. Save & Run starts the autonomous simulation clock.')

    def log(self, message: str):
        for line in str(message).splitlines():
            if line.strip():
                self.logs.append({'t': round(self.engine.s.t, 3), 'line': line[:800]})

    def record(self):
        self.trace.append({'state': self.engine.snapshot(), 'sensors': self.latest_sensors})

    def status(self):
        with self.lock:
            return {'running': self.running, 'loaded': self.loaded,
                    'complete': self.complete, 'run_id': self.run_id,
                    'trace_len': len(self.trace), 'config': self.config,
                    'scene': self.engine.scene(), 'state': self.engine.snapshot(),
                    'logs': list(self.logs)[-60:], 'sensors': self.latest_sensors}

    def frame(self):
        with self.lock:
            return {'type': 'frame', 'running': self.running, 'loaded': self.loaded,
                    'complete': self.complete, 'run_id': self.run_id,
                    'trace_len': len(self.trace), 'state': self.engine.snapshot(),
                    'logs': list(self.logs)[-60:], 'sensors': self.latest_sensors}

    def reset(self):
        with self.lock:
            self.running = False
            self.worker.stop()
            self.loaded = False
            self.complete = False
            self.run_id += 1
            self.engine.reset()
            self.sample_count = 0
            self.trace.clear()
            self.logs.clear()
            self.latest_sensors = self.engine.sample_sensors()
            self.record()
            self.log('Simulation reset.')

    def load(self):
        with self.lock:
            self.running = False
            code = CODE_PATH.read_text(encoding='utf-8')
            result = self.worker.start(code)
            self.loaded = bool(result.get('ok'))
            if result.get('log'):
                self.log(result['log'])
            if not self.loaded:
                self.log('ERROR: ' + result.get('error', 'Unknown error'))
            else:
                self.log('Controller loaded successfully.')
            return result

    def step(self, ticks: int = 20):
        """Advance in deterministic 1 ms physics ticks. Called only while lock is held."""
        if not self.loaded or self.complete:
            return
        for _ in range(ticks):
            if self.sample_count % 5 == 0:
                self.latest_sensors = self.engine.sample_sensors()
                response = self.worker.step(self.latest_sensors, .005)
                if not response.get('ok'):
                    self.running = False
                    self.loaded = False
                    self.engine.set_command({'left_motor': 0, 'right_motor': 0, 'fan': 0})
                    self.log('CONTROLLER ERROR: ' + response.get('error', 'Unknown error'))
                    self.worker.stop()
                    self.record()
                    return
                if response.get('log'):
                    self.log(response['log'])
                try:
                    self.engine.set_command(response.get('output', {}))
                except (TypeError, ValueError) as exc:
                    self.log('Invalid controller output: ' + str(exc))
                    self.running = False
                    self.record()
                    return
            self.engine.step()
            self.sample_count += 1
            if self.engine.s.t + 1e-8 >= self.config['duration_s']:
                self.running = False
                self.complete = True
                self.log('Run complete: configured time limit reached. Replay is ready.')
                break
        # Record one complete measurement sample per 20 ms block (50 Hz).
        self.record()

    def start_clock(self):
        self.shutdown.clear()
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.clock_loop, daemon=True, name='micromouse-physics')
        self.thread.start()

    def clock_loop(self):
        deadline = time.perf_counter()
        while not self.shutdown.is_set():
            with self.lock:
                active = self.running
                if active:
                    try:
                        self.step(20)
                    except Exception as exc:
                        self.running = False
                        self.log(f'SIMULATION ERROR: {type(exc).__name__}: {exc}')
            if not active:
                deadline = time.perf_counter() + .020
            else:
                deadline = max(deadline + .020, time.perf_counter())
            self.shutdown.wait(max(0., deadline - time.perf_counter()))

    def stop_clock(self):
        self.shutdown.set()
        if self.thread:
            self.thread.join(timeout=1.5)
        with self.lock:
            self.running = False
            self.worker.stop()

    def replay(self):
        with self.lock:
            return {'format': 'micromouse-lab-replay-v2', 'run_id': self.run_id,
                    'complete': self.complete, 'frames': list(self.trace),
                    'logs': list(self.logs), 'scene': self.engine.scene()}

    def export(self):
        with self.lock:
            return {'format': 'micromouse-lab-run-v2', 'run_id': self.run_id,
                    'complete': self.complete, 'config': self.config,
                    'controller': CODE_PATH.read_text(encoding='utf-8'),
                    'scene': self.engine.scene(), 'trace': list(self.trace),
                    'logs': list(self.logs),
                    'limitations': ['planar dynamics', 'circular hull collision',
                                    'simplified tyre stiffness and DC motors',
                                    'fan normal-force approximation']}


service = SimService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    service.start_clock()
    broadcaster = asyncio.create_task(broadcast_loop())
    try:
        yield
    finally:
        broadcaster.cancel()
        try:
            await broadcaster
        except asyncio.CancelledError:
            pass
        service.stop_clock()


app = FastAPI(title='MicroMouse Lab', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=str(WEB)), name='static')


@app.get('/')
async def home():
    return FileResponse(WEB / 'index.html')


@app.get('/api/status')
async def status():
    return service.status()


@app.get('/api/replay')
async def replay():
    return service.replay()


@app.get('/api/examples/{name}')
async def example(name: str):
    if name not in ('wall_follower', 'left_turn'):
        raise HTTPException(status_code=404, detail='Unknown example')
    return {'code': (EXAMPLES / (name + '.py')).read_text(encoding='utf-8')}


@app.get('/api/controller')
async def get_controller():
    return {'code': CODE_PATH.read_text(encoding='utf-8')}


class CodePayload(BaseModel):
    code: str


@app.post('/api/controller')
async def set_controller(payload: CodePayload):
    if len(payload.code) > 128_000:
        raise HTTPException(status_code=400, detail='Code exceeds 128 kB')
    with service.lock:
        if service.running:
            raise HTTPException(status_code=409, detail='Pause before saving controller source')
        CODE_PATH.write_text(payload.code, encoding='utf-8')
        service.log('Controller source saved.')
    return {'ok': True}


class ConfigPayload(BaseModel):
    config: dict[str, Any]


@app.post('/api/config')
async def set_config(payload: ConfigPayload):
    try:
        cfg = validate_config(payload.config)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    with service.lock:
        service.reset()
        service.config = cfg
        service.engine = PlanarPhysics(cfg)
        service.latest_sensors = service.engine.sample_sensors()
        service.trace.clear()
        service.record()
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
        service.log('Hardware/course configuration applied; model rebuilt.')
        return service.status()


class ActionPayload(BaseModel):
    action: str


@app.post('/api/action')
async def action(payload: ActionPayload):
    with service.lock:
        a = payload.action
        if a == 'pause':
            service.running = False
            service.log('Paused.')
        elif a == 'reset':
            service.reset()
        elif a == 'run':
            if service.complete:
                service.reset()
            if not service.loaded:
                result = service.load()
                if not result.get('ok'):
                    return JSONResponse(status_code=400, content={'error': result.get('error'),
                                                                    'status': service.status()})
            service.running = True
            service.log('RUN: autonomous clock started.')
        elif a == 'step':
            service.running = False
            if service.complete:
                service.reset()
            if not service.loaded:
                result = service.load()
                if not result.get('ok'):
                    return JSONResponse(status_code=400, content={'error': result.get('error'),
                                                                    'status': service.status()})
            service.step(20)
        else:
            raise HTTPException(status_code=400, detail='Unknown action')
        return service.status()


@app.get('/api/export')
async def export():
    return JSONResponse(service.export(), headers={
        'Content-Disposition': 'attachment; filename="micromouse-run.json"'})


@app.websocket('/ws')
async def socket(ws: WebSocket):
    await ws.accept()
    service.clients.add(ws)
    try:
        await ws.send_json({'type': 'status', **service.status()})
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        service.clients.discard(ws)


async def broadcast_loop():
    while True:
        if service.clients:
            message = service.frame()
            for ws in tuple(service.clients):
                try:
                    await asyncio.wait_for(ws.send_json(message), timeout=.15)
                except Exception:
                    service.clients.discard(ws)
        await asyncio.sleep(.05)
