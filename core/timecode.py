from __future__ import annotations

import re

_TIME_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*$")


class TimecodeError(ValueError):
    pass


def parse_timecode_to_seconds(raw_value: str) -> float:
    value = raw_value.strip()
    if not value:
        raise TimecodeError("Time value is empty")

    parts = value.split(":")
    if len(parts) > 3:
        raise TimecodeError("Timecode must be SS, MM:SS or HH:MM:SS")

    if len(parts) == 1:
        return _parse_seconds(parts[0])
    if len(parts) == 2:
        minutes = _parse_int(parts[0], "minutes")
        seconds = _parse_seconds(parts[1])
        return minutes * 60 + seconds

    hours = _parse_int(parts[0], "hours")
    minutes = _parse_int(parts[1], "minutes")
    seconds = _parse_seconds(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def _parse_int(value: str, label: str) -> int:
    if not value.isdigit():
        raise TimecodeError(f"Invalid {label} component: {value}")
    return int(value)


def _parse_seconds(value: str) -> float:
    if not _TIME_RE.match(value):
        raise TimecodeError(f"Invalid seconds component: {value}")
    return float(value)
