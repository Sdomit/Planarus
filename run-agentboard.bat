@echo off
REM ============================================================================
REM  AgentBoard - local dev launcher (UI/UX testing)
REM  Starts the FastAPI backend (:8000) + Vite frontend (:5173) and opens the UI.
REM  Commands mirror docs/dev/setup.md. Vite proxies /api -> :8000, so every
REM  UI feature works with no extra config.
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

echo Starting AgentBoard  ^|  API :8000   Web :5173
echo.

REM --- backend window: migrate to head, then run with hot reload --------------
REM  Force the external (ChatGPT) API OFF for local UI testing, regardless of
REM  any leftover value in your environment. setlocal keeps this out of your
REM  shell; the started window inherits it.
set "AGENTBOARD_EXTERNAL_API_ENABLED=false"
cd /d "%ROOT%apps\api"
start "AgentBoard API (:8000)" cmd /k "call .venv\Scripts\activate.bat && alembic upgrade head && uvicorn app.main:app --reload --port 8000"

REM --- frontend window: Vite dev server (root workspace script) ---------------
cd /d "%ROOT%"
start "AgentBoard Web (:5173)" cmd /k "pnpm dev:web"

REM --- give the dev server a moment, then open the UI -------------------------
timeout /t 6 /nobreak >nul
start "" http://localhost:5173

echo.
echo Opened two windows: API (:8000) and Web (:5173).
echo   UI:        http://localhost:5173
echo   API docs:  http://localhost:8000/docs
echo Stop everything by closing those two windows (or Ctrl+C in each).
endlocal
