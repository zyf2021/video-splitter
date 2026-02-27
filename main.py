from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Video Splitter")
    parser.add_argument("--test-run", action="store_true", help="Run one-file processing without GUI")
    args = parser.parse_args()

    if args.test_run:
        return run_test_mode()

    from PyQt6.QtWidgets import QApplication

    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
