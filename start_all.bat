@echo off
REM TruthSync AI - starts the device API (port 8000) and the web app (port 8501) from THIS folder.
cd /d "%~dp0"
echo Stopping anything already using ports 8000 and 8501 ...
for %%P in (8000 8501) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P " ^| findstr LISTENING') do taskkill /PID %%A /F >nul 2>&1
)
if not exist .env copy .env.example .env >nul
start "TruthSync API (port 8000)" cmd /k python -m uvicorn api:app --host 0.0.0.0 --port 8000
timeout /t 4 >nul
start "TruthSync Web (port 8501)" cmd /k python -m streamlit run app.py
echo.
echo Started. In the API window you must see:  TruthSync API using database: ...truthsync.db
echo Open http://localhost:8501
