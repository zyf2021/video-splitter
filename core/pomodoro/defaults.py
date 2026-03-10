from __future__ import annotations

from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = MODULE_DIR / "assets"
FONTS_DIR = MODULE_DIR / "fonts"
OUTPUT_TEMP_DIR = MODULE_DIR / "output_temp"

DEFAULT_START_BG = ASSETS_DIR / "start_bg.png"
DEFAULT_TIMER_BG = ASSETS_DIR / "timer_bg.png"
DEFAULT_INSTRUCTION_BG = ASSETS_DIR / "instruction_bg.png"
DEFAULT_FINAL_BG = ASSETS_DIR / "final_bg.png"
DEFAULT_COVER_PATTERN = ASSETS_DIR / "light_sphere_2.png"
DEFAULT_FONT = FONTS_DIR / "default.ttf"

DEFAULT_INSTRUCTION_TEXT = "\n".join(
    [
        "Choose one task to focus on without switching to anything else.",
        "Start the timer and work with full concentration until the session ends.",
        "Avoid messages, social media, and other distractions.",
        "When the signal sounds, take a short break and let your mind recover.",
        "Repeat the cycle until you finish the amount of work you planned.",
    ]
)

COVER_LAYOUT_1920X1080 = {
    "title": {"x": 443, "y": 154, "fontsize": 120},
    "work_minutes": {"x": 183, "y": 519, "fontsize": 144},
    "break_minutes": {"x": 1510, "y": 519, "fontsize": 144},
    "light_sphere": {"x": 613, "y": 237, "w": 694, "h": 789},
}


def first_existing_path(*candidates: Path) -> str:
    for path in candidates:
        if path.is_file():
            return str(path)
    return ""
