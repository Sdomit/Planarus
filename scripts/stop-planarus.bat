@echo off
REM ============================================================================
REM Planarus - stop the local Windows development app
REM
REM Closes the two windows run-planarus.bat opened. Safe to run when nothing is
REM running: it reports that and exits 0, so a desktop shortcut never presents
REM an error for the ordinary case of "it was already stopped".
REM ============================================================================
setlocal EnableExtensions

REM Matched on window title, not on port, because the ports move when 8000 or
REM 5173 are busy - the titles carry whichever port was chosen, so the trailing
REM wildcard is what makes this work in both cases.
REM
REM /T kills the child tree as well. Without it the uvicorn and vite processes
REM would die while their host cmd windows stayed open, which looks to the user
REM like the app is still running.
set "_stopped=0"

call :kill_window "Planarus API*" "API"
call :kill_window "Planarus Web*" "Web"

REM Drop the port record run-planarus.bat left for the tray. Harmless if absent,
REM and leaving it behind would only make the tray probe a port nothing answers.
del /q "%LOCALAPPDATA%\Planarus\local.ports" >nul 2>&1

echo.
if "%_stopped%"=="0" (
  echo Planarus was not running.
) else (
  echo Planarus stopped.
)
exit /b 0

:kill_window
REM %1 = window title pattern, %2 = label for the message.
tasklist /FI "WINDOWTITLE eq %~1" 2>nul | find /i "cmd.exe" >nul 2>&1
if errorlevel 1 exit /b 0
taskkill /FI "WINDOWTITLE eq %~1" /T /F >nul 2>&1
if errorlevel 1 (
  echo [WARN] Found the Planarus %~2 window but could not close it.
  exit /b 0
)
echo   Stopped the Planarus %~2 window.
set "_stopped=1"
exit /b 0
