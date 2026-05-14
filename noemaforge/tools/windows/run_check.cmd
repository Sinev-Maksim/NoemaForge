@REM === NoemaForge Autodoc File Header ===
@REM File: tools/windows/run_check.cmd
@REM Purpose: Provide the script 'run_check'.
@REM Invoked by: Windows operators or wrapper scripts.
@REM Inputs: Command-line arguments and environment variables read below.
@REM Outputs: Console output and spawned helper processes.
@REM AutoDoc: refreshed 2026-04-09 (heuristic)
@REM === End NoemaForge Autodoc File Header ===




@echo off
setlocal DisableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "BRAIN_ROOT=%SCRIPT_DIR%\..\.."
for %%I in ("%BRAIN_ROOT%") do set "BRAIN_ROOT=%%~fI"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\noemaforge_check.ps1" -Root "%BRAIN_ROOT%"
exit /b %ERRORLEVEL%
