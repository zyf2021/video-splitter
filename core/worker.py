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
    build_frame_replace_command,
    build_frames_command,
    build_overlay_command,
    ensure_output_dir,
    fit_logo_rect,
    has_audio_stream,
    is_logo_file,
    make_unique_dir,
    probe_duration,
    probe_video_size,
    resolve_output_root,
    validate_binaries,
)
from core.jobs import FrameReplaceJob, Job, JobStatus, ProcessingOptions, SlideVideoJob
from core.jobs import PomodoroVideoJob
from core.timecode import TimecodeError, parse_timecode_to_seconds
from core.slide_video.builder import (
    build_audio_concat_command,
    build_audio_scene_command,
    build_mux_command,
    build_scene_clip_command,
    build_video_concat_command,
    scene_duration,
    write_concat_list,
)
from core.slide_video.models import Project, ProjectSettings, Scene
from core.slide_video.project_io import save_project
from core.pomodoro.ffmpeg_builder import (
    build_beep_audio_command,
    build_concat_command,
    build_mux_command as build_pomodoro_mux_command,
    build_scene_clip_command as build_pomodoro_scene_clip_command,
)
from core.pomodoro.models import PomodoroProject
from core.pomodoro.project_io import save_assets_used
from core.pomodoro.timeline import build_timeline
from core.pomodoro.timer_render import render_timer_sequence


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
        self._last_ffmpeg_error: str = ""

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

        if self._has_logo_jobs():
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
                if isinstance(job, FrameReplaceJob):
                    self._process_frame_replace_job(idx, job)
                elif isinstance(job, SlideVideoJob):
                    self._process_slide_video_job(idx, job)
                elif isinstance(job, PomodoroVideoJob):
                    self._process_pomodoro_job(idx, job)
                else:
                    self._process_logo_job(idx, job)

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

    def _has_logo_jobs(self) -> bool:
        return any(not isinstance(job, (FrameReplaceJob, SlideVideoJob, PomodoroVideoJob)) for job in self.jobs)

    def _process_pomodoro_job(self, index: int, job: PomodoroVideoJob) -> None:
        self._prepare_job(index, job)
        project = PomodoroProject(
            output_root=job.output_root,
            output_name=job.output_name,
            settings=job.settings,
            assets=job.assets,
            text=job.text,
            timer=job.timer,
            beep=job.beep,
        )
        timeline = build_timeline(project)
        output_root = Path(job.output_root) if job.output_root else Path(job.input_path).parent
        project_dir = make_unique_dir(output_root / project.display_name)
        ensure_output_dir(project_dir)
        temp_dir = project_dir / "temp"
        timer_dir = temp_dir / "timer_frames"
        clips_dir = temp_dir / "clips"
        ensure_output_dir(timer_dir)
        ensure_output_dir(clips_dir)

        self._log(f"[{job.output_name}] Step 1/9: validate assets")
        for p in [project.assets.bg_title, project.assets.bg_player, project.assets.bg_final, project.assets.object_image]:
            if not Path(p).is_file():
                raise FFmpegError(f"Asset not found: {p}")

        self._log(f"[{job.output_name}] Step 2/9: prepare timer frames")
        for i, scene in enumerate(timeline.scenes):
            if scene.show_timer:
                scene_timer_dir = timer_dir / f"scene_{i+1:03d}"
                render_timer_sequence(
                    output_dir=scene_timer_dir,
                    fps=project.settings.fps,
                    duration_sec=scene.duration,
                    diameter=project.timer.diameter,
                    ring_color=project.timer.ring_color,
                    progress_color=project.timer.progress_color,
                    text_color=project.timer.text_color,
                    show_progress_arc=project.timer.show_progress_arc,
                )

        if job.generate_cover_only:
            self._log(f"[{job.output_name}] Step 3/9: generate cover only")
            cover_path = project_dir / "cover.png"
            title_scene = timeline.scenes[0]
            cover_cmd = build_pomodoro_scene_clip_command(
                self.options.ffmpeg_path,
                project,
                title_scene,
                str(cover_path),
                timer_dir=None,
                overwrite=True,
                single_frame=True,
            )
            self._run_ffmpeg(cover_cmd, 1.0, index, job, 0.1, 0.8)
            save_assets_used(project, str(project_dir / "assets_used.json"))
            if not project.settings.keep_temp and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            job.outputs.extend([str(cover_path), str(project_dir / "assets_used.json")])
            self._finalize_job(index, job, project_dir, no_audio=False)
            return

        self._log(f"[{job.output_name}] Step 3/9: render scene clips")
        clip_paths: list[Path] = []
        for i, scene in enumerate(timeline.scenes):
            clip_path = clips_dir / f"clip_{i+1:03d}.mp4"
            this_timer_dir = (timer_dir / f"scene_{i+1:03d}") if scene.show_timer else None
            cmd = build_pomodoro_scene_clip_command(self.options.ffmpeg_path, project, scene, str(clip_path), this_timer_dir)
            self._run_ffmpeg(cmd, scene.duration, index, job, 0.1, 0.45 / max(1, len(timeline.scenes)))
            clip_paths.append(clip_path)

        self._log(f"[{job.output_name}] Step 4/9: concat video")
        video_no_audio = temp_dir / "video_no_audio.mp4"
        self._run_ffmpeg(
            build_concat_command(self.options.ffmpeg_path, [str(p) for p in clip_paths], str(video_no_audio), True),
            timeline.total_duration,
            index,
            job,
            0.56,
            0.14,
        )

        self._log(f"[{job.output_name}] Step 5/9: build beep audio")
        final_output = project_dir / "final.mp4"
        if project.beep.enabled and timeline.beep_events_sec:
            beep_audio = temp_dir / "beep_track.m4a"
            self._run_ffmpeg(
                build_beep_audio_command(
                    self.options.ffmpeg_path,
                    timeline.total_duration,
                    timeline.beep_events_sec,
                    project.beep.frequency,
                    project.beep.duration_ms,
                    project.beep.volume,
                    str(beep_audio),
                    True,
                ),
                timeline.total_duration,
                index,
                job,
                0.7,
                0.14,
            )
            self._log(f"[{job.output_name}] Step 6/9: mux final")
            self._run_ffmpeg(
                build_pomodoro_mux_command(self.options.ffmpeg_path, str(video_no_audio), str(beep_audio), str(final_output), True),
                timeline.total_duration,
                index,
                job,
                0.84,
                0.1,
            )
        else:
            self._log(f"[{job.output_name}] Step 6/9: write video without audio")
            shutil.copy2(video_no_audio, final_output)
            job.progress = 94
            self.signals.job_updated.emit(index, job)

        self._log(f"[{job.output_name}] Step 7/9: generate cover")
        cover_path = project_dir / "cover.png"
        cover_cmd = build_pomodoro_scene_clip_command(
            self.options.ffmpeg_path,
            project,
            timeline.scenes[0],
            str(cover_path),
            timer_dir=None,
            overwrite=True,
            single_frame=True,
        )
        self._run_ffmpeg(cover_cmd, 1.0, index, job, 0.94, 0.04)

        self._log(f"[{job.output_name}] Step 8/9: save metadata")
        save_assets_used(project, str(project_dir / "assets_used.json"))

        self._log(f"[{job.output_name}] Step 9/9: cleanup")
        if not project.settings.keep_temp and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

        job.outputs.extend([str(final_output), str(cover_path), str(project_dir / "assets_used.json")])
        self._finalize_job(index, job, project_dir, no_audio=not project.beep.enabled)

    def request_stop(self) -> None:
        self._stop_requested = True
        if self._current_process and self._current_process.poll() is None:
            self._current_process.terminate()

    def _prepare_job(self, index: int, job: Job) -> None:
        job.status = JobStatus.PROCESSING
        job.progress = 0
        job.outputs = []
        self.signals.job_updated.emit(index, job)
        self._log(f"[{job.filename}] Processing started")

    def _process_logo_job(self, index: int, job: Job) -> None:
        self._prepare_job(index, job)

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
                self._extract_audio(index, job, duration, processed_video, audio_output, 0.5, 0.2)

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
        self._finalize_job(index, job, job_dir, no_audio=no_audio and self.options.extract_audio)

    def _process_frame_replace_job(self, index: int, job: FrameReplaceJob) -> None:
        self._prepare_job(index, job)
        input_path = Path(job.input_path)

        try:
            start_seconds = parse_timecode_to_seconds(job.start_time)
            end_seconds = parse_timecode_to_seconds(job.end_time)
        except TimecodeError as exc:
            raise FFmpegError(str(exc)) from exc

        if start_seconds >= end_seconds:
            raise FFmpegError("start_time must be less than end_time")

        duration = probe_duration(self.options.ffprobe_path, job.input_path)
        video_width, video_height = probe_video_size(self.options.ffprobe_path, job.input_path)
        job.start_s = start_seconds

        if job.mode == "roi":
            if job.roi_w <= 0 or job.roi_h <= 0 or job.roi_x < 0 or job.roi_y < 0:
                raise FFmpegError("ROI must satisfy x>=0, y>=0, w>0, h>0")
            if job.roi_x + job.roi_w > video_width or job.roi_y + job.roi_h > video_height:
                error = (
                    "ROI выходит за границы видео. "
                    f"Видео: {video_width}×{video_height}, "
                    f"ROI: x={job.roi_x}, y={job.roi_y}, w={job.roi_w}, h={job.roi_h}"
                )
                self._log(f"[{job.filename}] {error}")
                job.status = JobStatus.SKIPPED
                job.error_message = error
                job.progress = 0
                self.signals.job_updated.emit(index, job)
                return

        self._log(f"[{job.filename}] Frame replace start={job.start_time} end={job.end_time}")
        self._log(f"[{job.filename}] Seconds start={start_seconds:.3f} end={end_seconds:.3f}")
        self._log(f"[{job.filename}] Video size {video_width}x{video_height}")

        output_root = resolve_output_root(job.input_path, self.options)
        ensure_output_dir(output_root)
        job_dir = make_unique_dir(output_root / input_path.stem)
        ensure_output_dir(job_dir)

        processed_video = job_dir / f"{input_path.stem}_frame_replace.mp4"
        audio_output = job_dir / f"audio.{self.options.audio_format}"
        frames_dir = job_dir / "frames"
        original_output = job_dir / f"original{input_path.suffix}"

        attempts = [
            {"keep_audio": job.keep_audio, "expression_style": "escaped", "tag": "primary"},
        ]
        if job.keep_audio:
            attempts.append({"keep_audio": False, "expression_style": "escaped", "tag": "aac-fallback"})
        attempts.append({"keep_audio": False, "expression_style": "quoted", "tag": "quoted-expr-fallback"})

        last_error: FFmpegError | None = None
        for attempt in attempts:
            cmd = build_frame_replace_command(
                self.options,
                job.input_path,
                job.replacement_image,
                str(processed_video),
                start_seconds,
                end_seconds,
                video_width,
                video_height,
                keep_audio=attempt["keep_audio"],
                mode=job.mode,
                roi_x=job.roi_x,
                roi_y=job.roi_y,
                roi_w=job.roi_w,
                roi_h=job.roi_h,
                expression_style=attempt["expression_style"],
            )
            try:
                self._run_ffmpeg(cmd, duration, index, job, 0.0, 0.7)
                last_error = None
                break
            except FFmpegError as exc:
                last_error = exc
                self._log(f"[{job.filename}] Frame replace attempt '{attempt['tag']}' failed: {exc}")

        if last_error is not None:
            raise last_error

        job.outputs.append(str(processed_video))

        no_audio = False
        if job.also_extract_audio:
            has_audio = has_audio_stream(self.options.ffprobe_path, str(processed_video))
            if not has_audio:
                no_audio = True
                self._log(f"[{job.filename}] No audio stream found, skipping audio extraction")
            else:
                self._extract_audio(index, job, duration, processed_video, audio_output, 0.7, 0.15)

        if job.also_extract_frames:
            ensure_output_dir(frames_dir)
            pattern = frames_dir / f"frame_%06d.{self.options.frame_format}"
            cmd_frames = build_frames_command(
                self.options,
                str(processed_video),
                str(pattern),
                frame_interval_sec=job.frame_interval_sec,
            )
            self._run_ffmpeg(cmd_frames, duration, index, job, 0.85, 0.1)
            job.outputs.append(str(frames_dir))

        shutil.move(str(input_path), str(original_output))
        job.outputs.append(str(original_output))
        self._log(f"[{job.filename}] Output: {job_dir}")
        self._finalize_job(index, job, job_dir, no_audio=no_audio and job.also_extract_audio)


    def _process_slide_video_job(self, index: int, job: SlideVideoJob) -> None:
        self._prepare_job(index, job)
        if not job.scenes:
            raise FFmpegError("Slide-video project has no scenes")

        settings = ProjectSettings(
            output_root=job.output_root,
            output_name=job.output_name,
            resolution_preset=job.resolution_preset,
            fps=job.fps,
            timing_mode=job.timing_mode,
            scale_mode=job.scale_mode,
            playback_speed=job.playback_speed,
            transitions=job.transitions,
            keep_temp=job.keep_temp,
            keep_scene_clips=job.keep_scene_clips,
        )
        scenes = [
            Scene(
                slide_path=s.slide_path,
                audio_path=s.audio_path,
                duration=s.duration,
                start=s.start,
                end=s.end,
                motion=s.motion,
                notes=s.notes,
            )
            for s in job.scenes
        ]
        project = Project(settings=settings, scenes=scenes)
        width, height = project.settings.resolution

        output_root = Path(job.output_root) if job.output_root else Path(job.input_path).parent
        project_dir = make_unique_dir(output_root / project.display_name)
        ensure_output_dir(project_dir)
        temp_dir = project_dir / "temp"
        scenes_dir = project_dir / "scenes"
        audio_tmp_dir = temp_dir / "audio"
        ensure_output_dir(temp_dir)
        ensure_output_dir(audio_tmp_dir)
        if job.keep_scene_clips:
            ensure_output_dir(scenes_dir)

        self._log(f"[{job.output_name}] Step 1/7: validate table + assets")
        for i, scene in enumerate(project.scenes, start=1):
            if not Path(scene.slide_path).exists():
                raise FFmpegError(f"Scene {i}: slide not found")
            duration = scene_duration(project, scene) / max(0.25, min(4.0, project.settings.playback_speed))
            if duration <= 0:
                raise FFmpegError(f"Scene {i}: invalid duration")

        self._log(f"[{job.output_name}] Step 2/7: ensure ffmpeg available")

        video_clips: list[Path] = []
        audio_clips: list[Path] = []
        total_scenes = len(project.scenes)

        self._log(f"[{job.output_name}] Step 3/7: render scene clips")
        for idx_scene, scene in enumerate(project.scenes):
            duration = scene_duration(project, scene) / max(0.25, min(4.0, project.settings.playback_speed))
            clip_output = temp_dir / f"scene_{idx_scene+1:03d}.mp4"
            scene_cmd = build_scene_clip_command(
                self.options.ffmpeg_path,
                scene,
                str(clip_output),
                width,
                height,
                project.settings.fps,
                duration,
                project.settings.scale_mode,
                overwrite=True,
            )
            self._run_ffmpeg(scene_cmd, duration, index, job, 0.05, 0.45 / total_scenes)
            video_clips.append(clip_output)
            if job.keep_scene_clips:
                shutil.copy2(clip_output, scenes_dir / clip_output.name)

            audio_output = audio_tmp_dir / f"audio_{idx_scene+1:03d}.m4a"
            audio_cmd = build_audio_scene_command(
                self.options.ffmpeg_path,
                scene,
                str(audio_output),
                duration,
                playback_speed=project.settings.playback_speed,
                overwrite=True,
            )
            self._run_ffmpeg(audio_cmd, duration, index, job, 0.5, 0.25 / total_scenes)
            audio_clips.append(audio_output)

        self._log(f"[{job.output_name}] Step 4/7: concat video")
        video_list = temp_dir / "video_concat.txt"
        write_concat_list(video_clips, video_list)
        video_mix = temp_dir / "video_mix.mp4"
        self._run_ffmpeg(build_video_concat_command(self.options.ffmpeg_path, str(video_list), str(video_mix), True), project.total_duration, index, job, 0.75, 0.08)

        self._log(f"[{job.output_name}] Step 5/7: build audio track")
        audio_list = temp_dir / "audio_concat.txt"
        write_concat_list(audio_clips, audio_list)
        audio_mix = project_dir / "audio_mix.m4a"
        self._run_ffmpeg(build_audio_concat_command(self.options.ffmpeg_path, str(audio_list), str(audio_mix), True), project.total_duration, index, job, 0.83, 0.07)

        self._log(f"[{job.output_name}] Step 6/7: mux final video")
        final_output = project_dir / "final.mp4"
        self._run_ffmpeg(build_mux_command(self.options.ffmpeg_path, str(video_mix), str(audio_mix), str(final_output), True), project.total_duration, index, job, 0.9, 0.09)

        self._log(f"[{job.output_name}] Step 7/7: cleanup temp")
        if not project.settings.keep_temp and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

        save_project(project, str(project_dir / "project.json"))
        job.outputs.extend([str(final_output), str(audio_mix), str(project_dir / "project.json")])
        job.output_path = str(project_dir)
        self._finalize_job(index, job, project_dir, no_audio=False)

    def _finalize_job(self, index: int, job: Job, job_dir: Path, no_audio: bool) -> None:
        job.output_path = str(job_dir)
        job.progress = 100
        job.status = JobStatus.DONE_NO_AUDIO if no_audio else JobStatus.DONE
        self.signals.job_updated.emit(index, job)
        self._log(f"[{job.filename}] Processing finished")

    def _extract_audio(
        self,
        index: int,
        job: Job,
        duration: float,
        processed_video: Path,
        audio_output: Path,
        offset: float,
        weight: float,
    ) -> None:
        try:
            cmd = build_audio_command(self.options, str(processed_video), str(audio_output))
            self._run_ffmpeg(cmd, duration, index, job, offset, weight)
        except FFmpegError as exc:
            if self.options.audio_mode == "copy" and self.options.audio_format == "m4a":
                self._log(f"[{job.filename}] Copy mode failed, fallback to transcode: {exc}")
                fallback_cmd = build_audio_command(
                    self.options,
                    str(processed_video),
                    str(audio_output),
                    force_transcode=True,
                )
                self._run_ffmpeg(fallback_cmd, duration, index, job, offset, weight)
            else:
                raise
        job.outputs.append(str(audio_output))

    def _run_overlay_step(
        self,
        index: int,
        job: Job,
        duration: float,
        input_path: Path,
        processed_video: Path,
    ) -> None:
        video_width, video_height = probe_video_size(self.options.ffprobe_path, str(input_path))
        overlay_rect = fit_logo_rect(video_width, video_height)
        delogo_rect = fit_logo_rect(video_width, video_height, strict_inside=True)
        custom_rect = (self.options.logo_x, self.options.logo_y, self.options.logo_w, self.options.logo_h)
        if self.options.logo_w > 0 and self.options.logo_h > 0:
            overlay_rect = custom_rect
            delogo_rect = custom_rect

        if self.options.remove_old_logo:
            cmd = build_delogo_overlay_command(
                self.options,
                str(input_path),
                self.options.logo_path,
                str(processed_video),
                logo_rect=delogo_rect,
                keep_logo_aspect=self.options.logo_keep_aspect,
            )
        else:
            cmd = build_overlay_command(
                self.options,
                str(input_path),
                self.options.logo_path,
                str(processed_video),
                logo_rect=overlay_rect,
                keep_logo_aspect=self.options.logo_keep_aspect,
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

        ffmpeg_lines: list[str] = []

        self._current_process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        recent_output: list[str] = []
        assert self._current_process.stdout is not None
        for raw_line in self._current_process.stdout:
            if self._stop_requested:
                self._current_process.terminate()
                break
            line = raw_line.strip()
            if not line:
                continue
            recent_output.append(line)
            if len(recent_output) > 30:
                recent_output.pop(0)

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
            tail = "\n".join(recent_output[-10:])
            raise FFmpegError(f"ffmpeg failed with code {return_code}. Last output:\n{tail}")

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
