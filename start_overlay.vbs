' NetPulse Overlay Silent Launcher
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Generate(_)\netpulse-overlay"
WshShell.Run """C:\Users\Generate(_)\AppData\Local\Programs\Python\Python312\pythonw.exe"" ""C:\Users\Generate(_)\netpulse-overlay\overlay.py""", 0, False
