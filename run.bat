@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   wz-agent - 实时输入需求，自动生成代码
echo ========================================
echo.
python src\main.py
echo.
echo 运行结束。按任意键关闭窗口。
pause >nul
