@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if not exist "frontend\node_modules" call npm install --prefix frontend
for /f %%p in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach ($p in 8000..8010) { if (-not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)) { $p; break } }"') do set "BACKEND_PORT=%%p"
if not defined BACKEND_PORT set "BACKEND_PORT=8000"
for /f %%p in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach ($p in 5173..5183) { if (-not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)) { $p; break } }"') do set "FRONTEND_PORT=%%p"
if not defined FRONTEND_PORT set "FRONTEND_PORT=5173"
set "VITE_API_BASE_URL=http://127.0.0.1:%BACKEND_PORT%"
start "AI Painting Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port %BACKEND_PORT%"
start "AI Painting Frontend" cmd /k "set VITE_API_BASE_URL=%VITE_API_BASE_URL%&& npm run dev --prefix frontend -- --host 127.0.0.1 --port %FRONTEND_PORT% --strictPort"
start "" "http://127.0.0.1:%FRONTEND_PORT%"
