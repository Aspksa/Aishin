@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title Aishin Kitsune

cd /d "%~dp0"
if errorlevel 1 goto :fail_cd

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

if not defined BASE_PY goto :fail_python

echo [1/7] Проверяю Python 3.11+...
%BASE_PY% --version
%BASE_PY% --version >>"%LOG%" 2>&1

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >>"%LOG%" 2>&1
    if errorlevel 1 (
        echo       Найдено повреждённое виртуальное окружение. Пересоздаю...
        >>"%LOG%" echo Broken .venv detected. Recreating.
        rmdir /s /q ".venv" >>"%LOG%" 2>&1
        if exist ".venv" goto :fail_venv_remove
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [2/7] Создаю локальное окружение...
    %BASE_PY% -m venv .venv >>"%LOG%" 2>&1
    if errorlevel 1 goto :fail_venv_create
) else (
    echo [2/7] Локальное окружение готово.
)

set "VPY=%CD%\.venv\Scripts\python.exe"

echo [3/7] Проверяю зависимости...
"%VPY%" -m pip install --disable-pip-version-check -q -r requirements.txt >>"%LOG%" 2>&1
if errorlevel 1 goto :fail_dependencies

if /I "%~1"=="--check-only" goto :skip_update

echo [4/7] Проверяю обновления GitHub...
where git >nul 2>nul
if not errorlevel 1 (
    git fetch origin main >>"%LOG%" 2>&1
    if not errorlevel 1 (
        git pull --ff-only origin main >>"%LOG%" 2>&1
    )
)
goto :after_update

:skip_update
echo [4/7] GitHub update пропущен в check-only режиме.

:after_update
echo [5/7] Проверяю ядро Айшин...
"%VPY%" scripts\self_check.py >>"%LOG%" 2>&1
if errorlevel 1 goto :fail_self_check

echo [6/7] Проверяю FastAPI runtime...
"%VPY%" scripts\runtime_smoke.py >>"%LOG%" 2>&1
if errorlevel 1 goto :fail_runtime_smoke

if /I "%~1"=="--check-only" (
    echo.
    echo [OK] Launcher preflight успешно завершён.
    >>"%LOG%" echo Launcher check-only completed successfully.
    exit /b 0
)

echo [7/7] Проверяю порт 8765...
set "PROBE_FILE=%TEMP%\aishin_probe_%RANDOM%_%RANDOM%.txt"
"%VPY%" scripts\launcher_probe.py >"%PROBE_FILE%" 2>>"%LOG%"
set "PROBE_RC=%ERRORLEVEL%"
set "PROBE_RESULT="
if exist "%PROBE_FILE%" set /p PROBE_RESULT=<"%PROBE_FILE%"
if exist "%PROBE_FILE%" del /q "%PROBE_FILE%" >nul 2>&1

if "%PROBE_RC%"=="10" goto :already_running
if "%PROBE_RC%"=="11" goto :fail_port_busy
if not "%PROBE_RC%"=="0" goto :fail_probe

echo.
echo [START] Запускаю Айшин на http://127.0.0.1:8765
echo        Это окно является сервером Айшин. Не закрывайте его во время работы.
echo.
>>"%LOG%" echo Starting uvicorn on 127.0.0.1:8765

start "" http://127.0.0.1:8765
"%VPY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
set "SERVER_RC=%ERRORLEVEL%"
>>"%LOG%" echo Uvicorn exited with code %SERVER_RC%

if not "%SERVER_RC%"=="0" goto :fail_server

echo.
echo [STOP] Сервер Айшин завершил работу.
echo Нажмите любую клавишу, чтобы закрыть это окно.
pause >nul
exit /b 0

:already_running
echo.
echo [OK] Айшин уже запущена на http://127.0.0.1:8765
echo Открываю существующий экземпляр.
>>"%LOG%" echo Existing Aishin instance detected.
start "" http://127.0.0.1:8765
echo.
echo Нажмите любую клавишу, чтобы закрыть launcher.
pause >nul
exit /b 0

:fail_python
echo.
echo [ERROR] Python 3.11+ не найден.
echo Установите Python 3.11 или новее и включите его в PATH.
>>"%LOG%" echo ERROR: Python 3.11+ not found.
goto :fail_common

:fail_cd
echo.
echo [ERROR] Не удалось открыть папку проекта.
goto :fail_common

:fail_venv_remove
echo.
echo [ERROR] Не удалось удалить повреждённую .venv.
echo Закройте процессы Python, использующие эту папку, и повторите запуск.
>>"%LOG%" echo ERROR: could not remove broken .venv.
goto :fail_common

:fail_venv_create
echo.
echo [ERROR] Не удалось создать .venv.
>>"%LOG%" echo ERROR: venv creation failed.
goto :fail_common

:fail_dependencies
echo.
echo [ERROR] Не удалось установить или проверить зависимости.
>>"%LOG%" echo ERROR: dependency installation failed.
goto :fail_common

:fail_self_check
echo.
echo [ERROR] Self-check Айшин завершился ошибкой.
>>"%LOG%" echo ERROR: self_check failed.
goto :fail_common

:fail_runtime_smoke
echo.
echo [ERROR] FastAPI runtime smoke завершился ошибкой.
>>"%LOG%" echo ERROR: runtime_smoke failed.
goto :fail_common

:fail_probe
echo.
echo [ERROR] Не удалось проверить порт 8765.
echo Результат: %PROBE_RESULT%
>>"%LOG%" echo ERROR: launcher probe failed: %PROBE_RESULT%
goto :fail_common

:fail_port_busy
echo.
echo [ERROR] Порт 8765 уже занят другим приложением.
echo Закройте приложение, использующее 127.0.0.1:8765, и запустите Aishin.bat снова.
>>"%LOG%" echo ERROR: port 8765 busy: %PROBE_RESULT%
goto :fail_common

:fail_server
echo.
echo [ERROR] Сервер Айшин завершился с кодом %SERVER_RC%.
echo Причина сохранена в:
echo "%LOG%"
>>"%LOG%" echo ERROR: uvicorn failed with code %SERVER_RC%
goto :fail_common

:fail_common
echo.
echo ---------------- ПОСЛЕДНИЕ СТРОКИ ЛОГА ----------------
powershell -NoProfile -Command "if (Test-Path -LiteralPath '%LOG%') { Get-Content -LiteralPath '%LOG%' -Tail 35 }" 2>nul
echo ---------------------------------------------------------
echo.
echo Окно останется открытым. Нажмите любую клавишу после просмотра ошибки.
pause >nul
exit /b 1
