@echo off
REM ============================================================================
REM Planarus - start the system tray launcher
REM
REM Double-click this to put Planarus in the notification area. Start, stop and
REM open the app from there; "Exit tray" removes the icon and leaves whatever is
REM running alone.
REM ============================================================================
setlocal EnableExtensions

REM -WindowStyle Hidden applies to PowerShell's own window, not to this one, so
REM the console is handed off with "start /b" and this script exits immediately
REM rather than sitting in the background holding a window open.
REM
REM ponytail: a brief console flash is accepted here. Removing it entirely needs
REM a VBScript or a compiled shim, which is a second artefact to maintain for a
REM sub-second cosmetic gain.
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0planarus-tray.ps1"
exit /b 0
