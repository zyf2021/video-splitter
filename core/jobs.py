from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List


class JobStatus(str, Enum):
    QUEUED = "Queued"
    PROCESSING = "Processing"
    DONE = "Done"
    DONE_NO_AUDIO = "Done (no audio)"
    SKIPPED = "Skipped"
    ERROR = "Error"
    CANCELLED = "Cancelled"


@dataclass
class ProcessingOptions:
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    output_folder: str = ""
    save_next_to_input: bool = False
    overwrite_existing: bool = False

    extract_audio: bool = True
    audio_format: str = "m4a"  # m4a|mp3|wav
    audio_mode: str = "copy"  # copy|transcode

    extract_frames: bool = True
    frame_interval_sec: int = 10
    frame_format: str = "jpg"  # jpg|png
    resize_mode: str = "original"  # original|1280w|1920w

    logo_path: str = ""
    remove_old_logo: bool = True


@dataclass
class Job:
    input_path: str
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    output_path: str = ""
    outputs: List[str] = field(default_factory=list)
    error_message: str = ""

    @property
    def filename(self) -> str:
        return Path(self.input_path).name


@dataclass
class FrameReplaceJob(Job):
    replacement_image: str = ""
    start_time: str = ""
    start_s: float = 0.0
    end_time: str = ""
    mode: str = "full"  # full|roi
    roi_x: int = 0
    roi_y: int = 0
    roi_w: int = 0
    roi_h: int = 0
    keep_audio: bool = True
    also_extract_audio: bool = False
    also_extract_frames: bool = False
    frame_interval_sec: int = 10


@dataclass
class SlideSceneSpec:
    slide_path: str
    audio_path: str = ""
    duration: float = 3.0
    start: float = 0.0
    end: float = 3.0
    motion: str = "Static (no motion)"
    notes: str = ""


@dataclass
class SlideVideoJob(Job):
    output_root: str = ""
    output_name: str = "slide_video"
    resolution_preset: str = "1920x1080 (16:9)"
    fps: int = 30
    timing_mode: str = "duration"  # duration|timecodes
    scale_mode: str = "fill"  # fill|fit
    transitions: bool = False
    keep_temp: bool = False
    keep_scene_clips: bool = False
    scenes: list[SlideSceneSpec] = field(default_factory=list)
