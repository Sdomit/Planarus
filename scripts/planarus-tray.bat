@echo off
REM ============================================================================
REM Planarus - start the system tray launcher
REM
REM Double-click this to put Planarus in the notification area. Start, stop, open
REM the app and read its logs from there; "Exit tray" stops Planarus too, since
REM in silent mode this icon is the only interface the services have.
REM ============================================================================
setlocal EnableExtensions

REM No "/b" here, deliberately. With "/b" PowerShell shares THIS script's console
REM rather than getting its own, and -WindowStyle Hidden cannot hide a window
REM PowerShell does not own - so the launcher's console window would sit on the
REM taskbar, visible, for as long as the tray ran. A console is destroyed only
REM when its last attached process exits, and that would be the tray.
REM
REM Without "/b" PowerShell gets its own console and hides it, while this
REM script's console closes normally when this script exits.
REM
REM ponytail: the flash is accepted. Removing it needs a VBScript or compiled
REM shim, a second artefact to maintain for a sub-second cosmetic gain.
start "Planarus tray" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0planarus-tray.ps1"
exit /b 0
