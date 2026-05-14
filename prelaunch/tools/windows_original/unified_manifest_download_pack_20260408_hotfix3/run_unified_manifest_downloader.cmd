@echo off
setlocal

if not defined HF_HOME set "HF_HOME=E:\hf-home"
if not defined HF_HUB_CACHE set "HF_HUB_CACHE=%HF_HOME%\hub"
if not defined HF_XET_CACHE set "HF_XET_CACHE=%HF_HOME%\xet"
if not defined HF_HUB_DISABLE_XET set "HF_HUB_DISABLE_XET=1"
if not defined HF_HUB_DISABLE_SYMLINKS_WARNING set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
if not defined VAULT_ROOT set "VAULT_ROOT=E:\noemaforge-lab\data\Vault"

python "%~dp0unified_manifest_downloader.py" ^
  --manifest "%~dp0download_targets_runtime_manifest.json" ^
  --target-root "%VAULT_ROOT%\download-mirror" ^
  --cache-dir "%HF_HUB_CACHE%" ^
  --tfds-data-dir "%VAULT_ROOT%\datasets-tfds" ^
  --web-download-root "%VAULT_ROOT%\datasets-web" ^
  %*
