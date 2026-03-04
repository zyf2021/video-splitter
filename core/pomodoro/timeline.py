from __future__ import annotations

from dataclasses import dataclass

from core.pomodoro.models import PomodoroProject


@dataclass
class PomodoroScene:
    kind: str
    duration: float
    session_index: int = 0
    show_timer: bool = False
    label: str = ""


@dataclass
class PomodoroTimeline:
    scenes: list[PomodoroScene]
    beep_events_sec: list[float]

    @property
    def total_duration(self) -> float:
        return sum(scene.duration for scene in self.scenes)


def build_timeline(project: PomodoroProject) -> PomodoroTimeline:
    s = project.settings
    t = project.text
    scenes: list[PomodoroScene] = [
        PomodoroScene("title", float(s.title_duration_sec), label=t.video_title),
        PomodoroScene("instruction", float(s.instruction_duration_sec), show_timer=True, label=t.instruction_text),
    ]

    for i in range(1, s.cycles + 1):
        scenes.append(
            PomodoroScene("work", float(s.work_minutes * 60), session_index=i, show_timer=True, label=t.work_label)
        )
        if not (s.skip_last_break and i == s.cycles):
            scenes.append(
                PomodoroScene("break", float(s.break_minutes * 60), session_index=i, show_timer=True, label=t.break_label)
            )

    scenes.append(PomodoroScene("final", float(s.final_duration_sec), label=t.final_text))

    beep_events_sec: list[float] = []
    cursor = float(s.title_duration_sec + s.instruction_duration_sec)
    beep_events_sec.append(cursor)
    for scene in scenes[2:]:
        if scene.kind in {"work", "break"}:
            cursor += scene.duration
            beep_events_sec.append(cursor)
    if beep_events_sec:
        beep_events_sec.pop()

    return PomodoroTimeline(scenes=scenes, beep_events_sec=beep_events_sec)
