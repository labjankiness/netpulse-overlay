@echo off
title NetPulse Overlay
cd /d "%~dp0"
echo ==============================================
echo   NetPulse Desktop Stability Overlay
echo ==============================================
echo Starting overlay...
"C:\Users\Generate(_)\AppData\Local\Programs\Python\Python312\python.exe" overlay.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred while running the overlay.
    pause
)
