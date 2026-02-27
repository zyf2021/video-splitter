from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from core.ffmpeg import detect_ffmpeg, ffprobe_from_ffmpeg
from core.jobs import Job, ProcessingOptions
from core.worker import ProcessingWorker


def run_test_mode() -> int:
    input_file = Path("samples/input.mp4")
    output_dir = Path("samples/out")

    if not input_file.exists():
        print(f"Test input is missing: {input_file}")
        return 1

    ffmpeg_path = detect_ffmpeg() or "ffmpeg"
    options = ProcessingOptions(
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_from_ffmpeg(ffmpeg_path),
        output_folder=str(output_dir),
        save_next_to_input=False,
        overwrite_existing=True,
        extract_audio=True,
        audio_format="m4a",
        audio_mode="copy",
        extract_frames=True,
        frame_interval_sec=10,
        frame_format="jpg",
        resize_mode="original",
    )

    jobs = [Job(input_path=str(input_file))]
    worker = ProcessingWorker(jobs, options)
    worker.signals.log.connect(print)
    worker.signals.finished.connect(lambda summary: print(f"Summary: {summary}"))

    print("Starting test mode...")
    worker.run()
    print("Test mode finished")
    return 0 if jobs[0].status.value.startswith("Done") else 2



def _configure_windows_qt_runtime() -> None:
    """Apply safer Qt defaults for some Windows environments.

    Helps avoid native startup crashes (0xC0000409) caused by GPU/OpenGL driver
    issues with Qt widgets.
    """
    if os.name != "nt":
        return
    os.environ.setdefault("QT_OPENGL", "software")


def main() -> int:
    parser = argparse.ArgumentParser(description="Video Splitter")
    parser.add_argument("--test-run", action="store_true", help="Run one-file processing without GUI")
    args = parser.parse_args()

    if args.test_run:
        return run_test_mode()

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from ui.main_window import MainWindow

    _configure_windows_qt_runtime()
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
