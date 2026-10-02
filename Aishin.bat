@echo off
setlocal EnableExtensions
title Aishin Kitsune

cd /d "%~dp0"
if errorlevel 1 goto fail_cd

set "LOG_DIR=%CD%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "LOG=%LOG_DIR%\launcher.log"
> "%LOG%" echo [%DATE% %TIME%] Aishin launcher started
>>"%LOG%" echo Project: %CD%

echo.
echo ==========================================
echo           AISHIN KITSUNE
echo ==========================================
echo.
echo Launcher log: "%LOG%"
echo.

set "BASE_PY="

where py >nul 2>nul
if not errorlevel 1 (
    py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >>"%LOG%" 2>&1
    if not errorlevel 1 set "BASE_PY=py -3.11"
)

if not defined BASE_PY (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >>"%LOG%" 2>&1
        if not errorlevel 1 set "BASE_PY=python"
    )
)

if not defined BASE_PY goto fail_python

echo [1/7] Checking Python 3.11+...
%BASE_PY% --version
%BASE_PY% --version >>"%LOG%" 2>&1

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >>"%LOG%" 2>&1
    if errorlevel 1 (
        echo       Broken virtual environment detected. Recreating...
        >>"%LOG%" echo Broken .venv detected. Recreating.
        rmdir /s /q ".venv" >>"%LOG%" 2>&1
        if exist ".venv" goto fail_venv_remove
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [2/7] Creating local virtual environment...
    %BASE_PY% -m venv .venv >>"%LOG%" 2>&1
    if errorlevel 1 goto fail_venv_create
) else (
    echo [2/7] Local virtual environment is ready.
)

set "VPY=%CD%\.venv\Scripts\python.exe"

echo [3/7] Checking dependencies...
"%VPY%" -m pip install --disable-pip-version-check -q -r requirements.txt >>"%LOG%" 2>&1
if errorlevel 1 goto fail_dependencies

if /I "%~1"=="--check-only" goto skip_update

echo [4/7] Checking GitHub updates...
"%VPY%" -c "from pathlib import Path; from app.updater import ProjectUpdater; r=ProjectUpdater(Path.cwd()).update(); print('[UPDATE]', r.get('mode'), r.get('details'))" >>"%LOG%" 2>&1
if errorlevel 1 (
    echo       Update check failed; continuing with current files.
    >>"%LOG%" echo WARNING: automatic project update failed.
) else (
    echo       Project files refreshed from GitHub.
)
goto after_update

:skip_update
echo [4/7] GitHub update skipped in check-only mode.

:after_update
echo [5/7] Running Aishin core self-check...
"%VPY%" scripts\self_check.py >>"%LOG%" 2>&1
if errorlevel 1 goto fail_self_check

echo [6/7] Running FastAPI runtime smoke test...
"%VPY%" scripts\runtime_smoke.py >>"%LOG%" 2>&1
if errorlevel 1 goto fail_runtime_smoke

if /I "%~1"=="--check-only" (
    echo.
    echo [OK] Launcher preflight completed successfully.
    >>"%LOG%" echo Launcher check-only completed successfully.
    exit /b 0
)

echo [7/7] Checking port 8765...
set "PROBE_FILE=%TEMP%\aishin_probe_%RANDOM%_%RANDOM%.txt"
"%VPY%" scripts\launcher_probe.py >"%PROBE_FILE%" 2>>"%LOG%"
set "PROBE_RC=%ERRORLEVEL%"
set "PROBE_RESULT="
if exist "%PROBE_FILE%" set /p PROBE_RESULT=<"%PROBE_FILE%"
if exist "%PROBE_FILE%" del /q "%PROBE_FILE%" >nul 2>&1

if "%PROBE_RC%"=="10" goto already_running
if "%PROBE_RC%"=="11" goto fail_port_busy
if not "%PROBE_RC%"=="0" goto fail_probe

echo.
echo [START] Starting Aishin at http://127.0.0.1:8765
echo         Keep this window open while Aishin is running.
echo.
>>"%LOG%" echo Starting uvicorn on 127.0.0.1:8765

start "" http://127.0.0.1:8765
"%VPY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
set "SERVER_RC=%ERRORLEVEL%"
>>"%LOG%" echo Uvicorn exited with code %SERVER_RC%

if not "%SERVER_RC%"=="0" goto fail_server

echo.
echo [STOP] Aishin server stopped.
echo Press any key to close this window.
pause >nul
exit /b 0

:already_running
echo.
echo [OK] Aishin is already running at http://127.0.0.1:8765
echo Opening the existing instance.
>>"%LOG%" echo Existing Aishin instance detected.
start "" http://127.0.0.1:8765
echo.
echo Press any key to close this launcher.
pause >nul
exit /b 0

:fail_python
echo.
echo [ERROR] Python 3.11+ was not found.
echo Install Python 3.11 or newer and enable it in PATH.
>>"%LOG%" echo ERROR: Python 3.11+ not found.
goto fail_common

:fail_cd
echo.
echo [ERROR] Could not open the project directory.
goto fail_common

:fail_venv_remove
echo.
echo [ERROR] Could not remove the broken .venv directory.
echo Close Python processes using this folder and try again.
>>"%LOG%" echo ERROR: could not remove broken .venv.
goto fail_common

:fail_venv_create
echo.
echo [ERROR] Could not create .venv.
>>"%LOG%" echo ERROR: venv creation failed.
goto fail_common

:fail_dependencies
echo.
echo [ERROR] Dependency installation or verification failed.
>>"%LOG%" echo ERROR: dependency installation failed.
goto fail_common

:fail_self_check
echo.
echo [ERROR] Aishin self-check failed.
>>"%LOG%" echo ERROR: self_check failed.
goto fail_common

:fail_runtime_smoke
echo.
echo [ERROR] FastAPI runtime smoke test failed.
>>"%LOG%" echo ERROR: runtime_smoke failed.
goto fail_common

:fail_probe
echo.
echo [ERROR] Could not check port 8765.
echo Probe result: %PROBE_RESULT%
>>"%LOG%" echo ERROR: launcher probe failed: %PROBE_RESULT%
goto fail_common

:fail_port_busy
echo.
echo [ERROR] Port 8765 is already used by another application.
echo Close the application using 127.0.0.1:8765 and run Aishin.bat again.
>>"%LOG%" echo ERROR: port 8765 busy: %PROBE_RESULT%
goto fail_common

:fail_server
echo.
echo [ERROR] Aishin server exited with code %SERVER_RC%.
echo Full diagnostic log:
echo "%LOG%"
>>"%LOG%" echo ERROR: uvicorn failed with code %SERVER_RC%
goto fail_common

:fail_common
echo.
echo ---------------- LAST LOG LINES ----------------
powershell -NoProfile -Command "if (Test-Path -LiteralPath '%LOG%') { Get-Content -LiteralPath '%LOG%' -Tail 35 }" 2>nul
echo ------------------------------------------------
echo.
echo This window will stay open. Press any key after reading the error.
pause >nul
exit /b 1
