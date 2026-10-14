@echo off
rem Установка на Windows: окружение, зависимости, перенос данных, база.
rem Архив переноса (fiction_engine_perenos_*.zip) положи рядом с этим файлом.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" || goto nopython

if not exist fiction_engine\.venv\Scripts\python.exe (
    echo Создаю окружение .venv...
    %PY% -m venv fiction_engine\.venv || goto fail
)
set "VPY=%~dp0fiction_engine\.venv\Scripts\python.exe"
echo Ставлю зависимости...
"%VPY%" -m pip install -q --upgrade pip
"%VPY%" -m pip install -q -e fiction_engine || goto fail

set "ZIP="
for %%F in (fiction_engine_perenos_*.zip) do set "ZIP=%%F"
if defined ZIP (
    echo Переношу данные из %ZIP%...
    "%VPY%" perenos.py unpack "%ZIP%" || goto fail
)
"%VPY%" perenos.py init || goto fail
echo.
echo Готово. Запуск: start_all.bat
pause
exit /b 0

:nopython
echo Нужен Python 3.10 или новее: https://www.python.org/downloads/
echo При установке отметь "Add python.exe to PATH".
pause
exit /b 1

:fail
echo Установка не удалась — сообщение об ошибке выше.
pause
exit /b 1
