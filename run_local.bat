@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Run setup.bat first. & pause & exit /b 1)
start "ResearchOps API" cmd /k call "%~dp0run_backend.bat"
start "ResearchOps Worker" cmd /k call "%~dp0run_worker.bat"
echo Open http://localhost:3000 after the API terminal says Application startup complete.
