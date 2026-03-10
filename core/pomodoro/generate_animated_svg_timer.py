from __future__ import annotations

import argparse
import math
from pathlib import Path


def parse_time_to_seconds(value: str) -> int:
    value = str(value).strip()
    if not value:
        raise ValueError("Пустое значение времени")

    if ":" not in value:
        minutes = int(value)
        if minutes < 0:
            raise ValueError("Время не может быть отрицательным")
        return minutes * 60

    parts = value.split(":")
    if len(parts) == 2:
        mm, ss = map(int, parts)
        total = mm * 60 + ss
    elif len(parts) == 3:
        hh, mm, ss = map(int, parts)
        total = hh * 3600 + mm * 60 + ss
    else:
        raise ValueError("Формат времени: MM, MM:SS или HH:MM:SS")

    if total < 0:
        raise ValueError("Время не может быть отрицательным")
    return total


def normalize_hex_color(value: str) -> str:
    value = str(value).strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in value):
        raise ValueError("Цвет должен быть в формате #RRGGBB или RRGGBB")
    return f"#{value.lower()}"


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i+2], 16) for i in (0, 2, 4))


def fmt_mmss(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hh = total_seconds // 3600
    mm = (total_seconds % 3600) // 60
    ss = total_seconds % 60
    if hh > 0:
        return f"{hh:02d}:{mm:02d}:{ss:02d}"
    return f"{mm:02d}:{ss:02d}"


def escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_countdown_texts(cx: int, cy: int, total_seconds: int, font_family: str, font_size: int, text_color: str) -> str:
    lines: list[str] = []
    safe_font = escape_attr(font_family)

    for elapsed in range(total_seconds):
        left = total_seconds - elapsed
        label = fmt_mmss(left)
        lines.append(
            f'''  <text x="{cx}" y="{cy + font_size // 3}" text-anchor="middle" visibility="hidden" '''
            f'''fill="{text_color}" font-family="{safe_font}" font-size="{font_size}" font-weight="700" letter-spacing="2">'''
            f'''<set attributeName="visibility" to="visible" begin="{elapsed}s" dur="1s" fill="remove" />{label}</text>'''
        )

    # Финальный кадр 00:00 остается на экране
    final_label = fmt_mmss(0)
    lines.append(
        f'''  <text x="{cx}" y="{cy + font_size // 3}" text-anchor="middle" visibility="hidden" '''
        f'''fill="{text_color}" font-family="{safe_font}" font-size="{font_size}" font-weight="700" letter-spacing="2">'''
        f'''<set attributeName="visibility" to="visible" begin="{total_seconds}s" fill="freeze" />{final_label}</text>'''
    )

    return "\n".join(lines)


def build_svg(total_seconds: int, color: str, size: int, ring_width: int, font_family: str, no_glow: bool) -> str:
    cx = cy = size // 2
    radius = int(size * 0.3333)
    circumference = 2 * math.pi * radius
    track = "#ffffff22"
    text_color = "#f5ebff"
    rgb = hex_to_rgb(color)
    glow_filter = ""
    filter_attr = ""

    if not no_glow:
        glow_filter = f'''
  <defs>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="10" result="blur"/>
      <feColorMatrix in="blur" type="matrix"
        values="1 0 0 0 0
                0 1 0 0 0
                0 0 1 0 0
                0 0 0 0.85 0" result="softGlow"/>
      <feMerge>
        <feMergeNode in="softGlow"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>'''
        filter_attr = ' filter="url(#glow)"'

    font_size = int(size * 0.122)
    center_glow = (
        f'''  <circle cx="{cx}" cy="{cy}" r="{int(size * 0.23)}" fill="rgb({rgb[0]}, {rgb[1]}, {rgb[2]})" opacity="0.06">\n'''
        f'''    <animate attributeName="opacity" values="0.04;0.08;0.04" dur="3s" repeatCount="indefinite" />\n'''
        f'''  </circle>'''
    )

    countdown_texts = build_countdown_texts(
        cx=cx,
        cy=cy,
        total_seconds=total_seconds,
        font_family=font_family,
        font_size=font_size,
        text_color=text_color,
    )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" aria-label="Animated pomodoro timer">
{glow_filter}
  <title>Animated pomodoro timer</title>
  <desc>Standalone animated SVG timer with countdown text and progress ring.</desc>

  <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{track}" stroke-width="{ring_width}" />

{center_glow}

  <circle cx="{cx}" cy="{cy}" r="{radius}"
          fill="none"
          stroke="{color}"
          stroke-width="{ring_width}"
          stroke-linecap="round"
          stroke-dasharray="{circumference:.2f}"
          stroke-dashoffset="0"
          transform="rotate(-90 {cx} {cy})"{filter_attr}>
    <animate attributeName="stroke-dashoffset"
             from="0"
             to="{circumference:.2f}"
             dur="{total_seconds}s"
             fill="freeze" />
  </circle>

{countdown_texts}
</svg>
'''
    return svg


def main() -> None:
    parser = argparse.ArgumentParser(description="Генерация анимированного SVG-таймера без JavaScript")
    parser.add_argument("--time", required=True, help="Время: MM, MM:SS или HH:MM:SS")
    parser.add_argument("--color", required=True, help="Цвет кольца: #RRGGBB или RRGGBB")
    parser.add_argument("--out", required=True, help="Путь к выходному SVG")
    parser.add_argument("--size", type=int, default=1080, help="Размер SVG")
    parser.add_argument("--ring-width", type=int, default=40, help="Толщина кольца")
    parser.add_argument("--font-family", default="Inter, Arial, sans-serif", help="Семейство шрифта")
    parser.add_argument("--no-glow", action="store_true", help="Отключить свечение")

    args = parser.parse_args()

    total_seconds = parse_time_to_seconds(args.time)
    if total_seconds <= 0:
        raise ValueError("Время должно быть больше нуля")

    color = normalize_hex_color(args.color)
    svg_text = build_svg(
        total_seconds=total_seconds,
        color=color,
        size=args.size,
        ring_width=args.ring_width,
        font_family=args.font_family,
        no_glow=args.no_glow,
    )

    out_path = Path(args.out)
    out_path.write_text(svg_text, encoding="utf-8")
    print(f"Готово: {out_path}")


if __name__ == "__main__":
    main()
