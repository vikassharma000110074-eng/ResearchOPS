@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Run setup.bat first. & pause & exit /b 1)
set "PYTHONPATH=%~dp0backend"
echo ResearchOps API - website at http://localhost:3000
.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 3000
pause
