# Анализ архитектуры проекта `video-splitter`

## 1) Общая структура

Проект — desktop-приложение на **PyQt6** с движком обработки через **FFmpeg/FFprobe**.
Архитектурно он разделён на:

- **UI-слой** (`ui/*`): окно, вкладки и диалоги ввода параметров.
- **Core-слой** (`core/*`): модели задач, сборка ffmpeg-команд, воркер очереди, парсинг времени.
- **Feature-модули**:
  - `core/slide_video/*` + `ui/tabs/slide_video_tab.py` — генерация ролика из слайдов;
  - `core/pomodoro/*` + `ui/tabs/pomodoro_tab.py` — генерация pomodoro-видео и cover.

## 2) Ключевые функции, классы и методы

### Точка входа
- `main.py`:
  - `main()` — запуск GUI и ветка `--test-run`.
  - `run_test_mode()` — быстрый сценарий прогонки одной задачи без GUI.
  - `_configure_windows_qt_runtime()` — защитная настройка Qt/OpenGL для Windows.

### Модели задач
- `core/jobs.py`:
  - `JobStatus` — состояния задач (Queued, Processing, Done, Error и т.д.).
  - `ProcessingOptions` — глобальные параметры ffmpeg/выхода/аудио/кадров/логотипа.
  - `Job` — базовая задача очереди.
  - `FrameReplaceJob`, `SlideVideoJob`, `PomodoroVideoJob` — специализированные типы задач.
  - `SlideSceneSpec` — сцена для слайдового видео.

### FFmpeg-слой
- `core/ffmpeg.py`:
  - проверка и поиск бинарников: `detect_ffmpeg()`, `detect_ffprobe()`, `validate_binaries()`;
  - probe-операции: `probe_duration()`, `probe_video_size()`, `has_audio_stream()`;
  - генерация команд:
    - `build_overlay_command()`, `build_delogo_overlay_command()`;
    - `build_frame_replace_command()`;
    - `build_audio_command()`, `build_frames_command()`;
    - `build_extract_frame_preview_command()`;
  - утилиты путей: `make_unique_path()`, `make_unique_dir()`, `resolve_output_root()`;
  - геометрия логотипа: `fit_logo_rect()`.

### Очередь и выполнение
- `core/worker.py`:
  - `WorkerSignals` — Qt-сигналы лога, прогресса и завершения.
  - `ProcessingWorker.run()` — главный цикл обработки очереди, маршрутизация по типам задач.
  - методы обработки:
    - `_process_logo_job()`;
    - `_process_frame_replace_job()`;
    - `_process_slide_video_job()`;
    - `_process_pomodoro_job()`.
  - системные методы:
    - `_run_ffmpeg()` — запуск процесса + парсинг прогресса;
    - `_update_progress()`;
    - `request_stop()` — мягкая остановка;
    - `_finalize_job()` — финальный статус/выходы.

### Слайдовый видеоконструктор
- `core/slide_video/models.py`:
  - `Scene`, `ProjectSettings`, `Project`.
  - вычисление длительности: `Scene.effective_duration()`, `Project.total_duration`.
- `core/slide_video/builder.py`:
  - `build_scene_clip_command()` — создание клипа сцены, включая zoom/pan motion.
  - `build_video_concat_command()`, `build_audio_scene_command()`, `build_audio_concat_command()`, `build_mux_command()`.
  - `write_concat_list()` и `scene_duration()`.
- `core/slide_video/motions.py`:
  - `MotionPreset`, `motion_names()`, `get_motion_preset()`.

### Pomodoro-конструктор
- `core/pomodoro/models.py`:
  - `PomodoroSettings`, `PomodoroAssets`, `PomodoroTextSettings`, `PomodoroTimerSettings`, `PomodoroBeepSettings`, `PomodoroProject`.
- `core/pomodoro/timeline.py`:
  - `PomodoroScene`, `PomodoroTimeline`, `build_timeline()`.
- `core/pomodoro/ffmpeg_builder.py`:
  - сборка команд клипов, склейки, генерации beep-трека, финального mux.
- `core/pomodoro/timer_render.py`:
  - рендер последовательности PNG-таймера для сцен.

### UI-слой
- `ui/main_window.py`:
  - `MainWindow` — каркас приложения, очередь, старт/стоп worker, сохранение настроек.
- `ui/tabs/frame_replace_tab.py`:
  - `FrameReplaceTab` — валидация входных параметров, режим full/ROI, enqueue задачи.
- `ui/tabs/slide_video_tab.py`:
  - `SlideVideoTab` — визуальный конструктор сцен, предпросмотр, сериализация/десериализация проекта.
- `ui/tabs/pomodoro_tab.py`:
  - `PomodoroTab` — форма ассетов/таймингов/таймера/текста/beep и enqueue задач.
- `ui/dialogs/roi_picker_dialog.py`:
  - диалог выбора ROI для замены участка кадра.

## 3) Сильные стороны архитектуры

1. **Функциональная декомпозиция**: отделены core-модули и UI.
2. **Явные dataclass-модели**: удобно сериализовать/валидировать состояние задач.
3. **Единый pipeline-исполнитель** (`ProcessingWorker`) для разных режимов.
4. **Команды ffmpeg собираются функциями** (а не строками в UI), что улучшает тестируемость.
5. **Расширяемость**: новые типы задач уже вписываются в паттерн `Job` + обработчик в worker.

## 4) Точки роста и потенциальные риски

1. **God-object в `ProcessingWorker`**
   - Один класс знает слишком много про 4 бизнес-сценария.
   - Побочный эффект: сложнее тестировать и безопасно менять логику.

2. **UI и orchestration частично смешаны**
   - Вкладки делают и валидацию, и формирование доменных моделей, и orchestration enqueue.

3. **Слабая изоляция ошибок процессов**
   - Есть `FFmpegError`, но не хватает единого слоя типизированных ошибок с кодами/категориями.

4. **Ограниченное тестовое покрытие**
   - В репозитории нет полноценного набора unit/integration тестов, только `test_one.py` для ручного smoke.

5. **Конфигурация и пресеты частично захардкожены**
   - Параметры кодеков/битрейтов/CRF и дефолты координат разбросаны по модулям.

## 5) Практические варианты улучшения

### A. Рефакторинг слоя выполнения (высокий приоритет)
- Ввести интерфейс/протокол обработчика задачи (`JobHandler`), например:
  - `can_handle(job)`, `process(job, context)`.
- Разнести обработчики по файлам:
  - `handlers/logo_handler.py`, `handlers/frame_replace_handler.py`, ...
- `ProcessingWorker` оставить как оркестратор очереди и сигналов.

### B. Сервисный слой над ffmpeg
- Создать класс `FFmpegRunner`:
  - запуск команды,
  - парсинг прогресса,
  - унифицированное формирование ошибок/логов.
- Отделить "build command" от "execute command" полностью.

### C. Единая схема валидации
- Централизовать валидацию job-моделей в `core/validation.py`.
- UI-вкладки должны только отображать ошибку, а не держать доменные правила внутри виджетов.

### D. Тестирование
- Добавить unit-тесты на:
  - парсер timecode;
  - сборщики ffmpeg-команд (snapshot-style сравнение списков аргументов);
  - расчёты timeline/duration.
- Добавить lightweight integration-тесты на `ProcessingWorker` с мокнутым runner.

### E. Конфигурация/наблюдаемость
- Вынести кодек-профили в конфиг (JSON/YAML/dataclass presets).
- Добавить структурированные логи (уровень, job_id, этап, длительность этапа).
- Добавить метрики этапов (время на render/concat/mux).

### F. UX и производительность
- Для тяжёлых сценариев (Pomodoro/Slide) сделать отдельные прогресс-стадии в UI.
- Добавить предварительную оценку длительности рендера и объёма диска.
- Поддержать паузу/резюмирование long-run задач (если feasible через сегментацию пайплайна).

## 6) Рекомендуемый поэтапный план

1. **Шаг 1**: покрыть тестами `timecode`, `timeline`, `ffmpeg command builders`.
2. **Шаг 2**: выделить `FFmpegRunner` и унифицировать ошибки.
3. **Шаг 3**: декомпозировать `ProcessingWorker` на handler-ы.
4. **Шаг 4**: централизовать валидацию job-моделей.
5. **Шаг 5**: внедрить конфигурационные пресеты и улучшенные логи/метрики.

Такой путь даст быстрый выигрыш в стабильности и ускорит дальнейшее расширение функционала.
