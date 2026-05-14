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
if not "%PY_EXE%"=="" set "NOEMAFORGE_PYTHON=%PY_EXE%"

REM If python path provided, pass it explicitly to PowerShell too (belt + suspenders)
if not "%PY_EXE%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\noemaforge_lab.ps1" -SeedRoot "%BRAIN_ROOT%" -LabRoot "%LAB_ROOT%" -AutoManifest -PythonExe "%PY_EXE%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\noemaforge_lab.ps1" -SeedRoot "%BRAIN_ROOT%" -LabRoot "%LAB_ROOT%" -AutoManifest
)
exit /b %ERRORLEVEL%
