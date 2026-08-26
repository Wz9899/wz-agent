@echo off
rem ============================================================
rem  wz-agent graphical launcher
rem
rem  Usage 1: double-click this file -> folder picker dialog
rem  Usage 2: drag a project folder onto this icon
rem  Usage 3: right-click folder -> Send to -> wz-agent-here
rem           (after running install-sendto.bat once)
rem  Usage 4: command line  run.bat <dir> [extra args]
rem ============================================================
cd /d "%~dp0"
setlocal

set "TARGET=%~1"
if defined TARGET shift

if not defined TARGET (
    for /f "usebackq delims=" %%i in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $f=New-Object System.Windows.Forms.FolderBrowserDialog; $f.Description='wz-agent: pick target project (agent will work inside it)'; if($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){$f.SelectedPath}"`) do set "TARGET=%%i"
)

if not defined TARGET (
    echo Cancelled.
    pause
    exit /b 0
)

echo Target: %TARGET%
python src\main.py -C "%TARGET%" %1 %2 %3 %4 %5 %6 %7 %8 %9
echo.
pause
