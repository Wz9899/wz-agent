@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   wz-agent - 双击运行编码助手
echo ========================================
echo.
echo 默认任务：帮我写一个猜人游戏
echo 想改任务：右键编辑本文件，修改下面引号里的文字
echo.
python src\main.py "帮我写一个猜人游戏"
echo.
echo 运行结束。按任意键关闭窗口。
pause >nul
