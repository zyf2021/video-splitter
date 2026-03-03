from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotionPreset:
    name: str
    zoom_expr: str
    x_expr: str
    y_expr: str


def _clamp(expr: str, limit_expr: str) -> str:
    return f"max(0,min({expr},{limit_expr}))"


MOTION_PRESETS: dict[str, MotionPreset] = {
    "Static (no motion)": MotionPreset(
        "Static (no motion)",
        "1.0",
        "(iw-ow)/2",
        "(ih-oh)/2",
    ),
    "Zoom In (center)": MotionPreset(
        "Zoom In (center)",
        "if(eq(on,1),1.0,min(1.18,zoom+0.0007))",
        "(iw-iw/zoom)/2",
        "(ih-ih/zoom)/2",
    ),
    "Zoom Out (center)": MotionPreset(
        "Zoom Out (center)",
        "if(eq(on,1),1.18,max(1.0,zoom-0.0007))",
        "(iw-iw/zoom)/2",
        "(ih-ih/zoom)/2",
    ),
    "Pan Left → Right": MotionPreset(
        "Pan Left → Right",
        "1.08",
        _clamp("(on/duration)*(iw-iw/zoom)", "iw-iw/zoom"),
        "(ih-ih/zoom)/2",
    ),
    "Pan Right → Left": MotionPreset(
        "Pan Right → Left",
        "1.08",
        _clamp("(1-on/duration)*(iw-iw/zoom)", "iw-iw/zoom"),
        "(ih-ih/zoom)/2",
    ),
    "Pan Up → Down": MotionPreset(
        "Pan Up → Down",
        "1.08",
        "(iw-iw/zoom)/2",
        _clamp("(on/duration)*(ih-ih/zoom)", "ih-ih/zoom"),
    ),
    "Pan Down → Up": MotionPreset(
        "Pan Down → Up",
        "1.08",
        "(iw-iw/zoom)/2",
        _clamp("(1-on/duration)*(ih-ih/zoom)", "ih-ih/zoom"),
    ),
    "Diagonal (Top-Left → Bottom-Right)": MotionPreset(
        "Diagonal (Top-Left → Bottom-Right)",
        "1.12",
        _clamp("(on/duration)*(iw-iw/zoom)", "iw-iw/zoom"),
        _clamp("(on/duration)*(ih-ih/zoom)", "ih-ih/zoom"),
    ),
    "Diagonal (Bottom-Right → Top-Left)": MotionPreset(
        "Diagonal (Bottom-Right → Top-Left)",
        "1.12",
        _clamp("(1-on/duration)*(iw-iw/zoom)", "iw-iw/zoom"),
        _clamp("(1-on/duration)*(ih-ih/zoom)", "ih-ih/zoom"),
    ),
    "Random subtle": MotionPreset(
        "Random subtle",
        "if(eq(on,1),1.03+random(1)*0.06,zoom)",
        _clamp("random(2)*(iw-iw/zoom)", "iw-iw/zoom"),
        _clamp("random(3)*(ih-ih/zoom)", "ih-ih/zoom"),
    ),
}


def motion_names() -> list[str]:
    return list(MOTION_PRESETS.keys())


def get_motion_preset(name: str) -> MotionPreset:
    return MOTION_PRESETS.get(name, MOTION_PRESETS["Static (no motion)"])
