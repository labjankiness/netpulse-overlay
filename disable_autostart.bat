@echo off
echo Disabling NetPulse Overlay from Windows Startup...
del /F /Q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\netpulse-overlay.vbs" >nul 2>&1
echo NetPulse Overlay removed from Windows startup.
pause
