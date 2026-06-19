@echo off
chcp 65001 > nul
cd /d "%~dp0"

REM Development launcher.
REM The app is always started with Python from .venv so dependencies,
REM local NLP model files and runtime settings stay project-local.
REM
REM Python virtual environments store absolute paths in pyvenv.cfg. When the
REM project folder is moved, for example to a flash drive, those paths become
REM stale. This launcher rewrites pyvenv.cfg from the current folder before
REM starting Python, so the demo does not require manual path editing.

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "RUNTIME_DIR=%PROJECT_DIR%\runtime"
set "VENV_DIR=%PROJECT_DIR%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "RUNTIME_PYTHON=%RUNTIME_DIR%\python.exe"
set "PYVENV_CFG=%VENV_DIR%\pyvenv.cfg"

if not exist "%RUNTIME_PYTHON%" (
    echo Bundled runtime was not found:
    echo %RUNTIME_PYTHON%
    pause
    exit /b 1
)

if not exist "%VENV_PYTHON%" (
    echo Virtual environment .venv was not found.
    echo Create it with:
    echo runtime\python.exe -m venv .venv
    echo Then install project dependencies:
    echo .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

REM Keep .venv portable across folder moves by pointing it at the bundled
REM runtime in the current project directory.
(
    echo home = %RUNTIME_DIR%
    echo include-system-site-packages = false
    echo version = 3.12.8
    echo executable = %RUNTIME_PYTHON%
    echo command = %RUNTIME_PYTHON% -m venv %VENV_DIR%
) > "%PYVENV_CFG%"

set "LOG_ANALYZER_PORT=7000"
echo Starting Log Analyzer on 127.0.0.1:%LOG_ANALYZER_PORT% through .venv...

"%VENV_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port %LOG_ANALYZER_PORT%
pause
