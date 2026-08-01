@echo off
cd /d "%~dp0"
echo ========================================
echo   wz-agent - coding assistant
echo ========================================
echo.
echo Enter your requirement below (press Enter):
echo.
python src\main.py
echo.
echo Done. Press any key to close.
pause >nul
