from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.ffmpeg import (
    FFmpegError,
    build_extract_frame_preview_command,
    is_image_file,
    is_video_file,
    probe_video_size,
    validate_binaries,
)
from core.jobs import FrameReplaceJob, ProcessingOptions
from core.timecode import TimecodeError, parse_timecode_to_seconds
from ui.dialogs.roi_picker_dialog import RoiPickerDialog


class FrameReplaceTab(QWidget):
    def __init__(
        self,
        add_to_queue_callback: Callable[[FrameReplaceJob], None],
        pick_from_selected_queue_callback: Callable[[], str],
        get_options_callback: Callable[[], ProcessingOptions],
        log_callback: Callable[[str], None],
    ):
        super().__init__()
        self._add_to_queue_callback = add_to_queue_callback
        self._pick_from_selected_queue_callback = pick_from_selected_queue_callback
        self._get_options_callback = get_options_callback
        self._log_callback = log_callback
        self._video_size: tuple[int, int] | None = None
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
        self.start_time_edit.setPlaceholderText("HH:MM:SS.mmm / MM:SS / SS")
        self.end_time_edit = QLineEdit()
        self.end_time_edit.setPlaceholderText("HH:MM:SS.mmm / MM:SS / SS")

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Full Frame", "full")
        self.mode_combo.addItem("ROI", "roi")

        self.video_size_label = QLabel("Размер видео: -")
        self.roi_status_label = QLabel("ROI status: -")

        roi_group = QGroupBox("ROI")
        roi_layout = QGridLayout(roi_group)
        self.roi_x = QSpinBox()
        self.roi_y = QSpinBox()
        self.roi_w = QSpinBox()
        self.roi_h = QSpinBox()
        for spin in (self.roi_x, self.roi_y, self.roi_w, self.roi_h):
            spin.setRange(0, 100000)
            spin.valueChanged.connect(self._refresh_roi_status)
        self.pick_roi_btn = QPushButton("Выбрать ROI")
        self.roi_preview_label = QLabel("ROI: (0,0) 0×0")
        self.roi_preview_label.setStyleSheet("color: #666;")
        roi_layout.addWidget(QLabel("x"), 0, 0)
        roi_layout.addWidget(self.roi_x, 0, 1)
        roi_layout.addWidget(QLabel("y"), 0, 2)
        roi_layout.addWidget(self.roi_y, 0, 3)
        roi_layout.addWidget(QLabel("w"), 1, 0)
        roi_layout.addWidget(self.roi_w, 1, 1)
        roi_layout.addWidget(QLabel("h"), 1, 2)
        roi_layout.addWidget(self.roi_h, 1, 3)
        roi_layout.addWidget(self.pick_roi_btn, 2, 0, 1, 2)
        roi_layout.addWidget(self.roi_preview_label, 2, 2, 1, 2)

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
        form.addRow("Mode", self.mode_combo)
        form.addRow(self.video_size_label)
        form.addRow(self.roi_status_label)
        form.addRow(QLabel("Формат времени: SS, MM:SS, HH:MM:SS(.mmm)"))
        form.addRow(roi_group)
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
        self.pick_roi_btn.clicked.connect(self._pick_roi)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.video_edit.editingFinished.connect(self._probe_video_size)

        self._on_mode_changed()

    def _browse_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select video", "", "Video files (*.mp4 *.mov *.mkv *.avi)")
        if path:
            self.video_edit.setText(path)
            self._probe_video_size()

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select image", "", "Image files (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.image_edit.setText(path)

    def _fill_video_from_queue(self) -> None:
        path = self._pick_from_selected_queue_callback()
        if path:
            self.video_edit.setText(path)
            self._probe_video_size()

    def _on_mode_changed(self) -> None:
        is_roi = self._mode() == "roi"
        self.roi_x.setEnabled(is_roi)
        self.roi_y.setEnabled(is_roi)
        self.roi_w.setEnabled(is_roi)
        self.roi_h.setEnabled(is_roi)
        self.pick_roi_btn.setEnabled(is_roi)
        self.roi_preview_label.setEnabled(is_roi)
        self._refresh_roi_status()

    def _probe_video_size(self) -> None:
        input_video = Path(self.video_edit.text().strip())
        self._video_size = None
        self.video_size_label.setText("Размер видео: -")
        if not input_video.exists():
            self._refresh_roi_status()
            return

        options = self._get_options_callback()
        ok, error = validate_binaries(options.ffmpeg_path, options.ffprobe_path)
        if not ok:
            QMessageBox.warning(self, "FFmpeg", error)
            self._log_callback(error)
            return

        try:
            w, h = probe_video_size(options.ffprobe_path, str(input_video))
        except FFmpegError as exc:
            QMessageBox.warning(self, "ffprobe error", str(exc))
            self._log_callback(str(exc))
            return

        self._video_size = (w, h)
        self.video_size_label.setText(f"Размер видео: {w}×{h}")
        self._refresh_roi_status()

    def _pick_roi(self) -> None:
        validation_error = self._validate_base_inputs()
        if validation_error:
            QMessageBox.warning(self, "Invalid input", validation_error)
            return

        options = self._get_options_callback()
        start_seconds = parse_timecode_to_seconds(self.start_time_edit.text())
        with tempfile.TemporaryDirectory(prefix="frame_replace_roi_") as tmpdir:
            preview_path = Path(tmpdir) / "preview.png"
            cmd = build_extract_frame_preview_command(
                options.ffmpeg_path,
                self.video_edit.text().strip(),
                str(preview_path),
                start_seconds,
            )
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0 or not preview_path.exists():
                message = result.stderr.strip() or "Не удалось извлечь кадр для ROI"
                QMessageBox.warning(self, "ROI", message)
                self._log_callback(message)
                return

            dialog = RoiPickerDialog(str(preview_path), self)
            if dialog.exec() != dialog.DialogCode.Accepted:
                return
            x, y, w, h = dialog.get_roi()
            if w <= 0 or h <= 0:
                QMessageBox.warning(self, "ROI", "Выделите прямоугольник ненулевого размера")
                return
            with QSignalBlocker(self.roi_x), QSignalBlocker(self.roi_y), QSignalBlocker(self.roi_w), QSignalBlocker(self.roi_h):
                self.roi_x.setValue(x)
                self.roi_y.setValue(y)
                self.roi_w.setValue(w)
                self.roi_h.setValue(h)
            self._refresh_roi_status()

    def _queue_job(self) -> None:
        validation_error = self._validate()
        if validation_error:
            QMessageBox.warning(self, "Invalid input", validation_error)
            return

        job = FrameReplaceJob(
            input_path=self.video_edit.text().strip(),
            replacement_image=self.image_edit.text().strip(),
            start_time=self.start_time_edit.text().strip(),
            start_s=parse_timecode_to_seconds(self.start_time_edit.text().strip()),
            end_time=self.end_time_edit.text().strip(),
            mode=self._mode(),
            roi_x=self.roi_x.value(),
            roi_y=self.roi_y.value(),
            roi_w=self.roi_w.value(),
            roi_h=self.roi_h.value(),
            keep_audio=self.keep_audio_checkbox.isChecked(),
            also_extract_audio=self.extract_audio_checkbox.isChecked(),
            also_extract_frames=self.extract_frames_checkbox.isChecked(),
            frame_interval_sec=self.frame_interval_spin.value(),
        )
        self._add_to_queue_callback(job)

    def _mode(self) -> str:
        return self.mode_combo.currentData() or "full"

    def _refresh_roi_status(self) -> None:
        x, y, w, h = self.roi_x.value(), self.roi_y.value(), self.roi_w.value(), self.roi_h.value()
        self.roi_preview_label.setText(f"ROI: ({x},{y}) {w}×{h}")
        if self._mode() != "roi":
            self.roi_status_label.setText("ROI status: OK")
            return
        if w <= 0 or h <= 0 or x < 0 or y < 0:
            self.roi_status_label.setText("ROI status: Invalid")
            return
        if self._video_size:
            vw, vh = self._video_size
            if x + w > vw or y + h > vh:
                self.roi_status_label.setText("ROI status: Invalid")
                return
        self.roi_status_label.setText("ROI status: OK")

    def _validate_base_inputs(self) -> str:
        input_video = Path(self.video_edit.text().strip())
        image_path = Path(self.image_edit.text().strip())

        if not input_video.exists() or not input_video.is_file() or not is_video_file(input_video):
            return "Выберите существующий входной видеофайл"
        if not image_path.exists() or not image_path.is_file() or not is_image_file(image_path):
            return "Выберите изображение PNG/JPG/WEBP"

        options = self._get_options_callback()
        ok, error_text = validate_binaries(options.ffmpeg_path, options.ffprobe_path)
        if not ok:
            return error_text
        return ""

    def _validate(self) -> str:
        base_error = self._validate_base_inputs()
        if base_error:
            return base_error

        try:
            start_seconds = parse_timecode_to_seconds(self.start_time_edit.text())
            end_seconds = parse_timecode_to_seconds(self.end_time_edit.text())
        except TimecodeError as exc:
            return str(exc)

        if start_seconds >= end_seconds:
            return "start_time должен быть меньше end_time"

        if self._video_size is None:
            self._probe_video_size()
        if self._video_size is None:
            return "Не удалось получить размеры видео через ffprobe"

        if self._mode() == "roi":
            x, y, w, h = self.roi_x.value(), self.roi_y.value(), self.roi_w.value(), self.roi_h.value()
            if w <= 0 or h <= 0 or x < 0 or y < 0:
                return "Для ROI требуется x>=0, y>=0, w>0, h>0"
            vw, vh = self._video_size
            if x + w > vw or y + h > vh:
                return f"ROI выходит за границы видео. Видео: {vw}×{vh}, ROI: x={x}, y={y}, w={w}, h={h}"

        return ""
