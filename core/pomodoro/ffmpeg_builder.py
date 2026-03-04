from __future__ import annotations

from pathlib import Path

from core.pomodoro.models import PomodoroProject
from core.pomodoro.timeline import PomodoroScene


def _ow(overwrite: bool) -> str:
    return "-y" if overwrite else "-n"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _scene_bg(project: PomodoroProject, kind: str) -> str:
    if kind == "title":
        return project.assets.bg_title
    if kind == "instruction":
        return project.assets.bg_instruction or project.assets.bg_player
    if kind in {"work", "break"}:
        return project.assets.bg_player
    return project.assets.bg_final


def _drawtext(scene: PomodoroScene, project: PomodoroProject) -> list[str]:
    font = project.assets.font_path
    font_opt = f":fontfile='{_esc(font)}'" if font else ""
    items: list[str] = []

    if scene.kind == "title":
        items.append(f"drawtext=text='{_esc(project.text.video_title)}'{font_opt}:fontcolor=white:fontsize=74:x=(w-text_w)/2:y=h*0.13")
    elif scene.kind in {"work", "break"}:
        label = project.text.work_label if scene.kind == "work" else project.text.break_label
        items.append(f"drawtext=text='{_esc(label)}'{font_opt}:fontcolor=white:fontsize=54:x=(w-text_w)/2:y=h*0.12")
        if project.text.show_session_numbering:
            session_text = f"{project.text.session_label} {scene.session_index}"
            items.append(f"drawtext=text='{_esc(session_text)}'{font_opt}:fontcolor=white:fontsize=32:x=(w-text_w)/2:y=h*0.22")
    elif scene.kind == "instruction":
        items.append(f"drawtext=text='{_esc(project.text.instruction_text)}'{font_opt}:fontcolor=white:fontsize=48:x=(w-text_w)/2:y=h*0.12")
    elif scene.kind == "final":
        items.append(f"drawtext=text='{_esc(project.text.final_text)}'{font_opt}:fontcolor=white:fontsize=64:x=(w-text_w)/2:y=h*0.16")
    return items


def build_scene_clip_command(
    ffmpeg_path: str,
    project: PomodoroProject,
    scene: PomodoroScene,
    output_file: str,
    timer_dir: Path | None,
    overwrite: bool = True,
    single_frame: bool = False,
) -> list[str]:
    w, h = project.settings.resolution
    fps = project.settings.fps
    cmd = [ffmpeg_path, _ow(overwrite), "-loop", "1", "-i", _scene_bg(project, scene.kind), "-i", project.assets.object_image]

    has_timer = bool(scene.show_timer and timer_dir)
    if has_timer:
        cmd += ["-framerate", str(fps), "-i", str(timer_dir / "timer_%06d.png")]

    filters = [
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}[bg]",
        f"[1:v]scale=iw*{project.settings.object_scale_pct/100.0:.4f}:ih*{project.settings.object_scale_pct/100.0:.4f}[obj]",
        f"[bg][obj]overlay={project.settings.object_x}:{project.settings.object_y}[v1]",
    ]
    current = "[v1]"
    if has_timer:
        filters.append(f"{current}[2:v]overlay={project.timer.x}:{project.timer.y}[v2]")
        current = "[v2]"

    draw_chain = _drawtext(scene, project)
    filters.append(f"{current}{',' + ','.join(draw_chain) if draw_chain else ''},format=yuv420p[vout]")

    cmd += ["-filter_complex", ";".join(filters), "-map", "[vout]"]
    if single_frame:
        cmd += ["-frames:v", "1"]
    else:
        cmd += ["-t", f"{scene.duration:.3f}", "-r", str(fps)]

    cmd += ["-an", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", output_file]
    return cmd


def build_concat_command(ffmpeg_path: str, clips: list[str], output_file: str, overwrite: bool = True) -> list[str]:
    cmd = [ffmpeg_path, _ow(overwrite)]
    for clip in clips:
        cmd += ["-i", clip]
    concat_inputs = "".join(f"[{i}:v]" for i in range(len(clips)))
    cmd += ["-filter_complex", f"{concat_inputs}concat=n={len(clips)}:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", output_file]
    return cmd


def build_beep_audio_command(
    ffmpeg_path: str,
    total_duration: float,
    events_sec: list[float],
    frequency: int,
    duration_ms: int,
    volume: float,
    output_file: str,
    overwrite: bool = True,
) -> list[str]:
    cmd = [ffmpeg_path, _ow(overwrite), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{total_duration:.3f}"]
    for _ in events_sec:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration={duration_ms/1000:.3f}"]

    filters = [f"[0:a]atrim=0:{total_duration:.3f}[s0]"]
    mix_inputs = ["[s0]"]
    for idx, t_sec in enumerate(events_sec, start=1):
        delay = max(0, int(round(t_sec * 1000)))
        filters.append(f"[{idx}:a]volume={volume},adelay={delay}|{delay}[b{idx}]")
        mix_inputs.append(f"[b{idx}]")
    filters.append(f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:normalize=0[a]")

    cmd += ["-filter_complex", ";".join(filters), "-map", "[a]", "-c:a", "aac", "-b:a", "192k", output_file]
    return cmd


def build_mux_command(ffmpeg_path: str, video_file: str, audio_file: str, output_file: str, overwrite: bool = True) -> list[str]:
    return [ffmpeg_path, _ow(overwrite), "-i", video_file, "-i", audio_file, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", output_file]
