@echo off
setlocal
chcp 65001 >nul
title Aishin Kitsune

cd /d "%~dp0"

echo.
echo ==========================================
echo           AISHIN KITSUNE
echo ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python не найден.
    echo Установите Python 3.11+ и повторите запуск.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Создаю локальное окружение...
    python -m venv .venv
    if errorlevel 1 goto :fail
)

echo [2/4] Проверяю зависимости...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :fail

echo [3/5] Проверяю обновления GitHub...
where git >nul 2>nul
if not errorlevel 1 (
    git fetch origin main >nul 2>nul
    git pull --ff-only origin main >nul 2>nul
)

echo [4/5] Проверяю ядро Айшин...
".venv\Scripts\python.exe" scripts\self_check.py
if errorlevel 1 goto :fail

echo [5/5] Запускаю Айшин...
start "" http://127.0.0.1:8765
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8765

exit /b 0

:fail
echo.
echo [ERROR] Запуск не завершён. Проверьте сообщение выше.
pause
exit /b 1
