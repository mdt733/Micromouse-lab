@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
.venv\Scripts\python.exe -m uvicorn backend.server:app --host 127.0.0.1 --port 8000
pause
