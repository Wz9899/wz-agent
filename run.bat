@echo off
cd /d "%~dp0"
echo ========================================
echo   wz-agent - coding assistant
echo ========================================
echo.
set /p TARGET=Target project dir (Enter = current wz-agent dir):
echo.
if "%TARGET%"=="" (
    python src\main.py %*
) else (
    python src\main.py -C "%TARGET%" %*
)
echo.
echo Done. Press any key to close.
pause >nul
