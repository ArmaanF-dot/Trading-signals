@echo off
rem Installs Jarvis as a desktop app on Windows: its own window (no browser tabs or address bar),
rem a Start Menu and desktop shortcut, and optionally starts when you log in.
rem Run it once (double-click). Undo with app-remove.bat. Needs only Microsoft Edge, which Windows already has.
setlocal
set "URL=https://armaanf-dot.github.io/Trading-signals/"
set "HOME_DIR=%LOCALAPPDATA%\Jarvis"
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
rem The desktop may live in OneDrive, so ask Windows where it is.
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP=%%d"
set "STARTUP=%STARTMENU%\Startup"

set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" (
  echo Microsoft Edge was not found. Open %URL% in Chrome or Edge and use "Install Jarvis" instead.
  pause & exit /b 1
)

if not exist "%HOME_DIR%" mkdir "%HOME_DIR%"
if exist "%~dp0jarvis.ico" (
  copy /y "%~dp0jarvis.ico" "%HOME_DIR%\jarvis.ico" >nul
) else (
  powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/ArmaanF-dot/Trading-signals/main/app/jarvis.ico' -OutFile '%HOME_DIR%\jarvis.ico'" >nul 2>&1
)

set "ARGS=--app=%URL% --window-size=1500,950"
call :shortcut "%STARTMENU%\Jarvis.lnk"
call :shortcut "%DESKTOP%\Jarvis.lnk"

choice /c YN /m "Start Jarvis automatically when you log in to Windows"
if errorlevel 2 goto done
call :shortcut "%STARTUP%\Jarvis.lnk"

:done
echo.
echo Done. Open Jarvis from the Start Menu or the desktop icon.
echo Keys you type into the app (Keys button) are shared with Edge on this PC and never leave it.
start "" "%EDGE%" --app=%URL% --window-size=1500,950
pause
exit /b 0

:shortcut
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%~1'); $s.TargetPath='%EDGE%'; $s.Arguments='%ARGS%'; $s.WorkingDirectory='%HOME_DIR%'; if (Test-Path '%HOME_DIR%\jarvis.ico') { $s.IconLocation='%HOME_DIR%\jarvis.ico' }; $s.Description='Jarvis market homescreen'; $s.Save()"
exit /b 0
