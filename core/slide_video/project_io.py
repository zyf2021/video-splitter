from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from core.slide_video.models import Project, ProjectSettings, Scene


def save_project(project: Project, output_file: str) -> None:
    payload = {
        "settings": asdict(project.settings),
        "scenes": [asdict(scene) for scene in project.scenes],
    }
    Path(output_file).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(input_file: str) -> Project:
    payload = json.loads(Path(input_file).read_text(encoding="utf-8"))
    settings = ProjectSettings(**payload.get("settings", {}))
    scenes = [Scene(**raw_scene) for raw_scene in payload.get("scenes", [])]
    return Project(settings=settings, scenes=scenes)
