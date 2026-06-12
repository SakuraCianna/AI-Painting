@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if not exist "frontend\node_modules" call npm install --prefix frontend
set "BACKEND_PORT=8080"
set "FRONTEND_PORT=5173"
set "VITE_API_BASE_URL=http://127.0.0.1:%BACKEND_PORT%"
start "AI Painting Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port %BACKEND_PORT%"
start "AI Painting Frontend" cmd /k "set VITE_API_BASE_URL=%VITE_API_BASE_URL%&& npm run dev --prefix frontend -- --host 127.0.0.1 --port %FRONTEND_PORT% --strictPort"
start "" "http://127.0.0.1:%FRONTEND_PORT%"
