@echo off
for %%P in (8000 8501) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P " ^| findstr LISTENING') do taskkill /PID %%A /F
)
echo Stopped.
pause
