@REM === NoemaForge Autodoc File Header ===
@REM File: tools/windows/run_all.cmd
@REM Purpose: Provide the script 'run_all'.
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

echo === NoemaForge Windows smoke: verify_seed ===
call "%SCRIPT_DIR%\run_verify.cmd"
set "RC1=%ERRORLEVEL%"

echo === NoemaForge Windows smoke: noemaforge_check ===
call "%SCRIPT_DIR%\run_check.cmd"
set "RC2=%ERRORLEVEL%"

echo === NoemaForge Windows smoke: noemaforge_lab ===
call "%SCRIPT_DIR%\run_lab.cmd"
set "RC3=%ERRORLEVEL%"

echo === Done. Exit codes: verify=%RC1% check=%RC2% lab=%RC3% ===
if not "%RC1%"=="0" exit /b %RC1%
if not "%RC2%"=="0" exit /b %RC2%
if not "%RC3%"=="0" exit /b %RC3%
exit /b 0
