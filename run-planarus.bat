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

echo Starting Planarus  ^|  API :8000   Web :5173
echo.

REM --- backend window: migrate to head, then run with hot reload --------------
REM  Force the external (ChatGPT) API OFF for local UI testing, regardless of
REM  any leftover value in your environment. setlocal keeps this out of your
REM  shell; the started window inherits it.
set "PLANARUS_EXTERNAL_API_ENABLED=false"
cd /d "%ROOT%apps\api"
REM  --reload-dir app: watch only source; without it the watcher scans .venv
REM  (thousands of files - minutes on this OneDrive-synced tree).
start "Planarus API (:8000)" cmd /k "call .venv\Scripts\activate.bat && alembic upgrade head && uvicorn app.main:app --reload --reload-dir app --port 8000"

REM --- frontend window: Vite dev server (root workspace script) ---------------
cd /d "%ROOT%"
start "Planarus Web (:5173)" cmd /k "pnpm dev:web"

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
curl -sf -o NUL --max-time 2 http://localhost:8000/health >nul 2>&1
if not errorlevel 1 goto :api_up
set /a _tries+=1
if %_tries% geq 120 (
  echo [WARN] API not answering on :8000 after 120s - check the API window for errors.
  goto :open_ui
)
ping -n 2 127.0.0.1 >nul
goto :wait_api
:api_up
echo   API is up   http://localhost:8000

set /a _tries=0
:wait_web
curl -sf -o NUL --max-time 2 http://localhost:5173 >nul 2>&1
if not errorlevel 1 goto :web_up
set /a _tries+=1
if %_tries% geq 60 (
  echo [WARN] Web not answering on :5173 after 60s - check the Web window for errors.
  goto :open_ui
)
ping -n 2 127.0.0.1 >nul
goto :wait_web
:web_up
echo   Web is up   http://localhost:5173

:open_ui
start "" http://localhost:5173

echo.
echo Opened two windows: API (:8000) and Web (:5173).
echo   UI:        http://localhost:5173
echo   API docs:  http://localhost:8000/docs
echo Stop everything by closing those two windows (or Ctrl+C in each).
endlocal
