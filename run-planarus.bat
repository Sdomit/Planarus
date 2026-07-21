@echo off
REM ============================================================================
REM  Planarus - local dev launcher (UI/UX testing)
REM  Starts the FastAPI backend (:8000) + Vite frontend (:5173) and opens the UI
REM  once both actually respond. Commands mirror docs/dev/setup.md. Vite proxies
REM  /api -> :8000, so every UI feature works with no extra config.
REM  NOTE: this is LOCAL dev only - the external API (ChatGPT) stays DISABLED.
REM ============================================================================
setlocal
set "ROOT=%~dp0"

REM --- preflight checks -------------------------------------------------------
if not exist "%ROOT%apps\api\.venv\Scripts\activate.bat" (
  echo [ERROR] Backend venv missing: apps\api\.venv
  echo         First-time setup ^(see docs\dev\setup.md^):
  echo           cd apps\api ^&^& python -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -e ".[dev]"
  pause
  exit /b 1
)
where pnpm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] pnpm not found on PATH. Install Node 20+ then: npm install -g pnpm
  pause
  exit /b 1
)
if not exist "%ROOT%apps\web\node_modules" (
  echo [SETUP] Web dependencies missing - running pnpm install once...
  cd /d "%ROOT%"
  call pnpm install
  if errorlevel 1 (
    echo [ERROR] pnpm install failed - fix the error above and rerun.
    pause
    exit /b 1
  )
)

REM --- optional team mode: run-planarus.bat team ------------------------------
REM  Off by default (D25/D26): a plain run stays the single-user local tool with
REM  no sign-in at all. "team" turns on the account gate and the password
REM  provider, so the first account you create claims the server as its admin
REM  and you can add viewers from Team. setlocal keeps both out of your shell.
set "MODE=local (no sign-in)"
if /i "%~1"=="team" (
  set "PLANARUS_AUTH_ENABLED=true"
  set "PLANARUS_AUTH_PASSWORD_ENABLED=true"
  set "MODE=team (sign-in required)"
)

REM --- pick free ports (parity with run-planarus.sh) --------------------------
REM  Without this, a second copy - or a leftover window - meant uvicorn failed to
REM  bind while Vite came up fine, so the browser loaded the app and every call
REM  died with "Failed to fetch". netstat is built in, so no Python probe here.
call :free_port 8000 API_PORT
call :free_port 5173 WEB_PORT
if not "%API_PORT%"=="8000" echo [PORT] 8000 busy - API moved to :%API_PORT%
if not "%WEB_PORT%"=="5173" echo [PORT] 5173 busy - Web moved to :%WEB_PORT%

echo Starting Planarus  ^|  API :%API_PORT%   Web :%WEB_PORT%   Mode: %MODE%
echo.

REM --- backend window: migrate to head, then run with hot reload --------------
REM  Force the external (ChatGPT) API OFF for local UI testing, regardless of
REM  any leftover value in your environment. setlocal keeps this out of your
REM  shell; the started window inherits it.
set "PLANARUS_EXTERNAL_API_ENABLED=false"
cd /d "%ROOT%apps\api"
REM  --reload-dir app: watch only source; without it the watcher scans .venv
REM  (thousands of files - minutes on this OneDrive-synced tree).
start "Planarus API (:%API_PORT%)" cmd /k "call .venv\Scripts\activate.bat && alembic upgrade head && uvicorn app.main:app --reload --reload-dir app --port %API_PORT%"

REM --- frontend window: Vite dev server (root workspace script) ---------------
REM  VITE_PORT also flips Vite to strictPort, so it fails loudly instead of
REM  silently landing on +1 and leaving the URL below pointing at nothing.
REM  VITE_API_TARGET repoints the /api proxy when the API moved.
cd /d "%ROOT%"
set "VITE_PORT=%WEB_PORT%"
set "VITE_API_TARGET=http://localhost:%API_PORT%"
start "Planarus Web (:%WEB_PORT%)" cmd /k "pnpm dev:web"

REM --- open the UI when both servers actually answer (max ~60s each) ----------
REM  /health only returns 2xx once migrations ran and the app imported, so this
REM  also waits out "alembic upgrade head" on first boot.
REM  localhost, not 127.0.0.1: vite may bind the IPv6 loopback (::1) only;
REM  curl on localhost tries both address families. ping is the sleep because
REM  timeout dies when stdin is redirected (scheduler / nested-script launches).
where curl >nul 2>&1
if errorlevel 1 (
  REM No curl on this box - fall back to a fixed ~8s wait.
  ping -n 9 127.0.0.1 >nul
  goto :open_ui
)

set /a _tries=0
:wait_api
curl -sf -o NUL --max-time 2 http://localhost:%API_PORT%/health >nul 2>&1
if not errorlevel 1 goto :api_up
set /a _tries+=1
if %_tries% geq 120 (
  echo [WARN] API not answering on :%API_PORT% after 120s - check the API window for errors.
  goto :open_ui
)
ping -n 2 127.0.0.1 >nul
goto :wait_api
:api_up
echo   API is up   http://localhost:%API_PORT%

set /a _tries=0
:wait_web
curl -sf -o NUL --max-time 2 http://localhost:%WEB_PORT% >nul 2>&1
if not errorlevel 1 goto :web_up
set /a _tries+=1
if %_tries% geq 60 (
  echo [WARN] Web not answering on :%WEB_PORT% after 60s - check the Web window for errors.
  goto :open_ui
)
ping -n 2 127.0.0.1 >nul
goto :wait_web
:web_up
echo   Web is up   http://localhost:%WEB_PORT%

:open_ui
start "" http://localhost:%WEB_PORT%

echo.
echo Opened two windows: API (:%API_PORT%) and Web (:%WEB_PORT%).
echo   UI:        http://localhost:%WEB_PORT%
echo   API docs:  http://localhost:%API_PORT%/docs
echo   Mode:      %MODE%   ^(run "run-planarus.bat team" for sign-in + roles^)
echo Stop everything by closing those two windows (or Ctrl+C in each).
endlocal
goto :eof

REM --- free_port START VARNAME: first free port at or above START -------------
REM  Ask netstat rather than binding: SO_REUSEADDR and Windows'
REM  0.0.0.0-vs-127.0.0.1 rules both let a bind succeed on a taken port. The
REM  colon anchor keeps :8000 from matching :18000.
REM  NO "-p tcp": that flag drops every IPv6 row, and Vite binds [::1] only -
REM  with it, a busy :5173 reads as free and the second copy dies on bind.
REM  UDP rows come along without the filter but never say LISTENING.
REM  ponytail: check-then-start races if something grabs the port in the next
REM  second - the server window logs the bind error, rerun. Same caveat the
REM  shell twin carries.
:free_port
setlocal enabledelayedexpansion
set /a _p=%~1
set /a _stop=%~1+50
:free_port_probe
netstat -ano | findstr /r /c:":!_p! .*LISTENING" >nul 2>&1
if errorlevel 1 goto :free_port_done
set /a _p+=1
if !_p! lss !_stop! goto :free_port_probe
REM  50 in a row busy: fall back to the requested port and let the server
REM  report the bind error rather than silently scanning forever.
set /a _p=%~1
:free_port_done
endlocal & set "%~2=%_p%"
goto :eof
