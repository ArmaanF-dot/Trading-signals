@echo off
rem Double-click, or run from a terminal:  live\run_live.bat
rem First run creates a private Python environment and installs what is needed (a few minutes);
rem later runs start straight away. Extra options pass through, e.g.  live\run_live.bat --model base.en
cd /d "%~dp0\.."
if not exist .venv-live\Scripts\python.exe (
  py -3.12 -m venv .venv-live 2>nul || py -3.11 -m venv .venv-live 2>nul || py -3 -m venv .venv-live || (echo Python 3.11 or 3.12 is needed: https://www.python.org/downloads/ & pause & exit /b 1)
)
call .venv-live\Scripts\activate.bat
python -m pip install --quiet --disable-pip-version-check -r live\requirements.txt || (echo Install failed & pause & exit /b 1)
python -m live %*
pause
