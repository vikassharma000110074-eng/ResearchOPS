@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Run setup.bat first. & pause & exit /b 1)
set "PYTHONPATH=%~dp0backend"
echo ResearchOps independent worker - keep this terminal open for LOCAL research.
.venv\Scripts\python.exe -m researchops_backend.worker
pause
