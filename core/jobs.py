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
