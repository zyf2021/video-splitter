from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QDir, QSettings, QThread
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFileSystemModel,
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
    QTableWidget,
    QTableWidgetItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from core.ffmpeg import VIDEO_EXTENSIONS, detect_ffmpeg, ffprobe_from_ffmpeg, is_video_file
from core.jobs import Job, JobStatus, ProcessingOptions
from core.worker import ProcessingWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Splitter")
        self.resize(1280, 760)

        self.jobs: list[Job] = []
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None

        self.settings = QSettings("VideoSplitter", "VideoSplitter")

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
        self.overwrite_checkbox = QCheckBox("Overwrite existing files")

        output_layout.addRow("Output folder", output_row)
        output_layout.addRow(self.save_next_checkbox)
        output_layout.addRow(self.overwrite_checkbox)
        layout.addWidget(output_group)

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
        layout.addWidget(audio_group)

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
        frame_layout.addRow(QLabel("Naming: frame_%06d.jpg / frame_%06d.png"))
        layout.addWidget(frame_group)

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
        layout.addWidget(exec_group)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(QLabel("Log"))
        layout.addWidget(self.log_edit)

        self.ffmpeg_browse_btn.clicked.connect(self.browse_ffmpeg)
        self.output_browse_btn.clicked.connect(self.browse_output)
        self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn.clicked.connect(self.stop_processing)
        self.open_output_btn.clicked.connect(self.open_output_folder)

        return container

    def _load_settings(self) -> None:
        ffmpeg_path = self.settings.value("ffmpeg_path", detect_ffmpeg() or "ffmpeg")
        self.ffmpeg_path_edit.setText(str(ffmpeg_path))
        self.output_folder_edit.setText(str(self.settings.value("output_folder", "")))
        self.save_next_checkbox.setChecked(self.settings.value("save_next", False, type=bool))
        self.overwrite_checkbox.setChecked(self.settings.value("overwrite", False, type=bool))

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_settings()
        super().closeEvent(event)

    def _save_settings(self) -> None:
        self.settings.setValue("ffmpeg_path", self.ffmpeg_path_edit.text().strip())
        self.settings.setValue("output_folder", self.output_folder_edit.text().strip())
        self.settings.setValue("save_next", self.save_next_checkbox.isChecked())
        self.settings.setValue("overwrite", self.overwrite_checkbox.isChecked())

    def _on_tree_double_click(self, index) -> None:
        path = Path(self.fs_model.filePath(index))
        if path.is_file() and is_video_file(path):
            self._add_job(str(path))

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select videos",
            "",
            "Video files (*.mp4 *.mov *.mkv *.avi)",
        )
        for file_path in files:
            self._add_job(file_path)

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if not folder:
            return
        for child in sorted(Path(folder).iterdir()):
            if child.is_file() and child.suffix.lower() in VIDEO_EXTENSIONS:
                self._add_job(str(child))

    def _add_job(self, input_path: str) -> None:
        if any(Path(job.input_path) == Path(input_path) for job in self.jobs):
            return
        job = Job(input_path=input_path)
        self.jobs.append(job)
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        self.queue_table.setItem(row, 0, QTableWidgetItem(job.filename))
        self.queue_table.setItem(row, 1, QTableWidgetItem(job.status.value))
        self.queue_table.setItem(row, 2, QTableWidgetItem("0"))
        self.queue_table.setItem(row, 3, QTableWidgetItem(""))
        self.total_progress.setMaximum(len(self.jobs))

    def remove_selected(self) -> None:
        rows = sorted({idx.row() for idx in self.queue_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.queue_table.removeRow(row)
            self.jobs.pop(row)
        self.total_progress.setMaximum(max(1, len(self.jobs)))

    def clear_queue(self) -> None:
        if self._thread and self._thread.isRunning():
            QMessageBox.warning(self, "Busy", "Cannot clear queue while processing")
            return
        self.jobs.clear()
        self.queue_table.setRowCount(0)
        self.total_progress.reset()
        self.current_progress.reset()

    def browse_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select ffmpeg executable", "", "Executable (*.exe);;All files (*)")
        if path:
            self.ffmpeg_path_edit.setText(path)

    def browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.output_folder_edit.setText(folder)

    def _collect_options(self) -> ProcessingOptions:
        ffmpeg_path = self.ffmpeg_path_edit.text().strip() or "ffmpeg"
        return ProcessingOptions(
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_from_ffmpeg(ffmpeg_path),
            output_folder=self.output_folder_edit.text().strip(),
            save_next_to_input=self.save_next_checkbox.isChecked(),
            overwrite_existing=self.overwrite_checkbox.isChecked(),
            extract_audio=self.extract_audio_checkbox.isChecked(),
            audio_format=self.audio_format_combo.currentText(),
            audio_mode=self.audio_mode_combo.currentText(),
            extract_frames=self.extract_frames_checkbox.isChecked(),
            frame_interval_sec=self.interval_spin.value(),
            frame_format=self.image_format_combo.currentText(),
            resize_mode=self.resize_combo.currentText(),
        )

    def start_processing(self) -> None:
        if not self.jobs:
            QMessageBox.information(self, "Queue is empty", "Please add at least one video file")
            return
        if self._thread and self._thread.isRunning():
            return

        options = self._collect_options()
        if not options.extract_audio and not options.extract_frames:
            QMessageBox.warning(self, "Nothing selected", "Enable audio extraction and/or frame extraction")
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
        self._thread.finished.connect(self._thread.deleteLater)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
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
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        message = (
            f"Done: {summary['ok']}\n"
            f"Errors: {summary['error']}\n"
            f"Cancelled: {summary['cancelled']}"
        )
        self._append_log(message)
        QMessageBox.information(self, "Processing finished", message)

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
