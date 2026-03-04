from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

RESOLUTION_PRESETS: dict[str, tuple[int, int]] = {
    "1280x720": (1280, 720),
    "1920x1080": (1920, 1080),
    "1080x1920": (1080, 1920),
}


@dataclass
class PomodoroAssets:
    bg_title: str = ""
    bg_player: str = ""
    bg_instruction: str = ""
    bg_final: str = ""
    object_image: str = ""
    font_path: str = ""


@dataclass
class PomodoroTextSettings:
    video_title: str = "POMODORO"
    session_label: str = "Session"
    work_label: str = "time to focus"
    break_label: str = "break time"
    final_text: str = "YOU DID IT!"
    instruction_text: str = "Get ready"
    show_session_numbering: bool = True


@dataclass
class PomodoroTimerSettings:
    x: int = 460
    y: int = 170
    diameter: int = 360
    show_progress_arc: bool = True
    ring_color: str = "#ffffff"
    progress_color: str = "#d7fe4f"
    text_color: str = "#ffffff"


@dataclass
class PomodoroBeepSettings:
    enabled: bool = True
    frequency: int = 1000
    duration_ms: int = 200
    volume: float = 0.2


@dataclass
class PomodoroSettings:
    work_minutes: int = 25
    break_minutes: int = 5
    cycles: int = 4
    title_duration_sec: int = 3
    instruction_duration_sec: int = 5
    final_duration_sec: int = 5
    skip_last_break: bool = False
    fps: int = 30
    resolution_preset: str = "1280x720"
    object_scale_pct: int = 100
    object_x: int = 860
    object_y: int = 220
    keep_temp: bool = False

    @property
    def resolution(self) -> tuple[int, int]:
        return RESOLUTION_PRESETS.get(self.resolution_preset, (1280, 720))


@dataclass
class PomodoroProject:
    output_root: str = ""
    output_name: str = "pomodoro_video"
    settings: PomodoroSettings = field(default_factory=PomodoroSettings)
    assets: PomodoroAssets = field(default_factory=PomodoroAssets)
    text: PomodoroTextSettings = field(default_factory=PomodoroTextSettings)
    timer: PomodoroTimerSettings = field(default_factory=PomodoroTimerSettings)
    beep: PomodoroBeepSettings = field(default_factory=PomodoroBeepSettings)

    @property
    def display_name(self) -> str:
        return Path(self.output_name).stem or "pomodoro_video"
