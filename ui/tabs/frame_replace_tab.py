from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.ffmpeg import is_image_file, is_video_file
from core.jobs import FrameReplaceJob
from core.timecode import TimecodeError, parse_timecode_to_seconds


class FrameReplaceTab(QWidget):
    def __init__(
        self,
        add_to_queue_callback: Callable[[FrameReplaceJob], None],
        pick_from_selected_queue_callback: Callable[[], str],
    ):
        super().__init__()
        self._add_to_queue_callback = add_to_queue_callback
        self._pick_from_selected_queue_callback = pick_from_selected_queue_callback
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        video_row = QWidget()
        video_layout = QHBoxLayout(video_row)
        video_layout.setContentsMargins(0, 0, 0, 0)
        self.video_edit = QLineEdit()
        self.video_browse_btn = QPushButton("Выбрать...")
        self.video_from_queue_btn = QPushButton("Из очереди")
        video_layout.addWidget(self.video_edit)
        video_layout.addWidget(self.video_browse_btn)
        video_layout.addWidget(self.video_from_queue_btn)

        image_row = QWidget()
        image_layout = QHBoxLayout(image_row)
        image_layout.setContentsMargins(0, 0, 0, 0)
        self.image_edit = QLineEdit()
        self.image_browse_btn = QPushButton("Выбрать...")
        image_layout.addWidget(self.image_edit)
        image_layout.addWidget(self.image_browse_btn)

        self.start_time_edit = QLineEdit()
        self.start_time_edit.setPlaceholderText("00:01:12.500 / 72.5")
        self.end_time_edit = QLineEdit()
        self.end_time_edit.setPlaceholderText("00:01:15.000 / 75")

        self.keep_audio_checkbox = QCheckBox("Сохранять звук (как есть)")
        self.keep_audio_checkbox.setChecked(True)
        self.extract_audio_checkbox = QCheckBox("Также извлечь аудио")
        self.extract_frames_checkbox = QCheckBox("Также сделать раскадровку")
        self.frame_interval_spin = QSpinBox()
        self.frame_interval_spin.setRange(1, 3600)
        self.frame_interval_spin.setValue(10)

        self.start_btn = QPushButton("Start Replace")

        form.addRow("Input video", video_row)
        form.addRow("Replacement image", image_row)
        form.addRow("Start time", self.start_time_edit)
        form.addRow("End time", self.end_time_edit)
        form.addRow(QLabel("Формат времени: SS, MM:SS, HH:MM:SS(.mmm)"))
        form.addRow(self.keep_audio_checkbox)
        form.addRow(self.extract_audio_checkbox)
        form.addRow(self.extract_frames_checkbox)
        form.addRow("Frame interval (sec)", self.frame_interval_spin)

        layout.addLayout(form)
        layout.addWidget(self.start_btn)
        layout.addStretch(1)

        self.video_browse_btn.clicked.connect(self._browse_video)
        self.image_browse_btn.clicked.connect(self._browse_image)
        self.video_from_queue_btn.clicked.connect(self._fill_video_from_queue)
        self.start_btn.clicked.connect(self._queue_job)

    def _browse_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select video", "", "Video files (*.mp4 *.mov *.mkv *.avi)")
        if path:
            self.video_edit.setText(path)

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select image", "", "Image files (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.image_edit.setText(path)

    def _fill_video_from_queue(self) -> None:
        path = self._pick_from_selected_queue_callback()
        if path:
            self.video_edit.setText(path)

    def _queue_job(self) -> None:
        validation_error = self._validate()
        if validation_error:
            QMessageBox.warning(self, "Invalid input", validation_error)
            return

        job = FrameReplaceJob(
            input_path=self.video_edit.text().strip(),
            replacement_image=self.image_edit.text().strip(),
            start_time=self.start_time_edit.text().strip(),
            end_time=self.end_time_edit.text().strip(),
            keep_audio=self.keep_audio_checkbox.isChecked(),
            also_extract_audio=self.extract_audio_checkbox.isChecked(),
            also_extract_frames=self.extract_frames_checkbox.isChecked(),
            frame_interval_sec=self.frame_interval_spin.value(),
        )
        self._add_to_queue_callback(job)

    def _validate(self) -> str:
        input_video = Path(self.video_edit.text().strip())
        image_path = Path(self.image_edit.text().strip())

        if not input_video.exists() or not input_video.is_file() or not is_video_file(input_video):
            return "Выберите существующий входной видеофайл"
        if not image_path.exists() or not image_path.is_file() or not is_image_file(image_path):
            return "Выберите изображение PNG/JPG/WEBP"

        try:
            start_seconds = parse_timecode_to_seconds(self.start_time_edit.text())
            end_seconds = parse_timecode_to_seconds(self.end_time_edit.text())
        except TimecodeError as exc:
            return str(exc)

        if start_seconds >= end_seconds:
            return "start_time должен быть меньше end_time"

        return ""
