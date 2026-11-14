@echo off
cd /d "%~dp0"
python grader.py
if errorlevel 1 py grader.py
pause
