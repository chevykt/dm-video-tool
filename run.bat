@echo off
REM run.bat - double-click launcher for Windows.
cd /d "%~dp0"

REM Pick a Python launcher: prefer "py -3", fall back to plain "python".
where py >nul 2>nul
if errorlevel 1 goto usepython
set PYCMD=py -3
goto havepy

:usepython
set PYCMD=python

:havepy
REM If a virtual environment already exists, make sure it still actually
REM runs before trusting it: the base Python may have been updated or
REM removed since it was created, or the folder may have been moved.
if not exist ".venv\Scripts\python.exe" goto makevenv
".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if errorlevel 1 goto brokenvenv
goto havevenv

:brokenvenv
echo The app's Python setup is broken (Python may have been updated). Rebuilding it...
rmdir /s /q ".venv"

:makevenv
echo First run: setting things up, this takes a few minutes...
%PYCMD% -m venv .venv
if errorlevel 1 goto novenv

:havevenv
REM Every launch: make sure packages are installed, so a failed first
REM install heals itself on the next double-click.
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto nopip

".venv\Scripts\python.exe" -m streamlit run app.py
goto end

:novenv
echo.
echo Could not set up the app.
echo Please install Python 3.11 or newer from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during install, then run this file again.
pause
exit /b 1

:nopip
echo.
echo Could not install the required packages.
echo Check your internet connection and run this file again.
pause
exit /b 1

:end
pause
