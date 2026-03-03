from __future__ import annotations

from pathlib import Path

from core.slide_video.models import Project, Scene
from core.slide_video.motions import get_motion_preset


def _overwrite_flag(overwrite: bool) -> str:
    return "-y" if overwrite else "-n"


def build_scene_clip_command(
    ffmpeg_path: str,
    scene: Scene,
    output_clip: str,
    width: int,
    height: int,
    fps: int,
    duration: float,
    scale_mode: str,
    overwrite: bool = True,
) -> list[str]:
    preset = get_motion_preset(scene.motion)
    frame_count = max(2, int(round(duration * fps)))
    x_expr = preset.x_expr.replace("duration", str(frame_count))
    y_expr = preset.y_expr.replace("duration", str(frame_count))

    if scale_mode == "fit":
        scale_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        )
    else:
        scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"

    vf = (
        f"{scale_filter},"
        f"zoompan=z='{preset.zoom_expr}':x='{x_expr}':y='{y_expr}':d={frame_count}:s={width}x{height}:fps={fps},"
        "fps={fps},format=yuv420p"
    ).format(fps=fps)

    return [
        ffmpeg_path,
        _overwrite_flag(overwrite),
        "-loop",
        "1",
        "-i",
        scene.slide_path,
        "-t",
        f"{duration:.3f}",
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        output_clip,
    ]


def build_video_concat_command(ffmpeg_path: str, concat_list_file: str, output_file: str, overwrite: bool = True) -> list[str]:
    return [
        ffmpeg_path,
        _overwrite_flag(overwrite),
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_list_file,
        "-c",
        "copy",
        output_file,
    ]


def build_audio_scene_command(
    ffmpeg_path: str,
    scene: Scene,
    output_audio: str,
    duration: float,
    overwrite: bool = True,
) -> list[str]:
    if scene.audio_path:
        return [
            ffmpeg_path,
            _overwrite_flag(overwrite),
            "-i",
            scene.audio_path,
            "-t",
            f"{duration:.3f}",
            "-vn",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            output_audio,
        ]
    return [
        ffmpeg_path,
        _overwrite_flag(overwrite),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=stereo",
        "-t",
        f"{duration:.3f}",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        output_audio,
    ]


def build_audio_concat_command(ffmpeg_path: str, concat_list_file: str, output_audio: str, overwrite: bool = True) -> list[str]:
    return [
        ffmpeg_path,
        _overwrite_flag(overwrite),
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_list_file,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        output_audio,
    ]


def build_mux_command(ffmpeg_path: str, video_file: str, audio_file: str, output_file: str, overwrite: bool = True) -> list[str]:
    return [
        ffmpeg_path,
        _overwrite_flag(overwrite),
        "-i",
        video_file,
        "-i",
        audio_file,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-shortest",
        output_file,
    ]


def write_concat_list(paths: list[Path], output_file: Path) -> None:
    lines = []
    for path in paths:
        escaped = path.as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    output_file.write_text("\n".join(lines), encoding="utf-8")


def scene_duration(project: Project, scene: Scene) -> float:
    return scene.effective_duration(project.settings.timing_mode)
