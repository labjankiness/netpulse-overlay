@echo off
start "" pythonw overlay.py
if %ERRORLEVEL% NEQ 0 (
    start "" python overlay.py
)
