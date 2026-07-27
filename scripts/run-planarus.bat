@echo off
REM ============================================================================
REM Planarus - one-command Windows local development launcher
REM
REM A plain run bootstraps missing local dependencies, migrates the local DB,
REM starts FastAPI + Vite, and opens the UI only after both health checks pass.
REM It is loopback-only and always disables the external API. Add "verify" to
REM run the complete local API/web checks before launch; add "team" to opt in to
REM the account gate. Arguments can be combined in either order.
REM ============================================================================
setlocal EnableExtensions DisableDelayedExpansion
REM The script lives in scripts\; everything it drives is relative to the repo
REM root one level up. The %%~fI below resolves the ".." so ROOT stays a clean
REM absolute path. Both percent signs are doubled on purpose: cmd expands
REM parameter references inside REM lines too, and a bare %%~f there is not a
REM valid reference, so it aborted this script on every run with "The following
REM usage of the path operator in batch-parameter substitution is invalid".
for %%I in ("%~dp0..") do set "ROOT=%%~fI\"
set "API_DIR=%ROOT%apps\api"
set "API_PY=%API_DIR%\.venv\Scripts\python.exe"
set "PNPM_CMD=pnpm"
set "TEAM_MODE=0"
set "VERIFY_MODE=0"

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="team" (
  set "TEAM_MODE=1"
  shift
  goto parse_args
)
if /i "%~1"=="verify" (
  set "VERIFY_MODE=1"
  shift
  goto parse_args
)
if /i "%~1"=="help" goto usage
if /i "%~1"=="--help" goto usage
if /i "%~1"=="-h" goto usage
echo [ERROR] Unknown argument: %~1
goto usage_error

:args_done
REM --- prerequisites + first-run bootstrap -----------------------------------
call :ensure_pnpm
if errorlevel 1 goto failed
call :ensure_api_environment
if errorlevel 1 goto failed
call :ensure_web_environment
if errorlevel 1 goto failed

REM Keep every bootstrap and verification command local-only as well.
set "PLANARUS_EXTERNAL_API_ENABLED=false"
set "PLANARUS_AUTH_ENABLED=false"
set "PLANARUS_AUTH_PASSWORD_ENABLED=false"

if "%VERIFY_MODE%"=="1" (
  call :verify_checkout
  if errorlevel 1 goto failed
)

REM --- local-only runtime policy ---------------------------------------------
REM setlocal means these override only this launcher and its child processes.
REM A plain run must stay anonymous even if a parent shell had team mode set.
set "MODE=local (no sign-in)"
if "%TEAM_MODE%"=="1" (
  set "PLANARUS_AUTH_ENABLED=true"
  set "PLANARUS_AUTH_PASSWORD_ENABLED=true"
  set "MODE=team (sign-in required)"
)

REM --- pick free loopback ports ------------------------------------------------
REM netstat is built in. The colon anchor prevents :8000 matching :18000; omit
REM -p tcp so IPv6 Vite listeners are not mistaken for free ports.
call :free_port 8000 API_PORT
call :free_port 5173 WEB_PORT
if not "%API_PORT%"=="8000" echo [PORT] 8000 busy - API moved to :%API_PORT%
if not "%WEB_PORT%"=="5173" echo [PORT] 5173 busy - Web moved to :%WEB_PORT%
call :write_ports

echo.
echo Starting Planarus ^| API :%API_PORT%  Web :%WEB_PORT%  Mode: %MODE%
if "%VERIFY_MODE%"=="1" echo Verification passed; starting the local app.
echo.

REM --- start backend + frontend ------------------------------------------------
REM The API window applies migrations before uvicorn starts. A failure remains
REM visible there, while this launcher exits nonzero instead of opening a dead UI.
start "Planarus API (:%API_PORT%)" /D "%API_DIR%" cmd /k "call .venv\Scripts\activate.bat && alembic upgrade head && uvicorn app.main:app --reload --reload-dir app --port %API_PORT%"

REM vite.config.ts reads both variables; strictPort prevents a silent port drift.
set "VITE_PORT=%WEB_PORT%"
set "VITE_API_TARGET=http://localhost:%API_PORT%"
start "Planarus Web (:%WEB_PORT%)" /D "%ROOT%" cmd /k "call %PNPM_CMD% dev:web"

REM --- wait for real readiness -------------------------------------------------
set /a _tries=0
:wait_api
call :probe_url "http://localhost:%API_PORT%/health"
if not errorlevel 1 goto api_up
set /a _tries+=1
if %_tries% geq 120 (
  echo [ERROR] API did not pass /health on :%API_PORT% after 120 seconds.
  echo         Check the Planarus API window for the migration or startup error.
  goto failed
)
call :wait_one_second
goto wait_api

:api_up
echo   API is up   http://localhost:%API_PORT%
set /a _tries=0
:wait_web
call :probe_url "http://localhost:%WEB_PORT%"
if not errorlevel 1 goto web_up
set /a _tries+=1
if %_tries% geq 60 (
  echo [ERROR] Web app did not answer on :%WEB_PORT% after 60 seconds.
  echo         Check the Planarus Web window for the Vite startup error.
  goto failed
)
call :wait_one_second
goto wait_web

:web_up
echo   Web is up   http://localhost:%WEB_PORT%
start "" "http://localhost:%WEB_PORT%"
echo.
echo Planarus is ready.
echo   UI:       http://localhost:%WEB_PORT%
echo   API docs: http://localhost:%API_PORT%/docs
echo   Mode:     %MODE%
echo   Stop:     scripts\stop-planarus.bat  (or close the two Planarus windows)
exit /b 0

REM --- subroutines -------------------------------------------------------------
:ensure_pnpm
where node >nul 2>&1
if errorlevel 1 (
  call :offer_install "Node.js (LTS)" "OpenJS.NodeJS.LTS"
  if errorlevel 1 exit /b 1
  call :recheck_tool node "Node.js"
  if errorlevel 1 exit /b 1
)
where pnpm >nul 2>&1
if not errorlevel 1 (
  call pnpm --version >nul 2>&1
  if not errorlevel 1 exit /b 0
)
where corepack >nul 2>&1
if errorlevel 1 (
  echo [ERROR] pnpm is unavailable. Install Node.js 22+ with Corepack, then run: corepack enable
  exit /b 1
)
set "PNPM_CMD=corepack pnpm"
call %PNPM_CMD% --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Corepack could not run this repository's pinned pnpm version.
  echo         Run "corepack enable" once, then try again.
  exit /b 1
)
exit /b 0

:ensure_api_environment
if exist "%API_PY%" goto api_venv_ready
echo [SETUP] Creating the local Python 3.11 environment...
call :find_python311
if errorlevel 1 exit /b 1
REM These three lines are deliberately NOT inside an "if not exist (...)" block.
REM Delayed expansion is off, so every %VAR% inside a parenthesised block is
REM substituted when the block is parsed - which is before anything in it has
REM run. %BOOTSTRAP_PY% is set by :find_python311, called in that same block, so
REM it expanded to nothing and the line ran as "-m venv ...". cmd then reported
REM "'-m' is not recognized as an internal or external command" and the venv was
REM never created, on every machine that did not already have one.
%BOOTSTRAP_PY% -m venv "%API_DIR%\.venv"
if errorlevel 1 (
  echo [ERROR] Could not create apps\api\.venv.
  exit /b 1
)

:api_venv_ready
"%API_PY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] apps\api\.venv must use Python 3.11.
  echo         Recreate that environment with Python 3.11, then rerun this file.
  exit /b 1
)
"%API_PY%" -c "import alembic, fastapi, sqlmodel, uvicorn" >nul 2>&1
if not errorlevel 1 (
  if "%VERIFY_MODE%"=="0" exit /b 0
  "%API_PY%" -c "import pytest" >nul 2>&1
  if not errorlevel 1 exit /b 0
)
echo [SETUP] Installing local API and test dependencies...
pushd "%API_DIR%"
"%API_PY%" -m pip install -e ".[dev]"
set "_setup_status=%ERRORLEVEL%"
popd
if not "%_setup_status%"=="0" (
  echo [ERROR] API dependency installation failed.
  exit /b 1
)
exit /b 0

:find_python311
call :probe_python311
if not errorlevel 1 goto found_python311
call :offer_install "Python 3.11" "Python.Python.3.11"
if errorlevel 1 exit /b 1
call :probe_python311
if errorlevel 1 (
  echo [ERROR] Python 3.11 still is not answering after the install.
  echo         Close this window and run this file again - a new window picks
  echo         up the updated PATH. If it still fails, install Python 3.11 from
  echo         python.org with the Python Launcher option enabled.
  exit /b 1
)
:found_python311
set "BOOTSTRAP_PY=py -3.11"
exit /b 0

:probe_python311
py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>&1
exit /b %ERRORLEVEL%

REM --- winget bootstrap ---------------------------------------------------------
REM %1 = human name, %2 = winget package id. Installing software is not something
REM a launcher should do behind your back, so this always asks first and a plain
REM "no" leaves the machine untouched.
:offer_install
where winget >nul 2>&1
if errorlevel 1 (
  echo [ERROR] %~1 is required but was not found on PATH, and winget is not
  echo         available to install it. Install %~1 manually, then rerun this file.
  exit /b 1
)
echo.
echo [SETUP] %~1 is required and is not installed.
REM /t 30 /d N so an unattended run - CI, a scheduled task, anything without a
REM keyboard - declines after 30 seconds instead of waiting for an answer that
REM is never coming. Installing software is the answer that needs a human.
choice /c YN /n /t 30 /d N /m "        Install it now with winget? [Y/N] "
if errorlevel 2 (
  echo [ERROR] %~1 is required. Install it, then run this file again.
  exit /b 1
)
echo [SETUP] Installing %~1 - this can take a few minutes...
winget install -e --id %~2 --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo [ERROR] winget could not install %~1.
  exit /b 1
)
call :refresh_path
exit /b 0

REM Re-probe a command after installing it. %1 = executable, %2 = human name.
:recheck_tool
where %~1 >nul 2>&1
if not errorlevel 1 exit /b 0
echo [ERROR] %~2 installed, but this window cannot see it yet.
echo         Close this window and run this file again - a new window picks up
echo         the updated PATH.
exit /b 1

:refresh_path
REM winget writes the persisted environment; this already-running shell still
REM holds the PATH it started with, so a freshly installed tool is invisible
REM until the window is reopened. Rebuilding PATH from the registry avoids that
REM round trip. Those values are REG_EXPAND_SZ and can contain %%SystemRoot%%
REM style references, so "call set" is used for the extra expansion pass that
REM turns them into real directories - a plain set would store them literally.
REM
REM Appended, never assigned over the top: the persisted value does not include
REM whatever the shell that launched this script added to its own PATH, and
REM replacing would silently drop it. Duplicated entries are harmless, and this
REM runs at most once per install.
set "_sys_path="
set "_usr_path="
for /f "skip=2 tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "_sys_path=%%B"
for /f "skip=2 tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "_usr_path=%%B"
if defined _sys_path call set "PATH=%PATH%;%_sys_path%"
if defined _usr_path call set "PATH=%PATH%;%_usr_path%"
exit /b 0

:ensure_web_environment
if exist "%ROOT%apps\web\node_modules" if "%VERIFY_MODE%"=="0" exit /b 0
if "%VERIFY_MODE%"=="1" (
  echo [SETUP] Verifying locked web dependencies...
) else (
  echo [SETUP] Installing locked web dependencies...
)
pushd "%ROOT%"
call %PNPM_CMD% install --frozen-lockfile
set "_setup_status=%ERRORLEVEL%"
popd
if not "%_setup_status%"=="0" (
  echo [ERROR] Web dependency installation failed.
  exit /b 1
)
exit /b 0

:verify_checkout
echo.
echo [VERIFY] Running API tests...
pushd "%API_DIR%"
"%API_PY%" -m pytest
set "_verify_status=%ERRORLEVEL%"
popd
if not "%_verify_status%"=="0" exit /b 1

echo [VERIFY] Running web tests...
pushd "%ROOT%"
call %PNPM_CMD% test:web
set "_verify_status=%ERRORLEVEL%"
if not "%_verify_status%"=="0" goto verify_web_done
echo [VERIFY] Running web typecheck...
call %PNPM_CMD% typecheck:web
set "_verify_status=%ERRORLEVEL%"
if not "%_verify_status%"=="0" goto verify_web_done
echo [VERIFY] Building the production web app...
call %PNPM_CMD% build:web
set "_verify_status=%ERRORLEVEL%"
:verify_web_done
popd
if not "%_verify_status%"=="0" exit /b 1
exit /b 0

:write_ports
REM Record the ports for the tray. The tray cannot discover them by inspecting
REM windows: enumerating them needs either a child process (tasklist), which a
REM hidden console-less host cannot reliably spawn, or MainWindowTitle, which
REM comes back empty for these console windows often enough not to trust. A file
REM is boring and it works. The tray still TCP-probes the port before believing
REM it, so a file left behind by a crash reads as "stopped" rather than a lie.
set "STATE_DIR=%LOCALAPPDATA%\Planarus"
if not exist "%STATE_DIR%" mkdir "%STATE_DIR%" >nul 2>&1
> "%STATE_DIR%\local.ports" echo API=%API_PORT%
>>"%STATE_DIR%\local.ports" echo WEB=%WEB_PORT%
exit /b 0

:probe_url
curl -sf -o NUL --max-time 2 "%~1" >nul 2>&1
if not errorlevel 1 exit /b 0
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%~1'; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>&1
exit /b %ERRORLEVEL%

:wait_one_second
ping -n 2 127.0.0.1 >nul
exit /b 0

:free_port
setlocal EnableDelayedExpansion
set /a _p=%~1
set /a _stop=%~1+50
:free_port_probe
netstat -ano | findstr /r /c:":!_p! .*LISTENING" >nul 2>&1
if errorlevel 1 goto free_port_done
set /a _p+=1
if !_p! lss !_stop! goto free_port_probe
set /a _p=%~1
:free_port_done
endlocal & set "%~2=%_p%"
exit /b 0

:usage
echo Usage: scripts\run-planarus.bat [team] [verify]
echo.
echo   scripts\run-planarus.bat          Bootstrap and start the local anonymous app.
echo   scripts\run-planarus.bat verify   Run API and web checks, then start the app.
echo   scripts\run-planarus.bat team     Start local team mode with sign-in enabled.
echo.
echo Arguments can be combined: scripts\run-planarus.bat team verify
echo.
echo   scripts\stop-planarus.bat         Stop the running local app.
echo   scripts\planarus-tray.bat         Start/stop/open from the notification area.
echo   scripts\create-shortcuts.bat      Desktop shortcuts (run once).
exit /b 0

:usage_error
echo.
call :usage
exit /b 1

:failed
echo.
echo Planarus did not start. Fix the error above and run this file again.
exit /b 1
