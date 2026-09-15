@echo off
REM run.bat - double-click launcher for Windows.
setlocal
cd /d "%~dp0"

REM The app is tested on Python 3.12 to 3.14 (see constraints.txt). Every
REM Python this script uses has to pass this check first.
set "PYCHECK=import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 14) else 1)"
REM The Python install manager's "py" may otherwise offer to download a
REM missing version, with its question hidden by the checks below.
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"

REM If a virtual environment already exists, make sure it still runs and was
REM built with a supported Python before trusting it: the base Python may
REM have been updated or removed since it was created, or the folder moved.
if not exist ".venv" goto findpython
".venv\Scripts\python.exe" -c "%PYCHECK%" >nul 2>nul
if errorlevel 1 goto brokenvenv
goto havevenv

:brokenvenv
echo The app's Python setup is broken or out of date. Rebuilding it...
rmdir /s /q ".venv"

:findpython
REM Newest supported Python first, plain "python" last.
set "PYCMD="
call :trypython py -3.14
if defined PYCMD goto makevenv
call :trypython py -3.13
if defined PYCMD goto makevenv
call :trypython py -3.12
if defined PYCMD goto makevenv
call :trypython python
if defined PYCMD goto makevenv
goto nopython

:makevenv
echo First run: setting things up, this takes a few minutes...
%PYCMD% -m venv .venv
if errorlevel 1 goto novenv

:havevenv
REM Every launch: make sure packages are installed, so a failed first
REM install heals itself on the next double-click. The constraints file
REM pins every package to the versions the app was tested with.
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt -c constraints.txt
if errorlevel 1 goto nopip

".venv\Scripts\python.exe" -m streamlit run app.py
goto end

:nopython
echo.
echo Could not find a Python this app supports.
echo Install Python 3.14 (or 3.12 to 3.14) from https://www.python.org/downloads/
echo and run this file again.
pause
exit /b 1

:novenv
echo.
echo Could not set up the app.
echo Install Python 3.14 (or 3.12 to 3.14) from https://www.python.org/downloads/
echo and run this file again.
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
exit /b

:trypython
REM Sets PYCMD to the given command if it runs a supported Python.
%* -c "%PYCHECK%" >nul 2>nul
if errorlevel 1 goto :eof
set "PYCMD=%*"
goto :eof
