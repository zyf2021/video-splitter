# Video Splitter (PyQt6 + FFmpeg)

Desktop-приложение для пакетной обработки видео:
- замена эмблемы/логотипа по фиксированной области (`x=1100,y=660,w=140,h=20`) через `delogo + overlay`;
- извлечение аудио;
- извлечение кадров раз в N секунд;
- последовательная очередь с прогрессом и логом;
- новая вкладка «Замена кадра»: замена видеоряда на изображение на интервале времени.
- новая вкладка «Pomodoro Video»: генерация pomodoro-ролика и cover PNG по ассетам, таймлайну и beep-меткам.

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
   pip install PyQt6 Pillow
   ```
3. Установите FFmpeg/FFprobe:
   - **Windows**:
     1. Скачайте архив с https://ffmpeg.org/download.html (или сборку gyan.dev).
     2. Распакуйте, например, в `C:\ffmpeg`.
     3. Добавьте `C:\ffmpeg\bin` в переменную среды `PATH`.
   - **Ubuntu/Debian**:
     ```bash
     sudo apt update
     sudo apt install -y ffmpeg
     ```
   - **macOS (Homebrew)**:
     ```bash
     brew install ffmpeg
     ```

4. Проверьте установку:
   ```bash
   ffmpeg -version
   ffprobe -version
   ```


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


## Замена кадра (новая вкладка)

Во вкладке **«Замена кадра»** укажите:
- входное видео;
- изображение (PNG/JPG/WEBP);
- `start_time` и `end_time` в формате `SS`, `MM:SS` или `HH:MM:SS(.mmm)`.

Приложение выполняет ffprobe для определения размеров кадра и запускает ffmpeg с `overlay enable=between(t,start,end)` для покадровой замены на указанном интервале.
