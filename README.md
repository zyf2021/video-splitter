# Video Splitter (PyQt6 + FFmpeg)

Небольшое desktop-приложение для Windows (и других ОС с Python 3.10+) для:
- извлечения аудио из видео;
- нарезки кадров каждые N секунд;
- последовательной обработки очереди с логом и прогрессом.

## Структура проекта

- `main.py` — запуск GUI и `--test-run` режим.
- `test_one.py` — быстрый запуск тестового сценария.
- `ui/main_window.py` — интерфейс `QMainWindow`.
- `core/jobs.py` — dataclass-модели задач и настроек.
- `core/ffmpeg.py` — утилиты, проверки, сборка ffmpeg/ffprobe команд.
- `core/worker.py` — фоновая обработка задач в `QThread`.

## Установка

1. Установите Python 3.10+.
2. Установите зависимости:
   ```bash
   pip install PyQt6
   ```
3. Установите FFmpeg:
   - Скачайте сборку с официального сайта: https://ffmpeg.org/download.html
   - Добавьте папку с `ffmpeg.exe` и `ffprobe.exe` в `PATH`
   - Либо укажите путь к `ffmpeg.exe` в интерфейсе (блок **FFmpeg**).

## Запуск

```bash
python main.py
```

## Где что в UI

- **Левая колонка**
  - `QTreeView` (проводник)
  - Кнопки: `Add files...`, `Add folder...`, `Remove selected`, `Clear queue`
  - Таблица очереди: `Filename`, `Status`, `Progress`, `Output`
- **Правая колонка**
  - **FFmpeg**: путь к `ffmpeg`
  - **Output**: папка, чекбоксы `Save next to input file`, `Overwrite existing files`
  - **Audio extraction**: включение, формат (`m4a/mp3/wav`), режим (`copy/transcode`)
  - **Frame extraction**: включение, интервал, формат изображения, resize
  - **Execution**: `Start`, `Stop`, `Open output folder`, прогресс текущего и общего выполнения
  - **Log**: `QPlainTextEdit` со временем и сообщениями

## Тестовый сценарий (без UI)

Положите входной файл в `samples/input.mp4`, затем:

```bash
python test_one.py
```

или

```bash
python main.py --test-run
```

Результаты будут в `samples/out/`, итог печатается в консоль.


## Если приложение падает сразу после запуска в Windows (код 0xC0000409)

- В `main.py` уже включен software OpenGL режим для Qt (`QT_OPENGL=software`),
  это снижает риск падений из-за видеодрайвера.
- Обновите/переустановите драйвер видеокарты и Microsoft Visual C++ Redistributable 2015-2022.
- Проверьте, что версии пакетов согласованы:
  ```bash
  pip install --upgrade pip
  pip install --upgrade PyQt6 PyQt6-Qt6 PyQt6-sip
  ```
- Для диагностики плагинов Qt можно запустить:
  ```bash
  set QT_DEBUG_PLUGINS=1
  python main.py
  ```

