@echo off
cd /d "%~dp0"
python pythia.py
if errorlevel 1 py pythia.py
pause
