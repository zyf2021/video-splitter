from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from core.ffmpeg import (
    FFmpegError,
    build_audio_command,
    build_delogo_overlay_command,
    build_frames_command,
    build_overlay_command,
    ensure_output_dir,
    has_audio_stream,
    is_logo_file,
    make_unique_dir,
    probe_duration,
    resolve_output_root,
    validate_binaries,
)
from core.jobs import Job, JobStatus, ProcessingOptions


class WorkerSignals(QObject):
    log = pyqtSignal(str)
    job_updated = pyqtSignal(int, object)
    queue_progress = pyqtSignal(int, int)
    finished = pyqtSignal(dict)


class ProcessingWorker(QObject):
    def __init__(self, jobs: list[Job], options: ProcessingOptions):
        super().__init__()
        self.jobs = jobs
        self.options = options
        self.signals = WorkerSignals()
        self._stop_requested = False
        self._current_process: Optional[subprocess.Popen[str]] = None

        self._logger = logging.getLogger("video_splitter")
        self._logger.setLevel(logging.INFO)
        ensure_output_dir(Path("logs"))
        if not self._logger.handlers:
            file_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self._logger.addHandler(file_handler)

    @pyqtSlot()
    def run(self) -> None:
        ok, error_text = validate_binaries(self.options.ffmpeg_path, self.options.ffprobe_path)
        if not ok:
            self._log(error_text)
            self.signals.finished.emit({"ok": 0, "error": len(self.jobs), "cancelled": 0})
            return

        logo_path = Path(self.options.logo_path)
        if not logo_path.exists() or not is_logo_file(logo_path):
            self._log("Logo file is not selected or has unsupported format (PNG/WEBP)")
            self.signals.finished.emit({"ok": 0, "error": len(self.jobs), "cancelled": 0})
            return

        done_count = 0
        error_count = 0
        cancelled_count = 0

        for idx, job in enumerate(self.jobs):
            if self._stop_requested:
                job.status = JobStatus.CANCELLED
                self.signals.job_updated.emit(idx, job)
                cancelled_count += 1
                continue

            try:
                self._process_job(idx, job)
                if job.status in (JobStatus.DONE, JobStatus.DONE_NO_AUDIO):
                    done_count += 1
                elif job.status == JobStatus.CANCELLED:
                    cancelled_count += 1
                else:
                    error_count += 1
            except FFmpegError as exc:
                if self._stop_requested and "Cancelled" in str(exc):
                    job.status = JobStatus.CANCELLED
                    self._log(f"[{job.filename}] Cancelled")
                    self.signals.job_updated.emit(idx, job)
                    cancelled_count += 1
                    continue
                job.status = JobStatus.ERROR
                job.error_message = str(exc)
                job.progress = 0
                self._log(f"[{job.filename}] Fatal error: {exc}")
                self.signals.job_updated.emit(idx, job)
                error_count += 1
            except Exception as exc:  # pragma: no cover
                job.status = JobStatus.ERROR
                job.error_message = str(exc)
                job.progress = 0
                self._log(f"[{job.filename}] Unexpected error: {exc}")
                self.signals.job_updated.emit(idx, job)
                error_count += 1

            self.signals.queue_progress.emit(idx + 1, len(self.jobs))

        self.signals.finished.emit({"ok": done_count, "error": error_count, "cancelled": cancelled_count})

    def request_stop(self) -> None:
        self._stop_requested = True
        if self._current_process and self._current_process.poll() is None:
            self._current_process.terminate()

    def _process_job(self, index: int, job: Job) -> None:
        job.status = JobStatus.PROCESSING
        job.progress = 0
        job.outputs = []
        self.signals.job_updated.emit(index, job)
        self._log(f"[{job.filename}] Processing started")

        duration = probe_duration(self.options.ffprobe_path, job.input_path)
        input_path = Path(job.input_path)
        output_root = resolve_output_root(job.input_path, self.options)
        ensure_output_dir(output_root)

        job_dir = make_unique_dir(output_root / input_path.stem)
        ensure_output_dir(job_dir)

        processed_video = job_dir / f"{input_path.stem}_logo{input_path.suffix}"
        audio_output = job_dir / f"audio.{self.options.audio_format}"
        frames_dir = job_dir / "frames"
        original_output = job_dir / f"original{input_path.suffix}"

        self._log(f"[{job.filename}] Step 1/4: generating logo video")
        self._run_overlay_step(index, job, duration, input_path, processed_video)
        job.outputs.append(str(processed_video))

        no_audio = False
        if self.options.extract_audio:
            self._log(f"[{job.filename}] Step 2/4: extracting audio")
            has_audio = has_audio_stream(self.options.ffprobe_path, str(processed_video))
            if not has_audio:
                no_audio = True
                self._log(f"[{job.filename}] No audio stream found, skipping audio extraction")
            else:
                try:
                    cmd = build_audio_command(self.options, str(processed_video), str(audio_output))
                    self._run_ffmpeg(cmd, duration, index, job, 0.5, 0.2)
                except FFmpegError as exc:
                    if self.options.audio_mode == "copy" and self.options.audio_format == "m4a":
                        self._log(f"[{job.filename}] Copy mode failed, fallback to transcode: {exc}")
                        fallback_cmd = build_audio_command(
                            self.options,
                            str(processed_video),
                            str(audio_output),
                            force_transcode=True,
                        )
                        self._run_ffmpeg(fallback_cmd, duration, index, job, 0.5, 0.2)
                    else:
                        raise
                job.outputs.append(str(audio_output))

        if self.options.extract_frames:
            self._log(f"[{job.filename}] Step 3/4: extracting frames")
            ensure_output_dir(frames_dir)
            pattern = frames_dir / f"frame_%06d.{self.options.frame_format}"
            cmd = build_frames_command(self.options, str(processed_video), str(pattern))
            self._run_ffmpeg(cmd, duration, index, job, 0.7, 0.2)
            job.outputs.append(str(frames_dir))

        self._log(f"[{job.filename}] Step 4/4: finalizing output structure")
        shutil.move(str(input_path), str(original_output))
        job.outputs.append(str(original_output))
        job.output_path = str(job_dir)

        job.progress = 100
        if no_audio and self.options.extract_audio:
            job.status = JobStatus.DONE_NO_AUDIO
        else:
            job.status = JobStatus.DONE
        self.signals.job_updated.emit(index, job)
        self._log(f"[{job.filename}] Processing finished")

    def _run_overlay_step(
        self,
        index: int,
        job: Job,
        duration: float,
        input_path: Path,
        processed_video: Path,
    ) -> None:
        if self.options.remove_old_logo:
            cmd = build_delogo_overlay_command(
                self.options,
                str(input_path),
                self.options.logo_path,
                str(processed_video),
            )
        else:
            cmd = build_overlay_command(
                self.options,
                str(input_path),
                self.options.logo_path,
                str(processed_video),
            )

        try:
            self._run_ffmpeg(cmd, duration, index, job, 0.0, 0.5)
        except FFmpegError as exc:
            if "code" in str(exc):
                self._log(f"[{job.filename}] Audio copy failed on video export, retry with AAC")
                cmd_with_aac = cmd[:-2] + ["-c:a", "aac", "-b:a", "192k", str(processed_video)]
                self._run_ffmpeg(cmd_with_aac, duration, index, job, 0.0, 0.5)
            else:
                raise

    def _run_ffmpeg(
        self,
        command: list[str],
        duration: float,
        index: int,
        job: Job,
        progress_offset: float,
        step_weight: float,
    ) -> None:
        ffmpeg_cmd = [command[0], "-progress", "pipe:1", "-nostats", *command[1:]]
        self._log(f"Running: {' '.join(ffmpeg_cmd)}")

        self._current_process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        assert self._current_process.stdout is not None
        for raw_line in self._current_process.stdout:
            if self._stop_requested:
                self._current_process.terminate()
                break
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("out_time_ms="):
                out_time_ms = self._parse_out_time_ms(line.split("=", 1)[1])
                if out_time_ms is not None:
                    self._update_progress(index, job, progress_offset, step_weight, duration, out_time_ms / 1_000_000)
            elif line.startswith("out_time="):
                out_time = self._parse_time(line.split("=", 1)[1])
                if out_time is not None:
                    self._update_progress(index, job, progress_offset, step_weight, duration, out_time)
            elif line.startswith("progress=") and line.endswith("end"):
                job.progress = min(100, int((progress_offset + step_weight) * 100))
                self.signals.job_updated.emit(index, job)

        return_code = self._current_process.wait()
        self._current_process = None

        if self._stop_requested:
            raise FFmpegError("Cancelled")
        if return_code != 0:
            raise FFmpegError(f"ffmpeg failed with code {return_code}")

    def _update_progress(
        self,
        index: int,
        job: Job,
        progress_offset: float,
        step_weight: float,
        duration: float,
        current_seconds: float,
    ) -> None:
        if duration <= 0:
            return
        stage_ratio = max(0.0, min(1.0, current_seconds / duration))
        total_ratio = progress_offset + stage_ratio * step_weight
        job.progress = min(99, int(total_ratio * 100))
        self.signals.job_updated.emit(index, job)

    @staticmethod
    def _parse_out_time_ms(raw_value: str) -> Optional[int]:
        value = raw_value.strip()
        if not value or value == "N/A":
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_time(raw_time: str) -> Optional[float]:
        value = raw_time.strip()
        if not value or value == "N/A":
            return None
        parts = value.split(":")
        if len(parts) != 3:
            return None
        try:
            h = float(parts[0])
            m = float(parts[1])
            s = float(parts[2])
        except ValueError:
            return None
        return h * 3600 + m * 60 + s

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.signals.log.emit(f"[{timestamp}] {message}")
        self._logger.info(message)
