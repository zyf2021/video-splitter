from __future__ import annotations

import math
from pathlib import Path

from core.ffmpeg import FFmpegError

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover
    raise FFmpegError("Pillow is required for Pomodoro timer rendering. Install: pip install Pillow") from exc


def _format_mmss(seconds_left: float) -> str:
    total = max(0, int(round(seconds_left)))
    return f"{total // 60:02d}:{total % 60:02d}"


def render_timer_sequence(
    output_dir: Path,
    fps: int,
    duration_sec: float,
    diameter: int,
    ring_color: str,
    progress_color: str,
    text_color: str,
    show_progress_arc: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(round(duration_sec * fps)))
    size = max(64, diameter)
    pad = max(8, int(size * 0.06))

    for i in range(frames):
        ratio = i / max(1, frames - 1)
        seconds_left = max(0.0, duration_sec * (1.0 - ratio))
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        bbox = (pad, pad, size - pad, size - pad)
        draw.ellipse(bbox, outline=ring_color, width=max(4, size // 32))

        if show_progress_arc:
            draw.arc(
                bbox,
                start=-90,
                end=-90 + 360 * ratio,
                fill=progress_color,
                width=max(6, size // 24),
            )
        else:
            cx = size // 2
            cy = size // 2
            radius = (size - pad * 2) / 2
            angle = -math.pi / 2 + 2 * math.pi * ratio
            x2 = int(cx + math.cos(angle) * radius)
            y2 = int(cy + math.sin(angle) * radius)
            draw.line((cx, cy, x2, y2), fill=progress_color, width=max(5, size // 30))

        font = ImageFont.load_default()
        text = _format_mmss(seconds_left)
        tw, th = draw.textbbox((0, 0), text, font=font)[2:]
        draw.text(((size - tw) / 2, (size - th) / 2), text, fill=text_color, font=font)

        img.save(output_dir / f"timer_{i+1:06d}.png")
