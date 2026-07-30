@echo off
setlocal
cd /d "%~dp0"
title GuardianEye - File Integrity Watcher

set PYTHON_EXE=%~dp0python\python.exe

if not exist "%PYTHON_EXE%" (
    echo.
    echo   [*] Python not found. Downloading portable version...
    curl -L -o python-installer.exe https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe
    start /wait "" python-installer.exe /quiet InstallAllUsers=0 TargetDir="%~dp0python" Include_pip=1 PrependPath=0 Include_test=0 Include_doc=0
    del python-installer.exe 2>nul
)

:: Launch the GUI (pythonw = no console window)
if exist "%~dp0python\pythonw.exe" (
    "%~dp0python\pythonw.exe" guardian_gui.py
) else (
    "%PYTHON_EXE%" guardian_gui.py
)
