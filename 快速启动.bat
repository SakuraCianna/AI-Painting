@echo off
cd /d "%~dp0"
start "AI Painting Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8084"
start "AI Painting Frontend" cmd /k "set VITE_API_BASE_URL=http://127.0.0.1:8084&& npm run dev --prefix frontend -- --host 127.0.0.1 --port 3001 --strictPort"
start "" "http://127.0.0.1:3001"
