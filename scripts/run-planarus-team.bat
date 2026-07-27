@echo off
REM ============================================================================
REM Planarus - start the local app with team mode (sign-in) enabled
REM
REM A wrapper around run-planarus.bat, not a second launcher: the bootstrap,
REM port selection, health checks and silent services are all the same, and the
REM only difference is that the account gate is on. It exists so that the team
REM version is a file to double-click, like the plain one, instead of an
REM argument nobody remembers typing.
REM
REM Everything else still works, because the remaining arguments are passed
REM straight through:
REM   scripts\run-planarus-team.bat verify    checks first, then starts
REM   scripts\run-planarus-team.bat visible   keeps the two service consoles
REM   scripts\run-planarus-team.bat lan       also reachable from this network,
REM                                           on this machine's LAN address
REM   scripts\run-planarus-team.bat lan 192.168.1.50
REM                                           same, with the address teammates
REM                                           type spelled out for the allowlist
REM
REM Team mode is loopback-plus-LAN with local accounts; see
REM docs/guide/lan-team-mode.md for what to set up on the first sign-in.
REM ============================================================================
call "%~dp0run-planarus.bat" team %*
exit /b %ERRORLEVEL%
