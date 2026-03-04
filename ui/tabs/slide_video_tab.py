from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
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
    QRadioButton,
    QDoubleSpinBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.ffmpeg import FFmpegError, is_image_file, probe_duration, validate_binaries
from core.jobs import ProcessingOptions, SlideSceneSpec, SlideVideoJob
from core.slide_video.builder import build_scene_clip_command
from core.slide_video.models import Scene
from core.slide_video.models import RESOLUTION_PRESETS
from core.slide_video.motions import motion_names
from core.slide_video.project_io import load_project, save_project


class SlideVideoTab(QWidget):
    def __init__(
        self,
        add_job_callback: Callable[[SlideVideoJob], None],
        options_callback: Callable[[], ProcessingOptions],
        log_callback: Callable[[str], None],
        start_processing_callback: Callable[[], None],
    ):
        super().__init__()
        self._add_job_callback = add_job_callback
        self._options_callback = options_callback
        self._log_callback = log_callback
        self._start_processing_callback = start_processing_callback
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        mode_group = QGroupBox("Режим таймингов")
        mode_layout = QHBoxLayout(mode_group)
        self.mode_duration_radio = QRadioButton("Режим A: по длительности")
        self.mode_timecodes_radio = QRadioButton("Режим B: по временным меткам")
        self.mode_duration_radio.setChecked(True)
        self.mode_buttons = QButtonGroup(self)
        self.mode_buttons.addButton(self.mode_duration_radio)
        self.mode_buttons.addButton(self.mode_timecodes_radio)
        mode_layout.addWidget(self.mode_duration_radio)
        mode_layout.addWidget(self.mode_timecodes_radio)

        self.scene_table = QTableWidget(0, 8)
        self.scene_table.setHorizontalHeaderLabels(["№", "Slide image", "Audio", "Duration", "Start", "End", "Camera motion", "Notes"])
        self.scene_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.scene_table.horizontalHeader().setStretchLastSection(True)
        self.scene_table.setAlternatingRowColors(True)

        scene_controls = QHBoxLayout()
        self.add_slides_btn = QPushButton("Добавить слайд(ы)")
        self.assign_audio_btn = QPushButton("Назначить аудио…")
        self.delete_scene_btn = QPushButton("Удалить сцену")
        self.move_up_btn = QPushButton("Вверх")
        self.move_down_btn = QPushButton("Вниз")
        self.autofill_btn = QPushButton("Автозаполнить длительности")
        for btn in (
            self.add_slides_btn,
            self.assign_audio_btn,
            self.delete_scene_btn,
            self.move_up_btn,
            self.move_down_btn,
            self.autofill_btn,
        ):
            scene_controls.addWidget(btn)

        output_group = QGroupBox("Output")
        output_grid = QGridLayout(output_group)
        self.output_folder_edit = QLineEdit()
        self.output_folder_btn = QPushButton("Browse...")
        self.output_name_edit = QLineEdit("slide_video")
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(list(RESOLUTION_PRESETS.keys()))
        self.scale_mode_combo = QComboBox()
        self.scale_mode_combo.addItem("Fill (crop)", "fill")
        self.scale_mode_combo.addItem("Fit (letterbox)", "fit")
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(30)
        self.playback_speed_spin = QDoubleSpinBox()
        self.playback_speed_spin.setRange(0.25, 4.0)
        self.playback_speed_spin.setDecimals(2)
        self.playback_speed_spin.setSingleStep(0.05)
        self.playback_speed_spin.setValue(1.0)
        self.playback_speed_spin.setSuffix("x")
        self.transitions_checkbox = QCheckBox("Добавлять плавные переходы (crossfade)")
        self.keep_temp_checkbox = QCheckBox("Оставить temp")
        self.keep_scene_clips_checkbox = QCheckBox("Сохранять клипы сцен")

        output_grid.addWidget(QLabel("Output folder"), 0, 0)
        output_grid.addWidget(self.output_folder_edit, 0, 1)
        output_grid.addWidget(self.output_folder_btn, 0, 2)
        output_grid.addWidget(QLabel("Output name"), 1, 0)
        output_grid.addWidget(self.output_name_edit, 1, 1, 1, 2)
        output_grid.addWidget(QLabel("Resolution preset"), 2, 0)
        output_grid.addWidget(self.resolution_combo, 2, 1, 1, 2)
        output_grid.addWidget(QLabel("Scale mode"), 3, 0)
        output_grid.addWidget(self.scale_mode_combo, 3, 1, 1, 2)
        output_grid.addWidget(QLabel("FPS"), 4, 0)
        output_grid.addWidget(self.fps_spin, 4, 1, 1, 2)
        output_grid.addWidget(QLabel("Скорость видео"), 5, 0)
        output_grid.addWidget(self.playback_speed_spin, 5, 1, 1, 2)
        output_grid.addWidget(self.transitions_checkbox, 6, 0, 1, 3)
        output_grid.addWidget(self.keep_temp_checkbox, 7, 0, 1, 3)
        output_grid.addWidget(self.keep_scene_clips_checkbox, 8, 0, 1, 3)

        preview_group = QGroupBox("Preview")
        preview_layout = QFormLayout(preview_group)
        self.preview_label = QLabel("Preview: выберите сцену")
        self.preview_btn = QPushButton("Сгенерировать предпросмотр сцены (3 сек)")
        preview_layout.addRow(self.preview_label)
        preview_layout.addRow(self.preview_btn)

        action_row = QHBoxLayout()
        self.save_project_btn = QPushButton("Save Project")
        self.load_project_btn = QPushButton("Load Project")
        self.add_to_queue_btn = QPushButton("Добавить в очередь")
        self.generate_btn = QPushButton("Сгенерировать результат")
        action_row.addWidget(self.save_project_btn)
        action_row.addWidget(self.load_project_btn)
        action_row.addWidget(self.add_to_queue_btn)
        action_row.addWidget(self.generate_btn)

        root.addWidget(mode_group)
        root.addWidget(QLabel("Сцены"))
        root.addWidget(self.scene_table)
        root.addLayout(scene_controls)
        root.addWidget(output_group)
        root.addWidget(preview_group)
        root.addLayout(action_row)

        self.add_slides_btn.clicked.connect(self._add_slides)
        self.assign_audio_btn.clicked.connect(self._assign_audio)
        self.delete_scene_btn.clicked.connect(self._delete_scene)
        self.move_up_btn.clicked.connect(lambda: self._move_scene(-1))
        self.move_down_btn.clicked.connect(lambda: self._move_scene(1))
        self.autofill_btn.clicked.connect(self._autofill_durations)
        self.output_folder_btn.clicked.connect(self._pick_output_folder)
        self.preview_btn.clicked.connect(self._generate_scene_preview)
        self.scene_table.itemSelectionChanged.connect(self._update_preview)
        self.mode_buttons.buttonClicked.connect(self._refresh_mode_columns)
        self.save_project_btn.clicked.connect(self._save_project)
        self.load_project_btn.clicked.connect(self._load_project)
        self.add_to_queue_btn.clicked.connect(self._enqueue_job)
        self.generate_btn.clicked.connect(self._generate_result)

        self._refresh_mode_columns()

    def _pick_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.output_folder_edit.setText(folder)

    def _add_slides(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Slides", "", "Images (*.png *.jpg *.jpeg *.webp)")
        for f in files:
            p = Path(f)
            if p.is_file() and is_image_file(p):
                self._append_scene_row(str(p))

    def _append_scene_row(self, slide_path: str) -> None:
        row = self.scene_table.rowCount()
        self.scene_table.insertRow(row)
        self.scene_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.scene_table.setItem(row, 1, QTableWidgetItem(slide_path))
        self.scene_table.setItem(row, 2, QTableWidgetItem(""))
        self.scene_table.setItem(row, 3, QTableWidgetItem("3.0"))
        self.scene_table.setItem(row, 4, QTableWidgetItem("0.0"))
        self.scene_table.setItem(row, 5, QTableWidgetItem("3.0"))
        motion_combo = QComboBox()
        motion_combo.addItems(motion_names())
        self.scene_table.setCellWidget(row, 6, motion_combo)
        self.scene_table.setItem(row, 7, QTableWidgetItem(""))

    def _selected_row(self) -> int:
        rows = sorted({idx.row() for idx in self.scene_table.selectedIndexes()})
        return rows[0] if rows else -1

    def _assign_audio(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select audio", "", "Audio (*.mp3 *.m4a *.wav)")
        if path:
            self.scene_table.item(row, 2).setText(path)

    def _delete_scene(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        self.scene_table.removeRow(row)
        self._renumber()

    def _move_scene(self, delta: int) -> None:
        row = self._selected_row()
        if row < 0:
            return
        target = row + delta
        if target < 0 or target >= self.scene_table.rowCount():
            return
        values = [self.scene_table.item(row, c).text() if self.scene_table.item(row, c) else "" for c in [0,1,2,3,4,5,7]]
        motion = self.scene_table.cellWidget(row, 6).currentText()
        self.scene_table.removeRow(row)
        self.scene_table.insertRow(target)
        target_cols=[0,1,2,3,4,5,7]
        for c, value in zip(target_cols, values):
            self.scene_table.setItem(target, c, QTableWidgetItem(value))
        motion_combo = QComboBox()
        motion_combo.addItems(motion_names())
        motion_combo.setCurrentText(motion)
        self.scene_table.setCellWidget(target, 6, motion_combo)
        self.scene_table.selectRow(target)
        self._renumber()

    def _renumber(self) -> None:
        for row in range(self.scene_table.rowCount()):
            self.scene_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

    def _refresh_mode_columns(self) -> None:
        duration_mode = self.mode_duration_radio.isChecked()
        self.scene_table.setColumnHidden(3, not duration_mode)
        self.scene_table.setColumnHidden(4, duration_mode)
        self.scene_table.setColumnHidden(5, duration_mode)

    def _autofill_durations(self) -> None:
        options = self._options_callback()
        ok, error = validate_binaries(options.ffmpeg_path, options.ffprobe_path)
        if not ok:
            QMessageBox.warning(self, "FFmpeg", error)
            return
        current_start = 0.0
        for row in range(self.scene_table.rowCount()):
            audio = self.scene_table.item(row, 2).text().strip() if self.scene_table.item(row, 2) else ""
            duration = None
            if not audio:
                if self._is_timecode_mode():
                    try:
                        current_start = float((self.scene_table.item(row, 5).text() if self.scene_table.item(row, 5) else str(current_start)).replace(",", "."))
                    except ValueError:
                        current_start += 3.0
                continue
            try:
                duration = max(0.1, probe_duration(options.ffprobe_path, audio))
            except FFmpegError:
                duration = None

            if duration is None:
                continue

            self.scene_table.item(row, 3).setText(f"{duration:.3f}")
            if self._is_timecode_mode():
                start = current_start
                end = current_start + duration
                self.scene_table.item(row, 4).setText(f"{start:.3f}")
                self.scene_table.item(row, 5).setText(f"{end:.3f}")
                current_start = end

    def _update_preview(self) -> None:
        row = self._selected_row()
        if row < 0:
            self.preview_label.setText("Preview: выберите сцену")
            return
        slide = self.scene_table.item(row, 1).text() if self.scene_table.item(row, 1) else ""
        motion = self.scene_table.cellWidget(row, 6).currentText()
        self.preview_label.setText(f"Preview: {Path(slide).name} | motion={motion}")

    def _generate_scene_preview(self) -> None:
        row = self._selected_row()
        if row < 0:
            QMessageBox.warning(self, "Preview", "Выберите сцену для предпросмотра")
            return

        options = self._options_callback()
        ok, error = validate_binaries(options.ffmpeg_path, options.ffprobe_path)
        if not ok:
            QMessageBox.warning(self, "FFmpeg", error)
            return

        slide = self.scene_table.item(row, 1).text().strip()
        if not slide or not Path(slide).is_file():
            QMessageBox.warning(self, "Preview", "Слайд не найден")
            return

        motion = self.scene_table.cellWidget(row, 6).currentText()
        width, height = RESOLUTION_PRESETS[self.resolution_combo.currentText()]
        preview_duration = 3.0

        with tempfile.TemporaryDirectory(prefix="slide_preview_") as tmpdir:
            preview_path = Path(tmpdir) / f"scene_{row+1:03d}_preview.mp4"
            cmd = build_scene_clip_command(
                options.ffmpeg_path,
                Scene(slide_path=slide, motion=motion),
                str(preview_path),
                width,
                height,
                self.fps_spin.value(),
                preview_duration,
                self.scale_mode_combo.currentData(),
                overwrite=True,
            )
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0 or not preview_path.exists():
                message = result.stderr.strip() or "Не удалось сгенерировать предпросмотр"
                QMessageBox.warning(self, "Preview", message)
                self._log_callback(message)
                return

            saved_preview = Path.cwd() / f"scene_{row+1:03d}_preview.mp4"
            saved_preview.write_bytes(preview_path.read_bytes())

        self._log_callback(f"Preview generated: {saved_preview}")
        self.preview_label.setText(f"Preview: {saved_preview.name}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(saved_preview)))

    def _is_timecode_mode(self) -> bool:
        return self.mode_timecodes_radio.isChecked()

    def _collect_scenes(self) -> list[SlideSceneSpec]:
        scenes: list[SlideSceneSpec] = []
        for row in range(self.scene_table.rowCount()):
            slide = self.scene_table.item(row, 1).text().strip()
            audio = self.scene_table.item(row, 2).text().strip()
            duration = float((self.scene_table.item(row, 3).text() if self.scene_table.item(row, 3) else "0").replace(",", "."))
            start = float((self.scene_table.item(row, 4).text() if self.scene_table.item(row, 4) else "0").replace(",", "."))
            end = float((self.scene_table.item(row, 5).text() if self.scene_table.item(row, 5) else "0").replace(",", "."))
            motion = self.scene_table.cellWidget(row, 6).currentText()
            notes = self.scene_table.item(row, 7).text().strip() if self.scene_table.item(row, 7) else ""
            scenes.append(
                SlideSceneSpec(
                    slide_path=slide,
                    audio_path=audio,
                    duration=duration,
                    start=start,
                    end=end,
                    motion=motion,
                    notes=notes,
                )
            )
        return scenes

    def _validate(self) -> tuple[bool, str]:
        if self.scene_table.rowCount() == 0:
            return False, "Добавьте хотя бы один слайд"
        scenes = self._collect_scenes()
        for idx, scene in enumerate(scenes, start=1):
            if not Path(scene.slide_path).is_file() or not is_image_file(Path(scene.slide_path)):
                return False, f"Сцена {idx}: некорректный путь к слайду"
            if scene.audio_path and not Path(scene.audio_path).is_file():
                return False, f"Сцена {idx}: аудио файл не найден"
            if self._is_timecode_mode():
                if scene.start < 0 or scene.end < 0 or scene.start >= scene.end:
                    return False, f"Сцена {idx}: start/end некорректны"
            elif scene.duration <= 0:
                return False, f"Сцена {idx}: duration должен быть > 0"

        if self._is_timecode_mode():
            ordered = sorted(scenes, key=lambda s: s.start)
            for left, right in zip(ordered, ordered[1:]):
                if right.start < left.end:
                    return False, "Сцены с timecodes пересекаются"
        return True, ""

    def _enqueue_job(self) -> bool:
        valid, error = self._validate()
        if not valid:
            QMessageBox.warning(self, "Validation", error)
            return False

        input_anchor = self.scene_table.item(0, 1).text().strip()
        timing_mode = "timecodes" if self._is_timecode_mode() else "duration"
        job = SlideVideoJob(
            input_path=input_anchor,
            output_root=self.output_folder_edit.text().strip(),
            output_name=self.output_name_edit.text().strip() or "slide_video",
            resolution_preset=self.resolution_combo.currentText(),
            fps=self.fps_spin.value(),
            timing_mode=timing_mode,
            scale_mode=self.scale_mode_combo.currentData(),
            playback_speed=self.playback_speed_spin.value(),
            transitions=self.transitions_checkbox.isChecked(),
            keep_temp=self.keep_temp_checkbox.isChecked(),
            keep_scene_clips=self.keep_scene_clips_checkbox.isChecked(),
            scenes=self._collect_scenes(),
        )
        self._add_job_callback(job)
        self._log_callback(f"Slide-video job queued: {job.output_name}, scenes={len(job.scenes)}")
        return True

    def _generate_result(self) -> None:
        if self._enqueue_job():
            self._start_processing_callback()

    def _serialize_job(self) -> SlideVideoJob:
        return SlideVideoJob(
            input_path=self.scene_table.item(0, 1).text().strip() if self.scene_table.rowCount() else "",
            output_root=self.output_folder_edit.text().strip(),
            output_name=self.output_name_edit.text().strip() or "slide_video",
            resolution_preset=self.resolution_combo.currentText(),
            fps=self.fps_spin.value(),
            timing_mode="timecodes" if self._is_timecode_mode() else "duration",
            scale_mode=self.scale_mode_combo.currentData(),
            playback_speed=self.playback_speed_spin.value(),
            transitions=self.transitions_checkbox.isChecked(),
            keep_temp=self.keep_temp_checkbox.isChecked(),
            keep_scene_clips=self.keep_scene_clips_checkbox.isChecked(),
            scenes=self._collect_scenes(),
        )

    def _save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save project", "", "JSON (*.json)")
        if not path:
            return
        job = self._serialize_job()
        project = {
            "settings": {
                "output_root": job.output_root,
                "output_name": job.output_name,
                "resolution_preset": job.resolution_preset,
                "fps": job.fps,
                "timing_mode": job.timing_mode,
                "scale_mode": job.scale_mode,
                "playback_speed": job.playback_speed,
                "transitions": job.transitions,
                "keep_temp": job.keep_temp,
                "keep_scene_clips": job.keep_scene_clips,
            },
            "scenes": [scene.__dict__ for scene in job.scenes],
        }
        from core.slide_video.models import Project, ProjectSettings, Scene

        save_project(
            Project(
                settings=ProjectSettings(**project["settings"]),
                scenes=[Scene(**raw) for raw in project["scenes"]],
            ),
            path,
        )

    def _load_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load project", "", "JSON (*.json)")
        if not path:
            return
        project = load_project(path)
        self.output_folder_edit.setText(project.settings.output_root)
        self.output_name_edit.setText(project.settings.output_name)
        self.resolution_combo.setCurrentText(project.settings.resolution_preset)
        self.fps_spin.setValue(project.settings.fps)
        self.scale_mode_combo.setCurrentIndex(0 if project.settings.scale_mode == "fill" else 1)
        self.playback_speed_spin.setValue(max(0.25, min(4.0, project.settings.playback_speed)))
        self.transitions_checkbox.setChecked(project.settings.transitions)
        self.keep_temp_checkbox.setChecked(project.settings.keep_temp)
        self.keep_scene_clips_checkbox.setChecked(project.settings.keep_scene_clips)
        self.mode_timecodes_radio.setChecked(project.settings.timing_mode == "timecodes")
        self.mode_duration_radio.setChecked(project.settings.timing_mode != "timecodes")
        self.scene_table.setRowCount(0)
        for scene in project.scenes:
            self._append_scene_row(scene.slide_path)
            row = self.scene_table.rowCount() - 1
            self.scene_table.item(row, 2).setText(scene.audio_path)
            self.scene_table.item(row, 3).setText(str(scene.duration))
            self.scene_table.item(row, 4).setText(str(scene.start))
            self.scene_table.item(row, 5).setText(str(scene.end))
            self.scene_table.cellWidget(row, 6).setCurrentText(scene.motion)
            self.scene_table.item(row, 7).setText(scene.notes)
        self._refresh_mode_columns()
