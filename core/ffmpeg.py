from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from core.jobs import ProcessingOptions

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}


class FFmpegError(RuntimeError):
    pass


def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def detect_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def detect_ffprobe() -> Optional[str]:
    return shutil.which("ffprobe")


def ffprobe_from_ffmpeg(ffmpeg_path: str) -> str:
    ffmpeg = Path(ffmpeg_path)
    if ffmpeg.name.lower().startswith("ffmpeg"):
        return str(ffmpeg.with_name("ffprobe" + ffmpeg.suffix))
    return "ffprobe"


def validate_binaries(ffmpeg_path: str, ffprobe_path: str) -> tuple[bool, str]:
    if not shutil.which(ffmpeg_path) and not Path(ffmpeg_path).exists():
        return False, f"ffmpeg not found: {ffmpeg_path}"
    if not shutil.which(ffprobe_path) and not Path(ffprobe_path).exists():
        return False, f"ffprobe not found: {ffprobe_path}"
    return True, ""


def probe_duration(ffprobe_path: str, input_path: str) -> float:
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "ffprobe failed")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise FFmpegError("Could not parse duration from ffprobe output") from exc


def has_audio_stream(ffprobe_path: str, input_path: str) -> bool:
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


def make_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def resolve_output_root(input_path: str, options: ProcessingOptions) -> Path:
    if options.save_next_to_input:
        return Path(input_path).parent
    if options.output_folder:
        return Path(options.output_folder)
    return Path(input_path).parent


def build_audio_command(
    options: ProcessingOptions,
    input_path: str,
    output_file: str,
    force_transcode: bool = False,
) -> list[str]:
    overwrite_flag = "-y" if options.overwrite_existing else "-n"
    cmd = [options.ffmpeg_path, overwrite_flag, "-i", input_path, "-vn"]

    fmt = options.audio_format
    mode = options.audio_mode

    if fmt == "m4a":
        if mode == "copy" and not force_transcode:
            cmd += ["-acodec", "copy", output_file]
        else:
            cmd += ["-codec:a", "aac", "-b:a", "192k", output_file]
    elif fmt == "mp3":
        cmd += ["-codec:a", "libmp3lame", "-q:a", "2", output_file]
    elif fmt == "wav":
        cmd += ["-ac", "2", "-ar", "44100", output_file]
    else:
        raise FFmpegError(f"Unsupported audio format: {fmt}")

    return cmd


def build_frames_command(
    options: ProcessingOptions,
    input_path: str,
    output_pattern: str,
) -> list[str]:
    overwrite_flag = "-y" if options.overwrite_existing else "-n"
    fps_filter = f"fps=1/{options.frame_interval_sec}"

    if options.resize_mode == "1280w":
        vf = f"{fps_filter},scale=1280:-1"
    elif options.resize_mode == "1920w":
        vf = f"{fps_filter},scale=1920:-1"
    else:
        vf = fps_filter

    return [
        options.ffmpeg_path,
        overwrite_flag,
        "-i",
        input_path,
        "-vf",
        vf,
        output_pattern,
    ]


def ensure_output_dir(path: Path) -> None:
    os.makedirs(path, exist_ok=True)
