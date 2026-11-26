@echo off
rem Removes the Baco app shortcuts made by install-app.bat. Keys saved in Edge are left alone.
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
rem The desktop may live in OneDrive, so ask Windows where it is.
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP=%%d"
del "%STARTMENU%\Baco.lnk" >nul 2>&1
del "%STARTMENU%\Startup\Baco.lnk" >nul 2>&1
del "%DESKTOP%\Baco.lnk" >nul 2>&1
rmdir /s /q "%LOCALAPPDATA%\Baco" >nul 2>&1
rem Shortcuts from when the app was called Hugo or Jarvis.
del "%STARTMENU%\Hugo.lnk" >nul 2>&1
del "%STARTMENU%\Startup\Hugo.lnk" >nul 2>&1
del "%DESKTOP%\Hugo.lnk" >nul 2>&1
rmdir /s /q "%LOCALAPPDATA%\Hugo" >nul 2>&1
del "%STARTMENU%\Jarvis.lnk" >nul 2>&1
del "%STARTMENU%\Startup\Jarvis.lnk" >nul 2>&1
del "%DESKTOP%\Jarvis.lnk" >nul 2>&1
rmdir /s /q "%LOCALAPPDATA%\Jarvis" >nul 2>&1
echo Removed. The website still works at https://armaanf-dot.github.io/Trading-signals/
pause
