@echo off
cd /d "%~dp0"
set "APP_ENV=local"
set "EXECUTION_MODE=local-worker"
set "DEMO_MODE=true"
set "DATA_DIR=%~dp0data\demo"
set "DATABASE_URL="
set "WORKSPACE_PASSWORD="
set "SESSION_SECRET="
call run_local.bat
