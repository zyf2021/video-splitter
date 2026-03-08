from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtCore import QDir, QSettings, QSignalBlocker, QThread
from PyQt6.QtGui import QDesktopServices, QFileSystemModel, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from core.ffmpeg import (
    LOGO_HEIGHT,
    LOGO_LEFT,
    LOGO_TOP,
    LOGO_WIDTH,
    VIDEO_EXTENSIONS,
    build_extract_preview_frame_command,
    detect_ffmpeg,
    ffprobe_from_ffmpeg,
    is_logo_file,
    is_video_file,
    probe_video_info,
    validate_binaries,
    FFmpegError,
)
from core.jobs import FrameReplaceJob, Job, PomodoroVideoJob, ProcessingOptions, SlideVideoJob
from core.timecode import TimecodeError, parse_timecode_to_seconds
from core.worker import ProcessingWorker
from ui.tabs.frame_replace_tab import FrameReplaceTab
from ui.tabs.pomodoro_tab import PomodoroTab
from ui.tabs.slide_video_tab import SlideVideoTab
from ui.widgets.video_frame_preview import VideoFramePreviewWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Splitter")
        self.resize(1320, 800)

        self.jobs: list[Job] = []
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None

        self.settings = QSettings("VideoSplitter", "VideoSplitter")
        self._logo_video_size: tuple[int, int] | None = None
        self._logo_video_duration: float = 0.0
        self._preview_temp_dir = Path("temp") / "preview"
        self._preview_frame_path = self._preview_temp_dir / "preview_frame.png"

        self._build_ui()
        self._load_settings()

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        splitter = QSplitter()
        layout.addWidget(splitter)

        left = self._build_left_panel()
        right = self._build_right_panel()

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)

    def _build_left_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        self.fs_model = QFileSystemModel(self)
        self.fs_model.setRootPath(QDir.rootPath())
        self.fs_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)

        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.setRootIndex(self.fs_model.index(QDir.homePath()))
        self.tree.doubleClicked.connect(self._on_tree_double_click)
        self.tree.setAlternatingRowColors(True)
        for col in (1, 2, 3):
            self.tree.hideColumn(col)
        layout.addWidget(QLabel("File manager"))
        layout.addWidget(self.tree)

        tree_buttons_layout = QHBoxLayout()
        self.add_selected_btn = QPushButton("Add to Queue")
        self.set_logo_from_tree_btn = QPushButton("Set as Logo")
        tree_buttons_layout.addWidget(self.add_selected_btn)
        tree_buttons_layout.addWidget(self.set_logo_from_tree_btn)
        layout.addLayout(tree_buttons_layout)

        buttons_layout = QHBoxLayout()
        self.add_files_btn = QPushButton("Add files...")
        self.add_folder_btn = QPushButton("Add folder...")
        self.remove_btn = QPushButton("Remove selected")
        self.clear_btn = QPushButton("Clear queue")
        buttons_layout.addWidget(self.add_files_btn)
        buttons_layout.addWidget(self.add_folder_btn)
        buttons_layout.addWidget(self.remove_btn)
        buttons_layout.addWidget(self.clear_btn)
        layout.addLayout(buttons_layout)

        self.queue_table = QTableWidget(0, 4)
        self.queue_table.setHorizontalHeaderLabels(["Filename", "Status", "Progress", "Output"])
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.queue_table.horizontalHeader().setStretchLastSection(True)
        self.queue_table.setAlternatingRowColors(True)
        layout.addWidget(QLabel("Queue"))
        layout.addWidget(self.queue_table)

        self.add_selected_btn.clicked.connect(self.add_selected_from_tree)
        self.set_logo_from_tree_btn.clicked.connect(self.set_logo_from_tree)
        self.add_files_btn.clicked.connect(self.add_files)
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn.clicked.connect(self.clear_queue)

        return container

    def _build_right_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        ffmpeg_group = QGroupBox("FFmpeg")
        ffmpeg_form = QGridLayout(ffmpeg_group)
        self.ffmpeg_path_edit = QLineEdit()
        self.ffmpeg_browse_btn = QPushButton("Browse...")
        ffmpeg_form.addWidget(QLabel("ffmpeg path"), 0, 0)
        ffmpeg_form.addWidget(self.ffmpeg_path_edit, 0, 1)
        ffmpeg_form.addWidget(self.ffmpeg_browse_btn, 0, 2)
        layout.addWidget(ffmpeg_group)

        output_group = QGroupBox("Output")
        output_layout = QFormLayout(output_group)
        output_row = QWidget()
        output_row_layout = QHBoxLayout(output_row)
        output_row_layout.setContentsMargins(0, 0, 0, 0)
        self.output_folder_edit = QLineEdit()
        self.output_browse_btn = QPushButton("Browse...")
        output_row_layout.addWidget(self.output_folder_edit)
        output_row_layout.addWidget(self.output_browse_btn)
        self.save_next_checkbox = QCheckBox("Save next to input file")
        output_layout.addRow("Output folder", output_row)
        output_layout.addRow(self.save_next_checkbox)
        layout.addWidget(output_group)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_logo_tab(), "Замена эмблемы")
        self.frame_replace_tab = FrameReplaceTab(
            self.add_frame_replace_job,
            self.selected_queue_video_path,
            self._collect_options,
            self._append_log,
        )
        self.slide_video_tab = SlideVideoTab(
            self.add_slide_video_job,
            self._collect_options,
            self._append_log,
            self.start_processing,
        )
        self.pomodoro_tab = PomodoroTab(self.add_pomodoro_job, self._append_log, self.stop_processing)
        self.tabs.addTab(self.frame_replace_tab, "Замена кадра")
        self.tabs.addTab(self.slide_video_tab, "Слайд-видео")
        self.tabs.addTab(self.pomodoro_tab, "Pomodoro Video")
        layout.addWidget(self.tabs)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(QLabel("Log"))
        layout.addWidget(self.log_edit)

        self.ffmpeg_browse_btn.clicked.connect(self.browse_ffmpeg)
        self.output_browse_btn.clicked.connect(self.browse_output)
        self.frame_replace_tab.start_btn.clicked.connect(self.start_processing)
        return container

    def _build_logo_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        logo_group = QGroupBox("Замена эмблемы")
        logo_layout = QFormLayout(logo_group)
        logo_row = QWidget()
        logo_row_layout = QHBoxLayout(logo_row)
        logo_row_layout.setContentsMargins(0, 0, 0, 0)
        self.logo_file_edit = QLineEdit()
        self.logo_file_edit.setReadOnly(True)
        self.logo_browse_btn = QPushButton("Выбрать...")
        logo_row_layout.addWidget(self.logo_file_edit)
        logo_row_layout.addWidget(self.logo_browse_btn)

        self.logo_video_edit = QLineEdit()
        self.logo_video_browse_btn = QPushButton("Выбрать...")
        self.logo_video_from_queue_btn = QPushButton("Из очереди")
        video_row = QWidget()
        video_row_layout = QHBoxLayout(video_row)
        video_row_layout.setContentsMargins(0, 0, 0, 0)
        video_row_layout.addWidget(self.logo_video_edit)
        video_row_layout.addWidget(self.logo_video_browse_btn)
        video_row_layout.addWidget(self.logo_video_from_queue_btn)

        coords_widget = QWidget()
        coords_layout = QGridLayout(coords_widget)
        coords_layout.setContentsMargins(0, 0, 0, 0)
        self.logo_x_spin = QSpinBox()
        self.logo_y_spin = QSpinBox()
        self.logo_w_spin = QSpinBox()
        self.logo_h_spin = QSpinBox()
        for spin in (self.logo_x_spin, self.logo_y_spin, self.logo_w_spin, self.logo_h_spin):
            spin.setRange(0, 100000)
            spin.valueChanged.connect(self._on_logo_geometry_changed)
        self.logo_x_spin.setValue(LOGO_LEFT)
        self.logo_y_spin.setValue(LOGO_TOP)
        self.logo_w_spin.setValue(LOGO_WIDTH)
        self.logo_h_spin.setValue(LOGO_HEIGHT)
        coords_layout.addWidget(QLabel("X"), 0, 0)
        coords_layout.addWidget(self.logo_x_spin, 0, 1)
        coords_layout.addWidget(QLabel("Y"), 0, 2)
        coords_layout.addWidget(self.logo_y_spin, 0, 3)
        coords_layout.addWidget(QLabel("W"), 1, 0)
        coords_layout.addWidget(self.logo_w_spin, 1, 1)
        coords_layout.addWidget(QLabel("H"), 1, 2)
        coords_layout.addWidget(self.logo_h_spin, 1, 3)

        self.keep_aspect_checkbox = QCheckBox("Сохранять пропорции")
        self.keep_aspect_checkbox.setChecked(True)
        self.delogo_checkbox = QCheckBox("Удалять старую эмблему (delogo)")
        self.delogo_checkbox.setChecked(True)

        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_widget = VideoFramePreviewWidget()
        self.preview_widget.setMinimumHeight(280)
        self.coords_label = QLabel("Coords: —")
        self.video_size_label = QLabel("Video size: -")
        self.geometry_status_label = QLabel("Geometry: -")
        self.geometry_status_label.setStyleSheet("color: #666;")
        preview_controls = QHBoxLayout()
        self.refresh_frame_btn = QPushButton("Обновить кадр")
        self.frame_time_edit = QLineEdit("00:00:01.000")
        self.show_frame_btn = QPushButton("Показать")
        preview_controls.addWidget(self.refresh_frame_btn)
        preview_controls.addWidget(QLabel("Время кадра"))
        preview_controls.addWidget(self.frame_time_edit)
        preview_controls.addWidget(self.show_frame_btn)

        preview_layout.addWidget(self.preview_widget)
        preview_layout.addWidget(self.coords_label)
        preview_layout.addWidget(self.video_size_label)
        preview_layout.addWidget(self.geometry_status_label)
        preview_layout.addLayout(preview_controls)

        logo_layout.addRow("Logo file", logo_row)
        logo_layout.addRow("Input video", video_row)
        logo_layout.addRow("Geometry", coords_widget)
        logo_layout.addRow(self.keep_aspect_checkbox)
        logo_layout.addRow(self.delogo_checkbox)
        logo_layout.addRow(preview_group)

        audio_group = QGroupBox("Audio extraction")
        audio_layout = QFormLayout(audio_group)
        self.extract_audio_checkbox = QCheckBox("Extract audio")
        self.extract_audio_checkbox.setChecked(True)
        self.audio_format_combo = QComboBox()
        self.audio_format_combo.addItems(["m4a", "mp3", "wav"])
        self.audio_mode_combo = QComboBox()
        self.audio_mode_combo.addItems(["copy", "transcode"])
        audio_layout.addRow(self.extract_audio_checkbox)
        audio_layout.addRow("Format", self.audio_format_combo)
        audio_layout.addRow("Mode", self.audio_mode_combo)

        frame_group = QGroupBox("Frame extraction")
        frame_layout = QFormLayout(frame_group)
        self.extract_frames_checkbox = QCheckBox("Extract frames")
        self.extract_frames_checkbox.setChecked(True)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 3600)
        self.interval_spin.setValue(10)
        self.image_format_combo = QComboBox()
        self.image_format_combo.addItems(["jpg", "png"])
        self.resize_combo = QComboBox()
        self.resize_combo.addItems(["original", "1280w", "1920w"])
        frame_layout.addRow(self.extract_frames_checkbox)
        frame_layout.addRow("Interval seconds", self.interval_spin)
        frame_layout.addRow("Image format", self.image_format_combo)
        frame_layout.addRow("Resize", self.resize_combo)

        exec_group = QGroupBox("Execution")
        exec_layout = QVBoxLayout(exec_group)
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.open_output_btn = QPushButton("Open output folder")
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.open_output_btn)

        self.current_progress = QProgressBar()
        self.current_progress.setFormat("Current file: %p%")
        self.total_progress = QProgressBar()
        self.total_progress.setFormat("Queue: %v/%m")

        exec_layout.addLayout(btn_row)
        exec_layout.addWidget(self.current_progress)
        exec_layout.addWidget(self.total_progress)

        layout.addWidget(logo_group)
        layout.addWidget(audio_group)
        layout.addWidget(frame_group)
        layout.addWidget(exec_group)
        layout.addStretch(1)

        self.logo_browse_btn.clicked.connect(self.browse_logo)
        self.logo_video_browse_btn.clicked.connect(self.browse_logo_video)
        self.logo_video_from_queue_btn.clicked.connect(self._fill_logo_video_from_queue)
        self.logo_video_edit.editingFinished.connect(self._on_logo_video_changed)
        self.refresh_frame_btn.clicked.connect(self._refresh_logo_preview)
        self.show_frame_btn.clicked.connect(self._refresh_logo_preview)
        self.preview_widget.hoverPointChanged.connect(self._on_preview_hover)
        self.preview_widget.hoverLeftImage.connect(lambda: self.coords_label.setText("Coords: —"))
        self.preview_widget.clickedPoint.connect(self._on_preview_click)
        self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn.clicked.connect(self.stop_processing)
        self.open_output_btn.clicked.connect(self.open_output_folder)
        return tab

    def _load_settings(self) -> None:
        ffmpeg_path = self.settings.value("ffmpeg_path", detect_ffmpeg() or "ffmpeg")
        self.ffmpeg_path_edit.setText(str(ffmpeg_path))
        self.output_folder_edit.setText(str(self.settings.value("output_folder", "")))
        self.save_next_checkbox.setChecked(self.settings.value("save_next", False, type=bool))
        self.logo_file_edit.setText(str(self.settings.value("logo_path", "")))
        self.logo_video_edit.setText(str(self.settings.value("logo_video_path", "")))
        self.delogo_checkbox.setChecked(self.settings.value("remove_old_logo", True, type=bool))
        self.keep_aspect_checkbox.setChecked(self.settings.value("logo_keep_aspect", True, type=bool))
        self.logo_x_spin.setValue(self.settings.value("logo_x", LOGO_LEFT, type=int))
        self.logo_y_spin.setValue(self.settings.value("logo_y", LOGO_TOP, type=int))
        self.logo_w_spin.setValue(self.settings.value("logo_w", LOGO_WIDTH, type=int))
        self.logo_h_spin.setValue(self.settings.value("logo_h", LOGO_HEIGHT, type=int))
        self._on_logo_video_changed()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_settings()
        self._clear_preview_cache()
        super().closeEvent(event)

    def _save_settings(self) -> None:
        self.settings.setValue("ffmpeg_path", self.ffmpeg_path_edit.text().strip())
        self.settings.setValue("output_folder", self.output_folder_edit.text().strip())
        self.settings.setValue("save_next", self.save_next_checkbox.isChecked())
        self.settings.setValue("logo_path", self.logo_file_edit.text().strip())
        self.settings.setValue("logo_video_path", self.logo_video_edit.text().strip())
        self.settings.setValue("remove_old_logo", self.delogo_checkbox.isChecked())
        self.settings.setValue("logo_keep_aspect", self.keep_aspect_checkbox.isChecked())
        self.settings.setValue("logo_x", self.logo_x_spin.value())
        self.settings.setValue("logo_y", self.logo_y_spin.value())
        self.settings.setValue("logo_w", self.logo_w_spin.value())
        self.settings.setValue("logo_h", self.logo_h_spin.value())

    def _on_tree_double_click(self, index) -> None:
        path = Path(self.fs_model.filePath(index))
        if path.is_file() and is_video_file(path):
            self._add_job(Job(input_path=str(path)))

    def add_selected_from_tree(self) -> None:
        index = self.tree.currentIndex()
        if not index.isValid():
            return
        path = Path(self.fs_model.filePath(index))
        if path.is_file() and is_video_file(path):
            self._add_job(Job(input_path=str(path)))

    def set_logo_from_tree(self) -> None:
        index = self.tree.currentIndex()
        if not index.isValid():
            return
        path = Path(self.fs_model.filePath(index))
        if path.is_file() and is_logo_file(path):
            self.logo_file_edit.setText(str(path))
        else:
            QMessageBox.warning(self, "Invalid logo", "Select PNG or WEBP file for logo")

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select videos", "", "Video files (*.mp4 *.mov *.mkv *.avi)")
        for file_path in files:
            self._add_job(Job(input_path=file_path))

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if not folder:
            return
        for child in sorted(Path(folder).iterdir()):
            if child.is_file() and child.suffix.lower() in VIDEO_EXTENSIONS:
                self._add_job(Job(input_path=str(child)))

    def add_frame_replace_job(self, job: FrameReplaceJob) -> None:
        self._add_job(job)

    def add_slide_video_job(self, job: SlideVideoJob) -> None:
        self._add_job(job)

    def add_pomodoro_job(self, job: PomodoroVideoJob) -> None:
        self._add_job(job)

    def _add_job(self, job: Job) -> None:
        if not isinstance(job, SlideVideoJob):
            if any(Path(existing.input_path) == Path(job.input_path) and type(existing) is type(job) for existing in self.jobs):
                return
        self.jobs.append(job)
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        if isinstance(job, FrameReplaceJob):
            title = f"[FrameReplace] {job.filename}"
        elif isinstance(job, SlideVideoJob):
            title = f"[SlideVideo] {job.output_name}"
        elif isinstance(job, PomodoroVideoJob):
            title = f"[Pomodoro] {job.output_name}"
        else:
            title = job.filename
        self.queue_table.setItem(row, 0, QTableWidgetItem(title))
        self.queue_table.setItem(row, 1, QTableWidgetItem(job.status.value))
        self.queue_table.setItem(row, 2, QTableWidgetItem("0"))
        self.queue_table.setItem(row, 3, QTableWidgetItem(""))
        self.total_progress.setMaximum(max(1, len(self.jobs)))
        self._update_start_button_state()

    def selected_queue_video_path(self) -> str:
        rows = sorted({idx.row() for idx in self.queue_table.selectedIndexes()})
        if not rows:
            return ""
        return self.jobs[rows[0]].input_path

    def remove_selected(self) -> None:
        rows = sorted({idx.row() for idx in self.queue_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.queue_table.removeRow(row)
            self.jobs.pop(row)
        self.total_progress.setMaximum(max(1, len(self.jobs)))
        self._update_start_button_state()

    def clear_queue(self) -> None:
        if self._thread and self._thread.isRunning():
            QMessageBox.warning(self, "Busy", "Cannot clear queue while processing")
            return
        self.jobs.clear()
        self.queue_table.setRowCount(0)
        self.total_progress.reset()
        self.current_progress.reset()
        self._update_start_button_state()

    def browse_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select ffmpeg executable", "", "Executable (*.exe);;All files (*)")
        if path:
            self.ffmpeg_path_edit.setText(path)

    def browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.output_folder_edit.setText(folder)

    def browse_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select logo", "", "Images (*.png *.webp)")
        if path:
            self.logo_file_edit.setText(path)

    def browse_logo_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select preview video", "", "Video files (*.mp4 *.mov *.mkv *.avi)")
        if path:
            self.logo_video_edit.setText(path)
            self._on_logo_video_changed()

    def _fill_logo_video_from_queue(self) -> None:
        path = self.selected_queue_video_path()
        if path:
            self.logo_video_edit.setText(path)
            self._on_logo_video_changed()

    def _on_logo_video_changed(self) -> None:
        self._logo_video_size = None
        self._logo_video_duration = 0.0
        self.video_size_label.setText("Video size: -")
        self.geometry_status_label.setText("Geometry: -")
        video_path = Path(self.logo_video_edit.text().strip())
        if not video_path.exists() or not video_path.is_file() or not is_video_file(video_path):
            self.preview_widget.set_frame_pixmap(QPixmap())
            self._sync_logo_overlay()
            self._update_start_button_state()
            return

        options = self._collect_options()
        ok, err = validate_binaries(options.ffmpeg_path, options.ffprobe_path)
        if not ok:
            self._append_log(err)
            self.geometry_status_label.setText("Geometry: ffmpeg/ffprobe not configured")
            self._update_start_button_state()
            return

        try:
            w, h, duration = probe_video_info(options.ffprobe_path, str(video_path))
        except FFmpegError as exc:
            self._append_log(str(exc))
            self.geometry_status_label.setText("Geometry: failed to probe video")
            self._update_start_button_state()
            return

        self._logo_video_size = (w, h)
        self._logo_video_duration = duration
        self.video_size_label.setText(f"Video size: {w}x{h}")
        self._refresh_logo_preview()

    def _refresh_logo_preview(self) -> None:
        video_path = Path(self.logo_video_edit.text().strip())
        if not video_path.exists() or not video_path.is_file():
            return
        options = self._collect_options()
        try:
            frame_time = parse_timecode_to_seconds(self.frame_time_edit.text().strip())
        except TimecodeError as exc:
            QMessageBox.warning(self, "Timecode", str(exc))
            return
        if frame_time < 0:
            frame_time = 0.0
        if self._logo_video_duration > 0:
            frame_time = min(frame_time, self._logo_video_duration)

        self._preview_temp_dir.mkdir(parents=True, exist_ok=True)
        cmd = build_extract_preview_frame_command(options.ffmpeg_path, str(video_path), frame_time, str(self._preview_frame_path))
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not self._preview_frame_path.exists():
            msg = result.stderr.strip() or "Не удалось извлечь кадр"
            QMessageBox.warning(self, "Preview", msg)
            self._append_log(msg)
            return

        pixmap = QPixmap(str(self._preview_frame_path))
        self.preview_widget.set_frame_pixmap(pixmap)
        self._sync_logo_overlay()
        self._update_start_button_state()

    def _on_preview_hover(self, x: int, y: int) -> None:
        self.coords_label.setText(f"Coords: x={x}, y={y}")

    def _on_preview_click(self, x: int, y: int) -> None:
        with QSignalBlocker(self.logo_x_spin), QSignalBlocker(self.logo_y_spin):
            self.logo_x_spin.setValue(x)
            self.logo_y_spin.setValue(y)
        self._on_logo_geometry_changed()

    def _on_logo_geometry_changed(self) -> None:
        self._sync_logo_overlay()
        self._update_start_button_state()

    def _sync_logo_overlay(self) -> None:
        x, y, w, h = self.logo_x_spin.value(), self.logo_y_spin.value(), self.logo_w_spin.value(), self.logo_h_spin.value()
        is_invalid = not self._is_logo_geometry_valid()
        self.preview_widget.set_overlay_rect(x, y, w, h, invalid=is_invalid)
        error_style = "QSpinBox { border: 1px solid #d93025; }"
        normal_style = ""
        for spin in (self.logo_x_spin, self.logo_y_spin, self.logo_w_spin, self.logo_h_spin):
            spin.setStyleSheet(error_style if is_invalid else normal_style)
        if is_invalid:
            self.geometry_status_label.setText("Geometry: Invalid")
            self.geometry_status_label.setStyleSheet("color: #d93025;")
        else:
            self.geometry_status_label.setText("Geometry: OK")
            self.geometry_status_label.setStyleSheet("color: #188038;")

    def _is_logo_geometry_valid(self) -> bool:
        x, y, w, h = self.logo_x_spin.value(), self.logo_y_spin.value(), self.logo_w_spin.value(), self.logo_h_spin.value()
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            return False
        if self._logo_video_size:
            vw, vh = self._logo_video_size
            return x + w <= vw and y + h <= vh
        return True

    def _update_start_button_state(self) -> None:
        has_logo_jobs = any(not isinstance(job, (FrameReplaceJob, SlideVideoJob, PomodoroVideoJob)) for job in self.jobs)
        can_start = (not has_logo_jobs) or self._is_logo_geometry_valid()
        self.start_btn.setEnabled(can_start and bool(self.jobs))

    def _clear_preview_cache(self) -> None:
        if self._preview_temp_dir.exists():
            shutil.rmtree(self._preview_temp_dir, ignore_errors=True)

    def _collect_options(self) -> ProcessingOptions:
        ffmpeg_path = self.ffmpeg_path_edit.text().strip() or "ffmpeg"
        return ProcessingOptions(
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_from_ffmpeg(ffmpeg_path),
            output_folder=self.output_folder_edit.text().strip(),
            save_next_to_input=self.save_next_checkbox.isChecked(),
            overwrite_existing=True,
            extract_audio=self.extract_audio_checkbox.isChecked(),
            audio_format=self.audio_format_combo.currentText(),
            audio_mode=self.audio_mode_combo.currentText(),
            extract_frames=self.extract_frames_checkbox.isChecked(),
            frame_interval_sec=self.interval_spin.value(),
            frame_format=self.image_format_combo.currentText(),
            resize_mode=self.resize_combo.currentText(),
            logo_path=self.logo_file_edit.text().strip(),
            remove_old_logo=self.delogo_checkbox.isChecked(),
            logo_x=self.logo_x_spin.value(),
            logo_y=self.logo_y_spin.value(),
            logo_w=self.logo_w_spin.value(),
            logo_h=self.logo_h_spin.value(),
            logo_keep_aspect=self.keep_aspect_checkbox.isChecked(),
        )

    def start_processing(self) -> None:
        if not self.jobs:
            QMessageBox.information(self, "Queue is empty", "Please add at least one video file")
            return

        if self._thread is not None:
            try:
                if self._thread.isRunning():
                    return
            except RuntimeError:
                # Underlying Qt object can be deleted after deleteLater().
                pass
            self._thread = None
            self._worker = None

        options = self._collect_options()
        if any(not isinstance(job, (FrameReplaceJob, SlideVideoJob, PomodoroVideoJob)) for job in self.jobs):
            if not options.logo_path:
                QMessageBox.warning(self, "Logo missing", "Please select logo PNG/WEBP file")
                return
            if not self._is_logo_geometry_valid():
                QMessageBox.warning(self, "Invalid geometry", "Проверьте X/Y/W/H: прямоугольник должен быть внутри кадра")
                return

        self.total_progress.setMaximum(len(self.jobs))
        self.total_progress.setValue(0)
        self.current_progress.setValue(0)

        self._thread = QThread(self)
        self._worker = ProcessingWorker(self.jobs, options)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.signals.log.connect(self._append_log)
        self._worker.signals.job_updated.connect(self._update_job_row)
        self._worker.signals.queue_progress.connect(self._update_queue_progress)
        self._worker.signals.finished.connect(self._on_finished)
        self._worker.signals.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)

        self.start_btn.setEnabled(False)
        self.frame_replace_tab.start_btn.setEnabled(False)
        self.slide_video_tab.generate_btn.setEnabled(False)
        self.slide_video_tab.add_to_queue_btn.setEnabled(False)
        self.pomodoro_tab.generate_video_btn.setEnabled(False)
        self.pomodoro_tab.generate_cover_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.pomodoro_tab.stop_btn.setEnabled(True)
        self._thread.start()

    def stop_processing(self) -> None:
        if self._worker:
            self._worker.request_stop()
            self._append_log("Stop requested")

    def _append_log(self, text: str) -> None:
        self.log_edit.appendPlainText(text)

    def _update_job_row(self, row: int, job: Job) -> None:
        self.queue_table.item(row, 1).setText(job.status.value)
        self.queue_table.item(row, 2).setText(str(job.progress))
        self.queue_table.item(row, 3).setText(job.output_path)
        self.current_progress.setValue(job.progress)

    def _update_queue_progress(self, done: int, total: int) -> None:
        self.total_progress.setMaximum(max(1, total))
        self.total_progress.setValue(done)

    def _on_finished(self, summary: dict) -> None:
        self._update_start_button_state()
        self.frame_replace_tab.start_btn.setEnabled(True)
        self.slide_video_tab.generate_btn.setEnabled(True)
        self.slide_video_tab.add_to_queue_btn.setEnabled(True)
        self.pomodoro_tab.generate_video_btn.setEnabled(True)
        self.pomodoro_tab.generate_cover_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.pomodoro_tab.stop_btn.setEnabled(False)
        message = f"Done: {summary['ok']}\nErrors: {summary['error']}\nCancelled: {summary['cancelled']}"

        error_jobs = [job for job in self.jobs if job.status.value == "Error" and job.error_message]
        if error_jobs:
            self._append_log("Ошибки по задачам:")
            for job in error_jobs:
                self._append_log(f"- {job.filename}: {job.error_message}")
            first_error = error_jobs[0]
            message += f"\n\nПервый текст ошибки:\n{first_error.filename}: {first_error.error_message.splitlines()[0]}"

        self._append_log(message)
        QMessageBox.information(self, "Processing finished", message)

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None

    def open_output_folder(self) -> None:
        target = self.output_folder_edit.text().strip()
        if not target and self.jobs:
            target = str(Path(self.jobs[0].input_path).parent)
        if not target:
            return
        path = Path(target)
        if not path.exists():
            os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(path.as_uri())
