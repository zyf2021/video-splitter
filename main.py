from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_test_mode() -> int:
    from core.ffmpeg import detect_ffmpeg, ffprobe_from_ffmpeg
    from core.jobs import Job, ProcessingOptions
    from core.worker import ProcessingWorker

    input_file = Path("samples/input.mp4")
    output_dir = Path("samples/out")
    logo_file = Path("samples/logo.png")

    if not input_file.exists():
        print(f"Test input is missing: {input_file}")
        return 1
    if not logo_file.exists():
        print(f"Test logo is missing: {logo_file}")
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
        logo_path=str(logo_file),
        remove_old_logo=True,
    )

    jobs = [Job(input_path=str(input_file))]
    worker = ProcessingWorker(jobs, options)
    worker.signals.log.connect(print)
    worker.signals.finished.connect(lambda summary: print(f"Summary: {summary}"))

    print("Starting test mode...")
    worker.run()
    print("Test mode finished")
    return 0 if jobs[0].status.value.startswith("Done") else 2



def _maybe_relaunch_outside_pycharm_debugger() -> int | None:
    """On Windows/PyCharm, relaunch without debugger to bypass native 0xC0000409 crashes."""
    if os.name != "nt":
        return None
    if os.environ.get("PYCHARM_HOSTED") != "1":
        return None
    if os.environ.get("VIDEO_SPLITTER_CHILD") == "1":
        return None

    env = os.environ.copy()
    env["VIDEO_SPLITTER_CHILD"] = "1"
    env["PYDEVD_USE_CYTHON"] = "NO"
    env["PYCHARM_HOSTED"] = "0"

    cmd = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
    result = subprocess.run(cmd, env=env, check=False)
    return result.returncode


def _startup_log(enabled: bool, message: str) -> None:
    if not enabled:
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with Path("startup.log").open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {message}\n")


def _configure_windows_qt_runtime() -> None:
    """Apply safer Qt defaults for some Windows environments.

    Helps avoid native startup crashes (0xC0000409) caused by GPU/OpenGL driver
    issues with Qt widgets.
    """
    if os.name != "nt":
        return
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QSG_RHI_BACKEND", "software")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QTWEBENGINE_DISABLE_GPU", "1")


def main() -> int:
    relaunched_code = _maybe_relaunch_outside_pycharm_debugger()
    if relaunched_code is not None:
        return relaunched_code

    _configure_windows_qt_runtime()

    parser = argparse.ArgumentParser(description="Video Splitter")
    parser.add_argument("--safe-gui", action="store_true", help="Force extra-safe Qt software rendering mode")
    parser.add_argument("--diag-startup", action="store_true", help="Write startup milestones to startup.log")
    parser.add_argument("--test-run", action="store_true", help="Run one-file processing without GUI")
    args = parser.parse_args()

    _startup_log(args.diag_startup, "Arguments parsed")

    if args.safe_gui and os.name == "nt":
        os.environ["QT_OPENGL"] = "software"
        os.environ["QSG_RHI_BACKEND"] = "software"
        os.environ["QT_QUICK_BACKEND"] = "software"

    if args.test_run:
        _startup_log(args.diag_startup, "Running in test mode")
        return run_test_mode()

    _startup_log(args.diag_startup, "Importing PyQt6")
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from ui.main_window import MainWindow

    _startup_log(args.diag_startup, "Configuring QApplication attributes")
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
    app = QApplication(sys.argv)
    _startup_log(args.diag_startup, "QApplication created")
    app.setStyle("Fusion")
    _startup_log(args.diag_startup, "Fusion style set")
    window = MainWindow()
    _startup_log(args.diag_startup, "MainWindow created")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
