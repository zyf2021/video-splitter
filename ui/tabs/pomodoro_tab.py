from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from core.jobs import PomodoroVideoJob
from core.pomodoro.models import (
    PomodoroAssets,
    PomodoroBeepSettings,
    PomodoroSettings,
    PomodoroTextSettings,
    PomodoroTimerSettings,
    RESOLUTION_PRESETS,
)


class PomodoroTab(QWidget):
    def __init__(
        self,
        add_job_callback: Callable[[PomodoroVideoJob], None],
        log_callback: Callable[[str], None],
        start_processing_callback: Callable[[], None] | None = None,
        stop_callback: Callable[[], None] | None = None,
    ):
        super().__init__()
        self._add_job_callback = add_job_callback
        self._log_callback = log_callback
        self._start_processing_callback = start_processing_callback
        self._stop_callback = stop_callback
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        page = QWidget()
        page_layout = QVBoxLayout(page)
        scroll.setWidget(page)

        self.sections = QToolBox()
        page_layout.addWidget(self.sections)

        assets_group = QGroupBox("Inputs (assets)")
        assets = QGridLayout(assets_group)
        self.bg_title_edit = self._path_row(assets, 0, "Title background")
        self.bg_player_edit = self._path_row(assets, 1, "Player background")
        self.bg_instruction_edit = self._path_row(assets, 2, "Instruction background")
        self.bg_final_edit = self._path_row(assets, 3, "Final background")
        self.object_edit = self._path_row(assets, 4, "Object image")
        self.font_edit = self._path_row(assets, 5, "Font (TTF)")

        timing_group = QGroupBox("Timing")
        timing = QFormLayout(timing_group)
        self.work_spin = QSpinBox(); self.work_spin.setRange(1, 240); self.work_spin.setValue(25)
        self.break_spin = QSpinBox(); self.break_spin.setRange(1, 120); self.break_spin.setValue(5)
        self.cycles_spin = QSpinBox(); self.cycles_spin.setRange(1, 20); self.cycles_spin.setValue(4)
        self.title_sec_spin = QSpinBox(); self.title_sec_spin.setRange(1, 120); self.title_sec_spin.setValue(3)
        self.instruction_sec_spin = QSpinBox(); self.instruction_sec_spin.setRange(1, 120); self.instruction_sec_spin.setValue(5)
        self.final_sec_spin = QSpinBox(); self.final_sec_spin.setRange(1, 120); self.final_sec_spin.setValue(5)
        self.skip_last_break = QCheckBox("Не делать последний Break")
        for label, widget in [
            ("Work minutes", self.work_spin),
            ("Break minutes", self.break_spin),
            ("Cycles", self.cycles_spin),
            ("Title duration sec", self.title_sec_spin),
            ("Instruction duration sec", self.instruction_sec_spin),
            ("Final duration sec", self.final_sec_spin),
        ]:
            timing.addRow(label, widget)
        timing.addRow(self.skip_last_break)

        timer_group = QGroupBox("Timer settings")
        timer = QFormLayout(timer_group)
        self.timer_x = QSpinBox(); self.timer_x.setRange(0, 10000); self.timer_x.setValue(460)
        self.timer_y = QSpinBox(); self.timer_y.setRange(0, 10000); self.timer_y.setValue(170)
        self.timer_d = QSpinBox(); self.timer_d.setRange(64, 2000); self.timer_d.setValue(360)
        self.object_x = QSpinBox(); self.object_x.setRange(0, 10000); self.object_x.setValue(860)
        self.object_y = QSpinBox(); self.object_y.setRange(0, 10000); self.object_y.setValue(220)
        self.object_scale = QSpinBox(); self.object_scale.setRange(10, 400); self.object_scale.setValue(100)
        self.progress_arc = QCheckBox("Показывать прогресс дугой"); self.progress_arc.setChecked(True)
        timer.addRow("Timer x", self.timer_x)
        timer.addRow("Timer y", self.timer_y)
        timer.addRow("Timer diameter", self.timer_d)
        timer.addRow("Object x", self.object_x)
        timer.addRow("Object y", self.object_y)
        timer.addRow("Object scale %", self.object_scale)
        timer.addRow(self.progress_arc)

        text_group = QGroupBox("Text settings")
        text = QFormLayout(text_group)
        self.title_edit = QLineEdit("POMODORO")
        self.session_edit = QLineEdit("Session")
        self.work_label_edit = QLineEdit("time to focus")
        self.break_label_edit = QLineEdit("break time")
        self.final_text_edit = QLineEdit("YOU DID IT!")
        self.instruction_text_edit = QLineEdit("Get ready")
        self.session_num_cb = QCheckBox("Session numbering on"); self.session_num_cb.setChecked(True)
        text.addRow("Title text", self.title_edit)
        text.addRow("Session label", self.session_edit)
        text.addRow("Work label", self.work_label_edit)
        text.addRow("Break label", self.break_label_edit)
        text.addRow("Final text", self.final_text_edit)
        text.addRow("Instruction text", self.instruction_text_edit)
        text.addRow(self.session_num_cb)

        beep_group = QGroupBox("Beep settings")
        beep = QFormLayout(beep_group)
        self.beep_enable = QCheckBox("Enable beep"); self.beep_enable.setChecked(True)
        self.beep_freq = QSpinBox(); self.beep_freq.setRange(100, 3000); self.beep_freq.setValue(1000)
        self.beep_dur = QSpinBox(); self.beep_dur.setRange(50, 2000); self.beep_dur.setValue(200)
        self.beep_vol = QDoubleSpinBox(); self.beep_vol.setDecimals(2); self.beep_vol.setSingleStep(0.05); self.beep_vol.setRange(0.0, 1.0); self.beep_vol.setValue(0.2)
        beep.addRow(self.beep_enable)
        beep.addRow("Frequency", self.beep_freq)
        beep.addRow("Duration ms", self.beep_dur)
        beep.addRow("Volume", self.beep_vol)

        output_group = QGroupBox("Output")
        out = QGridLayout(output_group)
        self.output_folder = QLineEdit()
        out_btn = QPushButton("Browse..."); out_btn.clicked.connect(lambda: self._browse_dir(self.output_folder))
        self.output_name = QLineEdit("pomodoro_video")
        self.resolution_combo = QComboBox(); self.resolution_combo.addItems(list(RESOLUTION_PRESETS.keys()))
        self.fps_spin = QSpinBox(); self.fps_spin.setRange(1, 60); self.fps_spin.setValue(30)
        self.keep_temp_cb = QCheckBox("Оставлять временные файлы")
        self.generate_video_btn = QPushButton("Generate Video")
        self.generate_cover_btn = QPushButton("Generate Cover")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        row_btn = QHBoxLayout(); row_btn.addWidget(self.generate_video_btn); row_btn.addWidget(self.generate_cover_btn); row_btn.addWidget(self.stop_btn)
        out.addWidget(QLabel("Output folder"), 0, 0); out.addWidget(self.output_folder, 0, 1); out.addWidget(out_btn, 0, 2)
        out.addWidget(QLabel("Output name"), 1, 0); out.addWidget(self.output_name, 1, 1, 1, 2)
        out.addWidget(QLabel("Resolution"), 2, 0); out.addWidget(self.resolution_combo, 2, 1, 1, 2)
        out.addWidget(QLabel("FPS"), 3, 0); out.addWidget(self.fps_spin, 3, 1, 1, 2)
        out.addWidget(self.keep_temp_cb, 4, 0, 1, 3)
        out.addLayout(row_btn, 5, 0, 1, 3)

        self.sections.addItem(assets_group, "1) Assets")
        self.sections.addItem(timing_group, "2) Timing")
        self.sections.addItem(timer_group, "3) Timer")
        self.sections.addItem(text_group, "4) Text")
        self.sections.addItem(beep_group, "5) Beep")
        self.sections.addItem(output_group, "6) Output")
        self.sections.setCurrentIndex(0)

        page_layout.addStretch(1)

        self.generate_video_btn.clicked.connect(lambda: self._generate(False))
        self.generate_cover_btn.clicked.connect(lambda: self._generate(True))
        self.stop_btn.clicked.connect(self._on_stop)

    def _on_stop(self) -> None:
        if self._stop_callback:
            self._stop_callback()

    def _path_row(self, grid: QGridLayout, row: int, title: str) -> QLineEdit:
        edit = QLineEdit()
        btn = QPushButton("Browse...")
        btn.clicked.connect(lambda: self._browse_file(edit))
        grid.addWidget(QLabel(title), row, 0)
        grid.addWidget(edit, row, 1)
        grid.addWidget(btn, row, 2)
        return edit

    def _browse_file(self, edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select file", "")
        if path:
            edit.setText(path)

    def _browse_dir(self, edit: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if folder:
            edit.setText(folder)

    def _validate(self) -> tuple[bool, str]:
        required = [
            (self.bg_title_edit.text().strip(), "Title background"),
            (self.bg_player_edit.text().strip(), "Player background"),
            (self.bg_final_edit.text().strip(), "Final background"),
            (self.object_edit.text().strip(), "Object image"),
        ]
        for value, title in required:
            if not value or not Path(value).is_file():
                return False, f"{title} is required"
        instruction = self.bg_instruction_edit.text().strip()
        if instruction and not Path(instruction).is_file():
            return False, "Instruction background path is invalid"
        font = self.font_edit.text().strip()
        if font and not Path(font).is_file():
            return False, "Font path is invalid"
        return True, ""

    def _generate(self, cover_only: bool) -> None:
        if self._enqueue(cover_only) and self._start_processing_callback:
            self._start_processing_callback()

    def _enqueue(self, cover_only: bool) -> bool:
        ok, err = self._validate()
        if not ok:
            QMessageBox.warning(self, "Validation", err)
            return False

        settings = PomodoroSettings(
            work_minutes=self.work_spin.value(),
            break_minutes=self.break_spin.value(),
            cycles=self.cycles_spin.value(),
            title_duration_sec=self.title_sec_spin.value(),
            instruction_duration_sec=self.instruction_sec_spin.value(),
            final_duration_sec=self.final_sec_spin.value(),
            skip_last_break=self.skip_last_break.isChecked(),
            fps=self.fps_spin.value(),
            resolution_preset=self.resolution_combo.currentText(),
            object_scale_pct=self.object_scale.value(),
            object_x=self.object_x.value(),
            object_y=self.object_y.value(),
            keep_temp=self.keep_temp_cb.isChecked(),
        )
        assets = PomodoroAssets(
            bg_title=self.bg_title_edit.text().strip(),
            bg_player=self.bg_player_edit.text().strip(),
            bg_instruction=self.bg_instruction_edit.text().strip(),
            bg_final=self.bg_final_edit.text().strip(),
            object_image=self.object_edit.text().strip(),
            font_path=self.font_edit.text().strip(),
        )
        text = PomodoroTextSettings(
            video_title=self.title_edit.text().strip() or "POMODORO",
            session_label=self.session_edit.text().strip() or "Session",
            work_label=self.work_label_edit.text().strip() or "time to focus",
            break_label=self.break_label_edit.text().strip() or "break time",
            final_text=self.final_text_edit.text().strip() or "YOU DID IT!",
            instruction_text=self.instruction_text_edit.text().strip() or "Get ready",
            show_session_numbering=self.session_num_cb.isChecked(),
        )
        timer = PomodoroTimerSettings(
            x=self.timer_x.value(),
            y=self.timer_y.value(),
            diameter=self.timer_d.value(),
            show_progress_arc=self.progress_arc.isChecked(),
        )
        beep = PomodoroBeepSettings(
            enabled=self.beep_enable.isChecked(),
            frequency=self.beep_freq.value(),
            duration_ms=self.beep_dur.value(),
            volume=self.beep_vol.value(),
        )

        job = PomodoroVideoJob(
            input_path=self.bg_title_edit.text().strip(),
            output_root=self.output_folder.text().strip(),
            output_name=self.output_name.text().strip() or "pomodoro_video",
            generate_cover_only=cover_only,
            settings=settings,
            assets=assets,
            text=text,
            timer=timer,
            beep=beep,
        )
        self._add_job_callback(job)
        self._log_callback(f"Pomodoro job queued: {job.output_name} (cover_only={cover_only})")
        return True
