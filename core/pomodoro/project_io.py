from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from core.pomodoro.models import PomodoroProject


def save_assets_used(project: PomodoroProject, output_file: str) -> None:
    payload = {
        "output_name": project.output_name,
        "settings": asdict(project.settings),
        "assets": asdict(project.assets),
        "text": asdict(project.text),
        "timer": asdict(project.timer),
        "beep": asdict(project.beep),
    }
    Path(output_file).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
