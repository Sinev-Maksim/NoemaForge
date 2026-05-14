@REM === NoemaForge Autodoc File Header ===
@REM File: tools/windows/run_firstboot.cmd
@REM Purpose: Provide the script 'run_firstboot'.
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

REM Default LabRoot as sibling folder: <repo>\..\noemaforge-lab
set "LAB_ROOT=%BRAIN_ROOT%\..\noemaforge-lab"
for %%I in ("%LAB_ROOT%") do set "LAB_ROOT=%%~fI"
if not "%~1"=="" set "LAB_ROOT=%~1"

REM Optional explicit python.exe path
set "PY_EXE=%~2"
if not "%PY_EXE%"=="" set "NOEMAFORGE_PYTHON=%PY_EXE%"

echo NoemaForge firstboot runner
echo   BrainRoot: %BRAIN_ROOT%
echo   LabRoot:   %LAB_ROOT%
if not "%PY_EXE%"=="" echo   Python:    %PY_EXE%

REM 1) Cleanup forbidden artifacts (pyc/__pycache__/cd/)
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\cleanup_forbidden_artifacts.ps1" -Root "%BRAIN_ROOT%"
if errorlevel 1 echo WARN: cleanup_forbidden_artifacts.ps1 returned %ERRORLEVEL%

REM 2) Verify seed checksums
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\verify_seed.ps1" -Root "%BRAIN_ROOT%"
if errorlevel 1 exit /b %ERRORLEVEL%

REM 3) Deep checker (uses python if found; will warn if missing)
if not "%PY_EXE%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\noemaforge_check.ps1" -Root "%BRAIN_ROOT%" -Deep -PythonExe "%PY_EXE%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\noemaforge_check.ps1" -Root "%BRAIN_ROOT%" -Deep
)
if errorlevel 1 exit /b %ERRORLEVEL%

REM 4) Prepare lab (needs python)
if not "%PY_EXE%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\noemaforge_lab.ps1" -SeedRoot "%BRAIN_ROOT%" -LabRoot "%LAB_ROOT%" -AutoManifest -PythonExe "%PY_EXE%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\noemaforge_lab.ps1" -SeedRoot "%BRAIN_ROOT%" -LabRoot "%LAB_ROOT%" -AutoManifest
)
exit /b %ERRORLEVEL%
