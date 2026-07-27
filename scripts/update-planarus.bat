@echo off
REM ============================================================================
REM Planarus - update an existing checkout safely
REM
REM Rebases onto origin/main and refreshes both dependency trees, which a plain
REM "git pull" does not do. A moved lockfile with stale node_modules fails later
REM in ways that read like application bugs, so the refresh is not optional.
REM
REM   scripts\update-planarus.bat          Update, then report what to run.
REM   scripts\update-planarus.bat start    Update, then start the app.
REM
REM Refuses to touch a dirty working tree unless you agree to stash it.
REM ============================================================================
setlocal EnableExtensions DisableDelayedExpansion
for %%I in ("%~dp0..") do set "ROOT=%%~fI\"
set "API_DIR=%ROOT%apps\api"
set "API_PY=%API_DIR%\.venv\Scripts\python.exe"
set "START_AFTER=0"

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="start" (
  set "START_AFTER=1"
  shift
  goto parse_args
)
if /i "%~1"=="help" goto usage
if /i "%~1"=="--help" goto usage
if /i "%~1"=="-h" goto usage
echo [ERROR] Unknown argument: %~1
echo.
call :usage
exit /b 1

:args_done
pushd "%ROOT%"

where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] git was not found on PATH. Install Git for Windows, then rerun.
  goto failed
)
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
  echo [ERROR] This is not a git checkout, so there is nothing to update.
  echo         A ZIP download cannot be updated in place - clone it instead.
  goto failed
)

call :ensure_clean_tree
if errorlevel 1 goto failed

echo [UPDATE] Fetching origin...
call :capture_head BEFORE
git fetch origin
if errorlevel 1 (
  echo [ERROR] git fetch failed. Check the network and your credentials.
  goto failed
)
call :capture_head AFTER

REM Both values are read outside any parenthesised block on purpose. Inside one
REM they would be substituted while the block is parsed, which is before the
REM subroutine that sets them has run - the fault that stopped run-planarus.bat
REM from ever creating its virtual environment.
if "%BEFORE%"=="%AFTER%" goto no_new_commits
call :assert_fast_forward
if errorlevel 1 goto failed

echo.
echo [UPDATE] Incoming commits:
git --no-pager log --oneline --no-decorate "%BEFORE%..%AFTER%"
echo.

:no_new_commits
echo [UPDATE] Rebasing onto origin/main...
REM Rebase, not merge: this repository is pushed to directly by more than one
REM session, and merge-pulls would add a merge commit on every overlap.
git pull --rebase origin main
if errorlevel 1 (
  echo.
  echo [ERROR] The rebase stopped, most likely on a conflict.
  echo         Resolve the files listed above, then: git rebase --continue
  echo         Or abandon the update entirely with: git rebase --abort
  goto failed
)

call :refresh_web
if errorlevel 1 goto failed
call :refresh_api
if errorlevel 1 goto failed

echo.
echo Update complete.
git --no-pager log --oneline --no-decorate -1
call :report_stash
if "%START_AFTER%"=="1" goto start_app
echo.
echo Start the app with: scripts\run-planarus.bat
popd
exit /b 0

:start_app
echo.
popd
call "%~dp0run-planarus.bat"
exit /b %ERRORLEVEL%

REM --- subroutines -------------------------------------------------------------

:ensure_clean_tree
set "TREE_DIRTY="
for /f "delims=" %%L in ('git status --porcelain 2^>nul') do set "TREE_DIRTY=1"
if not defined TREE_DIRTY exit /b 0
echo.
echo [UPDATE] This checkout has uncommitted changes:
git --no-pager status --short
echo.
echo         Rebasing on top of them is how work gets lost, so they have to be
echo         put somewhere first. Stashing keeps them and is reversible with
echo         "git stash pop".
REM Default N on timeout: an unattended run must not silently move someone's
REM work, and stopping costs nothing while a bad stash costs an afternoon.
choice /c YN /n /t 60 /d N /m "        Stash them and continue? [Y/N] "
if errorlevel 2 (
  echo [ERROR] Stopped with the working tree untouched. Commit or stash, then rerun.
  exit /b 1
)
REM -u so untracked files are included. A plain stash leaves them behind, and
REM they then collide with whatever the rebase brings in.
git stash push -u -m "update-planarus auto-stash"
if errorlevel 1 (
  echo [ERROR] git stash failed. Nothing was changed.
  exit /b 1
)
set "DID_STASH=1"
exit /b 0

:capture_head
REM Resolves origin/main into the variable named by the first argument. Empty on
REM a checkout that has never fetched, which the caller treats as "no history to
REM compare against" rather than as an error.
set "%~1="
for /f "delims=" %%H in ('git rev-parse --verify --quiet origin/main 2^>nul') do set "%~1=%%H"
exit /b 0

:assert_fast_forward
if not defined BEFORE exit /b 0
git merge-base --is-ancestor "%BEFORE%" "%AFTER%" >nul 2>&1
if not errorlevel 1 exit /b 0
echo.
echo [ERROR] origin/main was rewritten - the commit this checkout last saw is no
echo         longer part of its history. Someone force-pushed.
echo.
echo         Rebasing onto a rewritten branch can replay or duplicate commits,
echo         so this stops instead. Inspect it with:
echo             git log --oneline --left-right main...origin/main
echo.
echo         Then rebase deliberately once you know what happened.
exit /b 1

:refresh_web
echo.
echo [UPDATE] Refreshing web dependencies...
where pnpm >nul 2>&1
if errorlevel 1 goto refresh_web_corepack
call pnpm install --frozen-lockfile
if errorlevel 1 goto refresh_web_failed
exit /b 0
:refresh_web_corepack
where corepack >nul 2>&1
if errorlevel 1 (
  echo [SKIP]  Neither pnpm nor corepack is on PATH. run-planarus.bat installs
  echo         them on first run; web dependencies were not refreshed.
  exit /b 0
)
call corepack pnpm install --frozen-lockfile
if errorlevel 1 goto refresh_web_failed
exit /b 0
:refresh_web_failed
echo [ERROR] Web dependency install failed. The lockfile and node_modules now
echo         disagree, so the app may not build until this is fixed.
exit /b 1

:refresh_api
echo.
if not exist "%API_PY%" (
  echo [SKIP]  No apps\api\.venv yet. run-planarus.bat creates it on first run.
  exit /b 0
)
echo [UPDATE] Refreshing API dependencies...
pushd "%API_DIR%"
"%API_PY%" -m pip install -e ".[dev]" --quiet
set "_status=%ERRORLEVEL%"
popd
if not "%_status%"=="0" (
  echo [ERROR] API dependency install failed.
  exit /b 1
)
exit /b 0

:report_stash
if not defined DID_STASH exit /b 0
echo.
echo [NOTE]  Your changes are in the stash. Restore them with: git stash pop
exit /b 0

:usage
echo Usage: scripts\update-planarus.bat [start]
echo.
echo   scripts\update-planarus.bat         Rebase onto origin/main, refresh deps.
echo   scripts\update-planarus.bat start   Same, then launch the app.
exit /b 0

:failed
popd
echo.
echo Update did not complete. Nothing was left half-applied on purpose.
exit /b 1
