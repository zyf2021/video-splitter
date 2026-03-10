import argparse
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


def str2bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_bg_color(value: str) -> tuple[int, int, int]:
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 3:
        raise ValueError("bg-color должен быть в формате R,G,B")
    rgb = tuple(int(p) for p in parts)
    for c in rgb:
        if not (0 <= c <= 255):
            raise ValueError("Каждый канал bg-color должен быть в диапазоне 0..255")
    return rgb


def format_mmss(seconds_left: int) -> str:
    seconds_left = max(0, int(seconds_left))
    mm = seconds_left // 60
    ss = seconds_left % 60
    return f"{mm:02d}:{ss:02d}"


def remove_animation_nodes(elem: ET.Element) -> None:
    for child in list(elem):
        tag = child.tag.split("}")[-1]
        if tag in {"animate", "animateTransform", "animateMotion", "set"}:
            elem.remove(child)
        else:
            remove_animation_nodes(child)


def patch_svg(svg_text: str, progress: float, label_text: str) -> str:
    """
    Обновляет SVG:
    - удаляет SMIL-анимации;
    - находит circle со stroke-dasharray и меняет stroke-dashoffset;
    - находит первый text и меняет его содержимое.
    """
    root = ET.fromstring(svg_text)

    remove_animation_nodes(root)

    progress_circle = None
    text_node = None

    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag == "circle" and "stroke-dasharray" in elem.attrib and progress_circle is None:
            progress_circle = elem
        elif tag == "text" and text_node is None:
            text_node = elem

    if progress_circle is None:
        raise RuntimeError("В SVG не найден progress circle со stroke-dasharray")

    r = float(progress_circle.attrib.get("r", "0"))
    circumference = 2.0 * math.pi * r
    progress = max(0.0, min(1.0, progress))

    progress_circle.set("stroke-dasharray", f"{circumference:.2f}")
    progress_circle.set("stroke-dashoffset", f"{circumference * progress:.2f}")

    if text_node is not None:
        text_node.text = label_text

    root.set("aria-label", f"Pomodoro timer {label_text}")
    return ET.tostring(root, encoding="unicode")


def render_svg_to_qimage(svg_text: str, size: int) -> QImage:
    data = QByteArray(svg_text.encode("utf-8"))
    renderer = QSvgRenderer(data)
    if not renderer.isValid():
        raise RuntimeError("QSvgRenderer не смог прочитать SVG")

    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()

    return image


def center_crop_scaled(image: QImage, width: int, height: int) -> QImage:
    scaled = image.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - width) // 2)
    y = max(0, (scaled.height() - height) // 2)
    return scaled.copy(x, y, width, height)


def qimage_to_rgb_array(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width = image.width()
    height = image.height()
    ptr = image.bits()
    ptr.setsize(image.sizeInBytes())
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((height, image.bytesPerLine() // 4, 4))
    return arr[:, :width, :3].copy()


def make_base_frame(width: int, height: int, bg_image_path: str | None, bg_color: tuple[int, int, int]) -> QImage:
    frame = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)

    if bg_image_path:
        bg = QImage(bg_image_path)
        if bg.isNull():
            raise FileNotFoundError(f"Не удалось открыть фон: {bg_image_path}")
        bg = center_crop_scaled(bg, width, height)

        painter = QPainter(frame)
        painter.drawImage(0, 0, bg)
        painter.end()
    else:
        frame.fill(QColor(*bg_color))

    return frame


def compose_frame(base_frame: QImage, timer_image: QImage, offset_x: int, offset_y: int) -> QImage:
    frame = base_frame.copy()

    x = (frame.width() - timer_image.width()) // 2 + offset_x
    y = (frame.height() - timer_image.height()) // 2 + offset_y

    painter = QPainter(frame)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawImage(x, y, timer_image)
    painter.end()

    return frame


def build_timer_frame(
    svg_template: str,
    elapsed_seconds: float,
    duration_seconds: int,
    timer_size: int,
) -> QImage:
    progress = 0.0 if duration_seconds <= 0 else elapsed_seconds / duration_seconds
    progress = max(0.0, min(1.0, progress))

    seconds_left = max(0, math.ceil(duration_seconds - elapsed_seconds))
    label = format_mmss(seconds_left)

    patched_svg = patch_svg(svg_template, progress=progress, label_text=label)
    return render_svg_to_qimage(patched_svg, timer_size)


def main() -> None:
    parser = argparse.ArgumentParser(description="Рендер SVG-таймера в MP4 без CairoSVG")
    parser.add_argument("--svg", required=True, help="Путь к SVG-файлу")
    parser.add_argument("--out", required=True, help="Выходной mp4")
    parser.add_argument("--duration", type=int, required=True, help="Длительность таймера в секундах")
    parser.add_argument("--fps", type=int, default=30, help="FPS видео")
    parser.add_argument("--width", type=int, default=1920, help="Ширина видео")
    parser.add_argument("--height", type=int, default=1080, help="Высота видео")
    parser.add_argument("--bg-image", default=None, help="Фоновое изображение")
    parser.add_argument("--bg-color", default="10,10,18", help="Фон R,G,B если нет bg-image")
    parser.add_argument("--timer-size", type=int, default=720, help="Размер таймера в пикселях")
    parser.add_argument("--offset-x", type=int, default=0, help="Сдвиг таймера по X")
    parser.add_argument("--offset-y", type=int, default=0, help="Сдвиг таймера по Y")
    parser.add_argument("--smooth", default="false", help="true = плавно каждый кадр, false = обновление раз в секунду")
    parser.add_argument("--final-hold", type=float, default=1.0, help="Сколько секунд держать 00:00 в конце")

    args = parser.parse_args()

    svg_path = Path(args.svg)
    if not svg_path.exists():
        raise FileNotFoundError(f"SVG не найден: {svg_path}")

    bg_color = parse_bg_color(args.bg_color)
    smooth = str2bool(args.smooth)

    svg_template = svg_path.read_text(encoding="utf-8")
    total_frames = args.duration * args.fps
    hold_frames = max(0, int(round(args.final_hold * args.fps)))

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    base_frame = make_base_frame(
        width=args.width,
        height=args.height,
        bg_image_path=args.bg_image,
        bg_color=bg_color,
    )

    writer = imageio.get_writer(
        args.out,
        fps=args.fps,
        codec="libx264",
        macro_block_size=None,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )

    cache: dict[int, np.ndarray] = {}

    try:
        for frame_idx in range(total_frames):
            if smooth:
                elapsed = frame_idx / args.fps
                cache_key = frame_idx
            else:
                whole_seconds = min(frame_idx // args.fps, args.duration)
                elapsed = float(whole_seconds)
                cache_key = whole_seconds

            if cache_key not in cache:
                timer_image = build_timer_frame(
                    svg_template=svg_template,
                    elapsed_seconds=elapsed,
                    duration_seconds=args.duration,
                    timer_size=args.timer_size,
                )
                frame_image = compose_frame(
                    base_frame=base_frame,
                    timer_image=timer_image,
                    offset_x=args.offset_x,
                    offset_y=args.offset_y,
                )
                cache[cache_key] = qimage_to_rgb_array(frame_image)

            writer.append_data(cache[cache_key])

            if frame_idx % max(1, args.fps * 10) == 0:
                current_sec = frame_idx / args.fps
                print(f"\rРендер: {current_sec:7.1f}s / {args.duration}s", end="", flush=True)

        final_timer_image = build_timer_frame(
            svg_template=svg_template,
            elapsed_seconds=float(args.duration),
            duration_seconds=args.duration,
            timer_size=args.timer_size,
        )
        final_frame = compose_frame(
            base_frame=base_frame,
            timer_image=final_timer_image,
            offset_x=args.offset_x,
            offset_y=args.offset_y,
        )
        final_arr = qimage_to_rgb_array(final_frame)

        for _ in range(hold_frames):
            writer.append_data(final_arr)

    finally:
        writer.close()

    print(f"\nГотово: {args.out}")
    app.quit()


if __name__ == "__main__":
    main()