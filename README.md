# Video Splitter (PyQt6 + FFmpeg)

Desktop-приложение для пакетной обработки видео:
- замена эмблемы/логотипа по фиксированной области (`x=1100,y=280,w=140,h=380`) через `delogo + overlay`;
- извлечение аудио;
- извлечение кадров раз в N секунд;
- последовательная очередь с прогрессом и логом.

## Структура проекта

- `main.py` — запуск GUI и `--test-run` режим.
- `test_one.py` — быстрый запуск тестового сценария.
- `ui/main_window.py` — интерфейс `QMainWindow` + файловый менеджер.
- `core/jobs.py` — dataclass-модели задач и настроек.
- `core/ffmpeg.py` — сборка ffmpeg/ffprobe команд (overlay/delogo/audio/frames).
- `core/worker.py` — фоновая обработка очереди в `QThread`.

## Установка

1. Установите Python 3.10+.
2. Установите зависимости:
   ```bash
   pip install PyQt6
   ```
3. Установите FFmpeg/FFprobe и добавьте их в `PATH`.

## Запуск

```bash
python main.py
```

## Выходная структура

После обработки каждого видео создаётся папка `<VideoName>/` (или `<VideoName>_01`, `<VideoName>_02`, ...):

```text
output_root/
  MyVideo/
    original.mp4
    MyVideo_logo.mp4
    frames/
      frame_000001.jpg
      ...
    audio.m4a
```

Исходный файл переносится в `original.*` только после успешного завершения этапов.

## Тестовый сценарий

Положите входной файл в `samples/input.mp4`, затем:

```bash
python test_one.py
```

или

```bash
python main.py --test-run
```
