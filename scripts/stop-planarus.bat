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

REM Ports first, titles second. Silent mode starts the services with no window
REM at all, and tasklist's WINDOWTITLE filter cannot match a window that does
REM not exist - so a title-only stop would report "was not running" while the
REM app kept serving. The port record run-planarus.bat writes is the one handle
REM that exists in both modes.
call :kill_by_ports
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

:kill_by_ports
REM Reads what run-planarus.bat recorded - the ports, and in silent mode the id
REM of the process hosting each service - and kills both. Absent file means
REM nothing was started by the launcher, which is not an error: the title pass
REM below still covers a session started before this record existed.
set "_ports_file=%LOCALAPPDATA%\Planarus\local.ports"
if not exist "%_ports_file%" exit /b 0
REM Recorded process ids first, ports second. The id is the top of the tree and
REM the port is a leaf of it, so doing it the other way round both reports the
REM same service twice and, for the API, kills a worker that is immediately
REM replaced. After the tree is gone the port pass finds nothing and stays quiet.
for /f "usebackq tokens=1,2 delims==" %%K in ("%_ports_file%") do call :kill_pid_entry "%%L" "%%K"
for /f "usebackq tokens=1,2 delims==" %%K in ("%_ports_file%") do call :kill_port_entry "%%L" "%%K"
exit /b 0

:kill_pid_entry
if /i "%~2"=="API_PID" call :kill_pid_tree "%~1" "API"
if /i "%~2"=="WEB_PID" call :kill_pid_tree "%~1" "Web"
exit /b 0

:kill_port_entry
if /i "%~2"=="API" call :kill_port "%~1" "API"
if /i "%~2"=="WEB" call :kill_port "%~1" "Web"
exit /b 0

:kill_pid_tree
REM %1 = process id the launcher recorded, %2 = label.
REM Stopping the API by port alone does not work: the pid holding :8000 is the
REM uvicorn worker, and its --reload supervisor holds no port, so netstat cannot
REM see it, it survives the kill and starts another worker. This pid is the cmd
REM that hosts the pair, and /T takes the tree with it.
REM The image name is checked first because this record outlives a crash and
REM Windows reuses process ids - killing whoever inherited the number is not on.
if "%~1"=="" exit /b 0
tasklist /FI "PID eq %~1" /FI "IMAGENAME eq cmd.exe" 2>nul | find /i "cmd.exe" >nul 2>&1
if errorlevel 1 exit /b 0
taskkill /PID %~1 /T /F >nul 2>&1
if errorlevel 1 exit /b 0
echo   Stopped the Planarus %~2 service.
set "_stopped=1"
exit /b 0

:kill_port
REM %1 = port, %2 = label. The colon anchor and the LISTENING guard keep :8000
REM from matching :18000 and from matching an outbound connection to the port.
if "%~1"=="" exit /b 0
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":%~1 .*LISTENING" 2^>nul') do call :kill_pid "%%P" "%~2"
exit /b 0

:kill_pid
REM /T so the child tree goes too: uvicorn and vite are children of the cmd that
REM was launched, and killing only the parent leaves them holding the port.
if "%~1"=="" exit /b 0
if "%~1"=="0" exit /b 0
taskkill /PID %~1 /T /F >nul 2>&1
if errorlevel 1 exit /b 0
echo   Stopped the Planarus %~2 service.
set "_stopped=1"
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
