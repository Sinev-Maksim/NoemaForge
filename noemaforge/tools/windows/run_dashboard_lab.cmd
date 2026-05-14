@REM === NoemaForge Autodoc File Header ===
@REM File: tools/windows/run_dashboard_lab.cmd
@REM Purpose: Provide the script 'run_dashboard_lab'.
@REM Invoked by: Windows operators or wrapper scripts.
@REM Inputs: Command-line arguments and environment variables read below.
@REM Outputs: Console output and spawned helper processes.
@REM AutoDoc: refreshed 2026-04-09 (heuristic)
@REM === End NoemaForge Autodoc File Header ===




@echo off
setlocal DisableDelayedExpansion

REM NoemaForge Dashboard (lab mode)
REM Starts a local UI server that reads state from the LabRoot data folder.
REM
REM Usage:
REM   tools\windows\run_dashboard_lab.cmd [LAB_ROOT] [PYTHON_EXE] [PORT]
REM
REM If Python is not on PATH, pass a full path to python.exe as PYTHON_EXE,
REM or set env var NOEMAFORGE_PYTHON.

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "ROOT=%SCRIPT_DIR%\..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

REM Default LabRoot as a sibling folder (keeps the repo clean): <repo>\..\noemaforge-lab
set "LAB_ROOT=%ROOT%\..\noemaforge-lab"
for %%I in ("%LAB_ROOT%") do set "LAB_ROOT=%%~fI"
if not "%~1"=="" set "LAB_ROOT=%~1"

REM Optional explicit python.exe path
if not "%~2"=="" set "NOEMAFORGE_PYTHON=%~2"

REM Optional port
set "PORT=8787"
if not "%~3"=="" set "PORT=%~3"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\run_dashboard_lab.ps1" -RepoRoot "%ROOT%" -LabRoot "%LAB_ROOT%" -Port %PORT%
exit /b %ERRORLEVEL%
