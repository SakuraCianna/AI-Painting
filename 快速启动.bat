@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if not exist "frontend\node_modules" call npm install --prefix frontend
start "AI Painting Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000"
start "AI Painting Frontend" cmd /k "npm run dev --prefix frontend -- --host 127.0.0.1 --port 5173"
start "" "http://127.0.0.1:5173"
