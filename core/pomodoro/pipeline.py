from __future__ import annotations

from pathlib import Path

from core.pomodoro.defaults import COVER_LAYOUT_1920X1080, DEFAULT_INSTRUCTION_TEXT


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("\n", "\\n")


def generate_cover(
    ffmpeg_path: str,
    output_png: str,
    width: int,
    height: int,
    background_path: str,
    font_path: str,
    work_minutes: int,
    break_minutes: int,
    instruction_text: str = DEFAULT_INSTRUCTION_TEXT,
    title_text: str = "POMODORO",
    pattern_path: str = "",
    overwrite: bool = True,
) -> list[str]:
    layout = COVER_LAYOUT_1920X1080
    ow = "-y" if overwrite else "-n"
    cmd = [ffmpeg_path, ow]

    if background_path and Path(background_path).is_file():
        cmd += ["-loop", "1", "-i", background_path]
    else:
        cmd += ["-f", "lavfi", "-i", f"color=c=#101018:s={width}x{height}:d=1"]

    has_pattern = bool(pattern_path and Path(pattern_path).is_file())
    if has_pattern:
        cmd += ["-loop", "1", "-i", pattern_path]

    font_opt = f":fontfile='{_esc(font_path)}'" if font_path and Path(font_path).is_file() else ""
    base = f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}[bg]"

    if has_pattern:
        filters = [
            base,
            (
                f"[1:v]scale={layout['light_sphere']['w']}:{layout['light_sphere']['h']}[pattern]"
            ),
            (
                f"[bg][pattern]overlay={layout['light_sphere']['x']}:{layout['light_sphere']['y']}[v0]"
            ),
        ]
        current = "[v0]"
    else:
        filters = [
            base,
            (
                f"[bg]drawbox=x={layout['light_sphere']['x']}:y={layout['light_sphere']['y']}:"
                f"w={layout['light_sphere']['w']}:h={layout['light_sphere']['h']}:"
                "color=white@0.15:t=fill[v0]"
            ),
        ]
        current = "[v0]"

    drawtext = (
        f"drawtext=text='{_esc(title_text)}'{font_opt}:fontcolor=white:fontsize={layout['title']['fontsize']}:x={layout['title']['x']}:y={layout['title']['y']},"
        f"drawtext=text='{work_minutes}'{font_opt}:fontcolor=white:fontsize={layout['work_minutes']['fontsize']}:x={layout['work_minutes']['x']}:y={layout['work_minutes']['y']},"
        f"drawtext=text='{break_minutes}'{font_opt}:fontcolor=white:fontsize={layout['break_minutes']['fontsize']}:x={layout['break_minutes']['x']}:y={layout['break_minutes']['y']},"
        f"drawtext=text='{_esc(instruction_text)}'{font_opt}:fontcolor=white:fontsize=36:line_spacing=14:x=(w-text_w)/2:y=h-320"
    )

    filters.append(f"{current}{''.join(drawtext)}[vout]")

    cmd += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[vout]",
        "-frames:v",
        "1",
        "-pix_fmt",
        "rgb24",
        output_png,
    ]
    return cmd
