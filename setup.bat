@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.12 --version >nul 2>&1
  if errorlevel 1 (python -m venv .venv) else (py -3.12 -m venv .venv)
)
if not exist .venv\Scripts\python.exe (echo Python setup failed. Install Python 3.12 and try again. & pause & exit /b 1)
.venv\Scripts\python.exe -c "import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)"
if errorlevel 1 (echo Use Python 3.12. Remove the incomplete .venv folder and run setup.bat again. & pause & exit /b 1)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (echo Dependency installation failed. & pause & exit /b 1)
if not exist .env copy .env.example .env >nul
echo Setup complete. Add your rotated Gemini and Tavily keys to .env.
echo Then double-click run_local.bat. For offline demonstration use run_demo.bat.
pause
