@echo off
rem Запуск Fiction Engine (порт 5000) и Планировщика (порт 5001) в отдельных окнах.
rem Окна не закрываются при ошибке — в них виден её текст. Остановить — закрыть окна.
rem Другой порт: set FE_PORT=5050 перед запуском (планировщик найдёт FE сам).
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
if not defined FE_PORT set FE_PORT=5000
if not defined PLANNER_PORT set PLANNER_PORT=5001
set "FE_URL=http://127.0.0.1:%FE_PORT%"
start "Fiction Engine" /d "%~dp0fiction_engine\web" cmd /k ""%VPY%" app.py"
start "Planner" /d "%~dp0planner" cmd /k ""%VPY%" app.py"
echo Жду, пока поднимутся оба приложения...
"%VPY%" "%~dp0perenos.py" wait %FE_PORT% %PLANNER_PORT%
start "" http://localhost:%FE_PORT%
start "" http://localhost:%PLANNER_PORT%
echo Fiction Engine:  http://localhost:%FE_PORT%
echo Планировщик:     http://localhost:%PLANNER_PORT%
