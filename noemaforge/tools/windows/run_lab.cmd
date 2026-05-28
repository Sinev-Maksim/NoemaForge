@REM === NoemaForge Autodoc File Header ===
@REM File: tools/windows/run_lab.cmd
@REM Purpose: Provide the script 'run_lab'.
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

REM Default LabRoot as a sibling folder (keeps the repo clean): <repo>\..\noemaforge-lab
set "LAB_ROOT=%BRAIN_ROOT%\..\noemaforge-lab"
for %%I in ("%LAB_ROOT%") do set "LAB_ROOT=%%~fI"
if not "%~1"=="" set "LAB_ROOT=%~1"

REM Optional explicit python.exe path (if python is not on PATH)
set "PY_EXE=%~2"
if "%PY_EXE%"=="" set "PY_EXE=%NOEMAFORGE_PYTHON%"
if "%PY_EXE%"=="" set "PY_EXE=py"

"%PY_EXE%" "%BRAIN_ROOT%\tools\prep\noemaforge_prep_core.py" lab --repo-root "%BRAIN_ROOT%" --lab-root "%LAB_ROOT%" --auto-manifest
exit /b %ERRORLEVEL%
