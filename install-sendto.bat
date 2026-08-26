@echo off
rem ============================================================
rem  One-time installer: add "wz-agent-here" to the right-click
rem  SendTo menu. After this, right-click any project folder ->
rem  "Send to" -> "wz-agent-here" launches the agent on it.
rem ============================================================
set "SENDTO=%APPDATA%\Microsoft\Windows\SendTo"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SENDTO%\wz-agent-here.lnk'); $s.TargetPath='%~dp0run.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0run.bat'; $s.Save()"
if exist "%SENDTO%\wz-agent-here.lnk" (
    echo Installed: right-click any folder -^> Send to -^> wz-agent-here
) else (
    echo Install failed.
)
pause
