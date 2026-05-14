@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem =========================
rem Edit only this block if needed
rem =========================
set "ROOT=E:\noemaforge-lab\data\Library\inbox"
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "COOLDOWN_MINUTES=15"
set "MAX_FAILS_PER_SOURCE=8"
set "AUTO_INSTALL_AWS=1"

set "RUN_OAPEN=1"
set "RUN_OAPEN_CHAPTERS=0"
set "RUN_OPENALEX=1"
set "OPENALEX_MODE=works"
set "RUN_PMC_METADATA=1"
set "RUN_PMC_COMM=1"
set "RUN_PMC_NONCOMM=1"
set "RUN_PMC_PHE=0"

rem OAPEN fail-fast tuning for source-level cooldowns
set "OAPEN_DELAY=0.8"
set "OAPEN_RETRIES=2"
set "OAPEN_TIMEOUT=120"
set "OAPEN_BACKOFF=2.0"
set "OAPEN_MAX_RETRY_WAIT=20"

rem =========================
rem Python selection
rem =========================
set "PYEXE="
if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PYEXE=%CONDA_PREFIX%\python.exe"
if not defined PYEXE if exist "C:\ProgramData\anaconda3\python.exe" set "PYEXE=C:\ProgramData\anaconda3\python.exe"
if not defined PYEXE if exist "C:\Users\%USERNAME%\anaconda3\python.exe" set "PYEXE=C:\Users\%USERNAME%\anaconda3\python.exe"
if not defined PYEXE for /f "delims=" %%I in ('where python 2^>nul') do if not defined PYEXE set "PYEXE=%%I"

if not defined PYEXE (
  echo Could not find Python. Activate your Anaconda environment or install Anaconda.
  exit /b 1
)

echo Using Python: "%PYEXE%"
"%PYEXE%" "%SCRIPT_DIR%\library_pipeline_orchestrator.py"
exit /b %ERRORLEVEL%
