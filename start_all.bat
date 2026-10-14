@echo off
rem Запуск Fiction Engine (порт 5000) и Планировщика (порт 5001) в отдельных окнах.
rem Закрыть — закрыть эти окна.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set "VPY=%~dp0fiction_engine\.venv\Scripts\python.exe"
if not exist "%VPY%" (
    echo Сначала запусти setup_windows.bat
    pause
    exit /b 1
)
start "Fiction Engine" /d "%~dp0fiction_engine\web" "%VPY%" app.py
start "Planner" /d "%~dp0planner" "%VPY%" app.py
timeout /t 4 /nobreak >nul
start "" http://localhost:5000
start "" http://localhost:5001
echo Fiction Engine:  http://localhost:5000
echo Планировщик:     http://localhost:5001
