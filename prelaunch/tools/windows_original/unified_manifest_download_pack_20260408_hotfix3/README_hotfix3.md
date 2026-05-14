# Unified download pack — hotfix 3

## Что исправлено
- `COCO (для seg/детекции/подписи)` больше не идёт через `tensorflow_datasets`. Загрузчик скачивает официальный bundle COCO 2017 напрямую:
  - `train2017.zip`
  - `val2017.zip`
  - `annotations_trainval2017.zip`
- `DAVIS (video segmentation)` больше не идёт через `tensorflow_datasets`. Загрузчик скачивает официальный `DAVIS-2017-trainval-480p.zip` напрямую и распаковывает его.
- TFDS остаётся для остальных builder-ов, где он у тебя уже работает.

## Почему это лучше
TFDS сам рекомендует при сбоях скачивания переходить на manual download в `manual_dir`, а для COCO и DAVIS источники известны и стабильны. В этом hotfix путь автоматизирован, но без зависимости от `download_and_prepare()` для этих двух датасетов.

## Куда кладутся файлы
- COCO: `E:\noemaforge-lab\data\Vault\download-mirror\datasets\coco-seg`
  - архивы: `raw\*.zip`
  - распаковка: `extracted\train2017`, `extracted\val2017`, `extracted\annotations`
- DAVIS: `E:\noemaforge-lab\data\Vault\download-mirror\datasets\davis-video-segmentation`
  - архив: `raw\DAVIS-2017-trainval-480p.zip`
  - распаковка: `extracted\DAVIS\...`

## Как обновиться
Замени в уже распакованной папке файл `unified_manifest_downloader.py` на новый из этого архива.

## Как продолжить
```bat
conda activate hf
cd /d E:\dwnlds\unified_download_pack

run_unified_manifest_downloader.cmd --match coco --dry-run
run_unified_manifest_downloader.cmd --match coco

run_unified_manifest_downloader.cmd --match davis --dry-run
run_unified_manifest_downloader.cmd --match davis

run_unified_manifest_downloader.cmd --verify-only
run_unified_manifest_downloader.cmd
```

## Примечания
- Предупреждение про symlink cache на Windows остаётся некритичным: это про расход места, а не про целостность файлов.
- oneDNN / `TF_ENABLE_ONEDNN_OPTS` — просто информационный лог TensorFlow.
