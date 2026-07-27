@echo off
REM ============================================================================
REM Planarus - put Start, Team, Stop and Tray shortcuts on the Desktop
REM
REM Run this once. The shortcuts point at this checkout, so moving or renaming
REM the folder afterwards means running this again.
REM ============================================================================
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "ROOT=%%~fI"

REM Without this every shortcut inherits the generic icon cmd.exe gives a .bat,
REM so a row of identical grey cogs lands on the Desktop. The .ico is committed
REM rather than generated here: building one needs an image library, and
REM requiring that at install time to decorate a shortcut is a poor trade.
set "ICON=%ROOT%\assets\planarus.ico"
if not exist "%ICON%" (
  echo [WARN] %ICON% is missing; shortcuts will use the default .bat icon.
  set "ICON="
)

REM The Desktop is not always %USERPROFILE%\Desktop - OneDrive's "back up my
REM folders" redirects it, and writing to the literal path would put shortcuts
REM somewhere the user never sees. Ask the shell where it actually is.
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP=%%D"
if not defined DESKTOP (
  echo [ERROR] Could not locate your Desktop folder.
  exit /b 1
)

call :make "Planarus.lnk"      "run-planarus.bat"      "Start Planarus"
if errorlevel 1 exit /b 1
call :make "Planarus Team.lnk" "run-planarus-team.bat" "Start Planarus with sign-in (team mode)"
if errorlevel 1 exit /b 1
call :make "Stop Planarus.lnk" "stop-planarus.bat"  "Stop Planarus"
if errorlevel 1 exit /b 1
call :make "Planarus Tray.lnk" "planarus-tray.bat"  "Planarus in the notification area"
if errorlevel 1 exit /b 1

echo.
echo Shortcuts created in %DESKTOP%.
exit /b 0

:make
REM %1 = shortcut file name, %2 = target script, %3 = description.
REM IconLocation takes "path,index"; 0 is the first icon in the file. Assigning
REM an empty string would blank the icon rather than leave the default, so the
REM missing-file case skips the line instead of setting it to nothing.
powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path '%DESKTOP%' '%~1'));" ^
  "$s.TargetPath = (Join-Path '%ROOT%' 'scripts\%~2');" ^
  "$s.WorkingDirectory = '%ROOT%';" ^
  "$s.Description = '%~3';" ^
  "if ('%ICON%' -ne '') { $s.IconLocation = '%ICON%,0' };" ^
  "$s.Save()"
if errorlevel 1 (
  echo [ERROR] Could not create %~1.
  exit /b 1
)
REM The caret escapes the ">": unescaped, cmd reads "-> Planarus.lnk" as a
REM redirect and writes a junk file of that name into the working directory
REM instead of printing anything.
echo   %~3  -^>  %~1
exit /b 0
