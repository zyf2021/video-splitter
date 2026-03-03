from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


RESOLUTION_PRESETS: dict[str, tuple[int, int]] = {
    "1920x1080 (16:9)": (1920, 1080),
    "1080x1920 (9:16)": (1080, 1920),
    "1080x1080 (1:1)": (1080, 1080),
    "1280x720": (1280, 720),
    "720x1280": (720, 1280),
}

TIMING_MODE_DURATION = "duration"
TIMING_MODE_TIMECODES = "timecodes"


@dataclass
class Scene:
    slide_path: str
    audio_path: str = ""
    duration: float = 3.0
    start: float = 0.0
    end: float = 3.0
    motion: str = "Static (no motion)"
    notes: str = ""

    def effective_duration(self, mode: str) -> float:
        if mode == TIMING_MODE_TIMECODES:
            return self.end - self.start
        return self.duration


@dataclass
class ProjectSettings:
    output_root: str = ""
    output_name: str = "slide_video"
    resolution_preset: str = "1920x1080 (16:9)"
    fps: int = 30
    timing_mode: str = TIMING_MODE_DURATION
    scale_mode: str = "fill"
    transitions: bool = False
    keep_temp: bool = False
    keep_scene_clips: bool = False

    @property
    def resolution(self) -> tuple[int, int]:
        return RESOLUTION_PRESETS.get(self.resolution_preset, (1920, 1080))


@dataclass
class Project:
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    scenes: list[Scene] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return sum(scene.effective_duration(self.settings.timing_mode) for scene in self.scenes)

    @property
    def display_name(self) -> str:
        return Path(self.settings.output_name).stem or "slide_video"
