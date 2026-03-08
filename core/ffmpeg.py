from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from core.jobs import ProcessingOptions

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}
LOGO_EXTENSIONS = {".png", ".webp"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

LOGO_LEFT = 1750
LOGO_TOP = 1040
LOGO_WIDTH = 140
LOGO_HEIGHT = 40


def fit_logo_rect(video_width: int, video_height: int, strict_inside: bool = False) -> tuple[int, int, int, int]:
    """Return logo rectangle clamped to current video dimensions.

    strict_inside=True keeps the rectangle strictly inside the frame bounds,
    which avoids ffmpeg delogo failures on bottom/right borders.
    """
    width = max(1, min(LOGO_WIDTH, video_width))
    height = max(1, min(LOGO_HEIGHT, video_height))
    x = max(0, min(LOGO_LEFT, video_width - 1))
    y = max(0, min(LOGO_TOP, video_height - 1))

    if x + width > video_width:
        x = max(0, video_width - width)
    if y + height > video_height:
        y = max(0, video_height - height)

    if strict_inside:
        if x + width >= video_width:
            if x > 0:
                x -= 1
            elif width > 1:
                width -= 1
        if y + height >= video_height:
            if y > 0:
                y -= 1
            elif height > 1:
                height -= 1

    return x, y, width, height


class FFmpegError(RuntimeError):
    pass


def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def is_logo_file(path: Path) -> bool:
    return path.suffix.lower() in LOGO_EXTENSIONS


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


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


def probe_video_size(ffprobe_path: str, input_path: str) -> tuple[int, int]:
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "ffprobe size probe failed")

    try:
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
    except Exception as exc:  # noqa: BLE001
        raise FFmpegError("Could not parse width/height from ffprobe output") from exc

    if width <= 0 or height <= 0:
        raise FFmpegError("Invalid video dimensions from ffprobe")
    return width, height

def probe_video_info(ffprobe_path: str, input_path: str) -> tuple[int, int, float]:
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:format=duration",
        "-of",
        "json",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "ffprobe info probe failed")

    try:
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(payload["format"]["duration"])
    except Exception as exc:  # noqa: BLE001
        raise FFmpegError("Could not parse width/height/duration from ffprobe output") from exc

    if width <= 0 or height <= 0:
        raise FFmpegError("Invalid video dimensions from ffprobe")
    if duration < 0:
        raise FFmpegError("Invalid duration from ffprobe")
    return width, height, duration


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
        candidate = parent / f"{stem}_{index:02d}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def make_unique_dir(path: Path) -> Path:
    if not path.exists():
        return path
    index = 1
    while True:
        candidate = path.parent / f"{path.name}_{index:02d}"
        if not candidate.exists():
            return candidate
        index += 1


def resolve_output_root(input_path: str, options: ProcessingOptions) -> Path:
    if options.save_next_to_input:
        return Path(input_path).parent
    if options.output_folder:
        return Path(options.output_folder)
    return Path(input_path).parent


def build_overlay_command(
    options: ProcessingOptions,
    input_path: str,
    logo_path: str,
    output_file: str,
    logo_rect: tuple[int, int, int, int] = (LOGO_LEFT, LOGO_TOP, LOGO_WIDTH, LOGO_HEIGHT),
    keep_logo_aspect: bool = True,
) -> list[str]:
    overwrite_flag = "-y" if options.overwrite_existing else "-n"
    logo_left, logo_top, logo_width, logo_height = logo_rect
    if keep_logo_aspect:
        logo_scale = (
            f"[1:v]scale={logo_width}:{logo_height}:force_original_aspect_ratio=decrease,"
            f"pad={logo_width}:{logo_height}:(ow-iw)/2:(oh-ih)/2[lg]"
        )
    else:
        logo_scale = f"[1:v]scale={logo_width}:{logo_height}[lg]"

    filter_complex = f"{logo_scale};[0:v][lg]overlay={logo_left}:{logo_top}:format=auto[v]"

    return [
        options.ffmpeg_path,
        overwrite_flag,
        "-i",
        input_path,
        "-i",
        logo_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-c:a",
        "copy",
        output_file,
    ]


def build_delogo_overlay_command(
    options: ProcessingOptions,
    input_path: str,
    logo_path: str,
    output_file: str,
    logo_rect: tuple[int, int, int, int] = (LOGO_LEFT, LOGO_TOP, LOGO_WIDTH, LOGO_HEIGHT),
    keep_logo_aspect: bool = True,
) -> list[str]:
    overwrite_flag = "-y" if options.overwrite_existing else "-n"
    logo_left, logo_top, logo_width, logo_height = logo_rect
    if keep_logo_aspect:
        logo_scale = (
            f"[1:v]scale={logo_width}:{logo_height}:force_original_aspect_ratio=decrease,"
            f"pad={logo_width}:{logo_height}:(ow-iw)/2:(oh-ih)/2[lg]"
        )
    else:
        logo_scale = f"[1:v]scale={logo_width}:{logo_height}[lg]"

    filter_complex = (
        f"[0:v]delogo=x={logo_left}:y={logo_top}:w={logo_width}:h={logo_height}:show=0[v0];"
        f"{logo_scale};"
        f"[v0][lg]overlay={logo_left}:{logo_top}:format=auto[v]"
    )

    return [
        options.ffmpeg_path,
        overwrite_flag,
        "-i",
        input_path,
        "-i",
        logo_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-c:a",
        "copy",
        output_file,
    ]


def build_frame_replace_command(
    options: ProcessingOptions,
    input_path: str,
    image_path: str,
    output_file: str,
    start_seconds: float,
    end_seconds: float,
    video_width: int,
    video_height: int,
    keep_audio: bool,
    mode: str = "full",
    roi_x: int = 0,
    roi_y: int = 0,
    roi_w: int = 0,
    roi_h: int = 0,
    expression_style: str = "escaped",
) -> list[str]:
    overwrite_flag = "-y" if options.overwrite_existing else "-n"
    if expression_style == "quoted":
        enable_expr = f"'between(t,{start_seconds:.3f},{end_seconds:.3f})'"
    else:
        enable_expr = f"between(t\,{start_seconds:.3f}\,{end_seconds:.3f})"

    if mode == "roi":
        filter_complex = (
            f"[1:v]scale={roi_w}:{roi_h}:force_original_aspect_ratio=decrease,"
            f"pad={roi_w}:{roi_h}:(ow-iw)/2:(oh-ih)/2[img];"
            f"[0:v][img]overlay={roi_x}:{roi_y}:enable={enable_expr}[v]"
        )
    else:
        filter_complex = (
            f"[1:v]scale={video_width}:{video_height}:force_original_aspect_ratio=decrease,"
            f"pad={video_width}:{video_height}:(ow-iw)/2:(oh-ih)/2[img];"
            f"[0:v][img]overlay=0:0:enable={enable_expr}[v]"
        )

    command = [
        options.ffmpeg_path,
        overwrite_flag,
        "-i",
        input_path,
        "-loop",
        "1",
        "-i",
        image_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-shortest",
    ]

    if keep_audio:
        command += ["-c:a", "copy"]
    else:
        command += ["-c:a", "aac", "-b:a", "192k"]

    command.append(output_file)
    return command


def build_extract_preview_frame_command(
    ffmpeg_path: str,
    input_path: str,
    time_s: float,
    out_png: str,
) -> list[str]:
    return [
        ffmpeg_path,
        "-y",
        "-ss",
        f"{time_s:.3f}",
        "-i",
        input_path,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        out_png,
    ]


def build_extract_frame_preview_command(
    ffmpeg_path: str,
    input_path: str,
    output_png: str,
    at_seconds: float,
) -> list[str]:
    return build_extract_preview_frame_command(ffmpeg_path, input_path, at_seconds, output_png)


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
    frame_interval_sec: int | None = None,
) -> list[str]:
    overwrite_flag = "-y" if options.overwrite_existing else "-n"
    interval = frame_interval_sec or options.frame_interval_sec
    fps_filter = f"fps=1/{interval}"

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
