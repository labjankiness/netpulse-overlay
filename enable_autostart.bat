@echo off
echo Enabling NetPulse Overlay at Windows Startup...
copy /Y "start_overlay.vbs" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\netpulse-overlay.vbs" >nul
echo NetPulse Overlay will now start automatically when you turn on your PC.
pause
