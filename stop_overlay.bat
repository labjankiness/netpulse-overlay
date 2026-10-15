@echo off
echo Stopping NetPulse Overlay...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*overlay.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo NetPulse Overlay stopped.
