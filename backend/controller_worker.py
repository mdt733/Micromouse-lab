"""Separate-process controller execution with a per-step wall-clock watchdog.

IMPORTANT: Process isolation protects application responsiveness, NOT host security.
User Python has normal filesystem and OS permissions. Only use trusted local code.
"""
from __future__ import annotations
from dataclasses import dataclass
import contextlib
import io
import multiprocessing as mp
import traceback
from typing import Any

@dataclass(frozen=True)
class Sensors:
    tof_mm:dict[str,float|None]
    encoder_ticks:tuple[int,int]
    gyro_z_rad_s:float
    battery_v:float
    timestamp_s:float

@dataclass(frozen=True)
class Outputs:
    left_motor:float=0
    right_motor:float=0
    fan:float=0

def worker_main(conn, source:str):
    try:
        ns={'Sensors':Sensors,'Outputs':Outputs,'__name__':'micromouse_controller'}
        log=io.StringIO()
        with contextlib.redirect_stdout(log):
            exec(compile(source,'controller.py','exec'),ns)
            if 'Controller' in ns:
                controller=ns['Controller']()
                fn=controller.step
            else:
                fn=ns['step']
        conn.send({'ok':True,'log':log.getvalue()[-4000:]})
        while True:
            request=conn.recv()
            if request.get('type')=='quit':break
            capture=io.StringIO()
            with contextlib.redirect_stdout(capture):
                result=fn(Sensors(**request['sensors']), request['dt'])
            if isinstance(result,dict): data=result
            elif isinstance(result,Outputs): data={k:getattr(result,k) for k in ('left_motor','right_motor','fan')}
            else: raise TypeError('step() must return Outputs(...) or a dict')
            conn.send({'ok':True,'output':data,'log':capture.getvalue()[-4000:]})
    except BaseException:
        try:conn.send({'ok':False,'error':traceback.format_exc()[-5000:]})
        except Exception:pass
    finally:conn.close()

class ControllerRunner:
    def __init__(self):
        self.proc=None;self.conn=None
    def stop(self):
        if self.proc is not None:
            try:
                if self.proc.is_alive():
                    self.conn.send({'type':'quit'})
                    self.proc.join(timeout=.15)
            except (OSError,EOFError,BrokenPipeError):pass
            if self.proc.is_alive():
                self.proc.terminate();self.proc.join(timeout=.5)
            if self.proc.is_alive(): self.proc.kill();self.proc.join(timeout=.5)
        if self.conn:self.conn.close()
        self.conn=None;self.proc=None
    def start(self,source:str):
        self.stop()
        ctx=mp.get_context('spawn')
        parent,child=ctx.Pipe()
        p=ctx.Process(target=worker_main,args=(child,source),daemon=True)
        p.start();child.close()
        self.proc,self.conn=p,parent
        return self._receive(3.0)
    def _receive(self,timeout:float):
        if self.conn is None or not self.conn.poll(timeout):
            self.stop()
            return {'ok':False,'error':f'Controller timeout ({timeout:.2f}s); worker stopped.'}
        try:return self.conn.recv()
        except (OSError,EOFError) as e:
            self.stop();return {'ok':False,'error':f'Controller process ended: {e}'}
    def step(self,sensors:dict[str,Any],dt:float):
        if self.conn is None:return {'ok':False,'error':'Controller is not loaded'}
        try:self.conn.send({'type':'step','sensors':sensors,'dt':dt})
        except (OSError,EOFError,BrokenPipeError) as e:
            return {'ok':False,'error':str(e)}
        return self._receive(.5)
