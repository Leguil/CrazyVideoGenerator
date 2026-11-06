# Author: François Guillemette
"""Background execution engine, job queuing, and WebSocket broadcast manager."""

import asyncio
import json
import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.config import (
    DEFAULT_CFG,
    DEFAULT_FPS,
    DEFAULT_FRAMES,
    DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_PRESET,
    DEFAULT_STEPS,
    MODEL_DIR,
    MODEL_ID,
    OUTPUTS_DIR,
    PRESETS,
)
from app.pipeline import get_pipeline
from app.system_info import check_model_files, get_cached_gpu_info, get_gpu_info, get_system_status

logger = logging.getLogger("crazy_video_generator.engine")

MAX_JOBS_HISTORY = 100


class GenerationJob:
    """Encapsulates a video generation request and its live execution state."""

    def __init__(
        self,
        job_id: str,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 1280,
        height: int = 704,
        num_frames: int = DEFAULT_FRAMES,
        num_inference_steps: int = DEFAULT_STEPS,
        guidance_scale: float = DEFAULT_CFG,
        seed: int = -1,
        fps: int = DEFAULT_FPS,
        init_image: Optional[str] = None,
        image_strength: float = 0.85,
    ):
        self.job_id = job_id
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.width = width
        self.height = height
        self.num_frames = num_frames
        self.num_inference_steps = num_inference_steps
        self.guidance_scale = guidance_scale
        self.seed = seed
        self.fps = fps
        self.init_image = init_image
        self.has_init_image: bool = bool(init_image)
        self.image_strength = image_strength

        self.status: str = "queued"  # queued, running, completed, failed
        self.progress_percent: int = 0
        self.current_step: int = 0
        self.total_steps: int = num_inference_steps
        self.elapsed_sec: float = 0.0
        self.eta_sec: float = 0.0
        self.it_per_sec: float = 0.0
        self.error_message: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None
        self.created_at: str = datetime.now().isoformat()
        self.completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "width": self.width,
            "height": self.height,
            "num_frames": self.num_frames,
            "num_inference_steps": self.num_inference_steps,
            "guidance_scale": self.guidance_scale,
            "seed": self.seed,
            "fps": self.fps,
            "has_init_image": self.has_init_image,
            "image_strength": self.image_strength if self.has_init_image else None,
            "progress_percent": self.progress_percent,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "elapsed_sec": self.elapsed_sec,
            "eta_sec": self.eta_sec,
            "it_per_sec": self.it_per_sec,
            "error_message": self.error_message,
            "result": self.result,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class DownloadJob:
    """Tracks background HuggingFace model checkpoint download."""

    def __init__(self, repo_id: str, target_dir: Path):
        self.repo_id = repo_id
        self.target_dir = target_dir
        self.status = "idle"  # idle, downloading, completed, failed
        self.message = "Model download not started"
        self.error: Optional[str] = None
        self.progress_percent: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "status": self.status,
            "message": self.message,
            "error": self.error,
            "progress_percent": self.progress_percent,
        }


class EngineManager:
    """Central engine coordinator handling jobs, workers, and WebSockets."""

    def __init__(self):
        self.jobs: Dict[str, GenerationJob] = {}
        self.job_queue: asyncio.Queue[GenerationJob] = asyncio.Queue()
        self.active_job: Optional[GenerationJob] = None
        self.download_job = DownloadJob(MODEL_ID, MODEL_DIR)
        self.active_websockets: Set[Any] = set()
        self._worker_task: Optional[asyncio.Task] = None
        self._telemetry_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def register_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = loop.create_task(self._job_worker())
        if self._telemetry_task is None or self._telemetry_task.done():
            self._telemetry_task = loop.create_task(self._telemetry_loop())

    async def register_websocket(self, ws: Any) -> None:
        self.active_websockets.add(ws)

    def unregister_websocket(self, ws: Any) -> None:
        self.active_websockets.discard(ws)

    async def broadcast_message(self, message: Dict[str, Any]) -> None:
        """Send JSON message to all connected clients."""
        dead = set()
        for ws in self.active_websockets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for d in dead:
            self.active_websockets.discard(d)

    def submit_job(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 1280,
        height: int = 704,
        num_frames: int = DEFAULT_FRAMES,
        num_inference_steps: int = DEFAULT_STEPS,
        guidance_scale: float = DEFAULT_CFG,
        seed: int = -1,
        fps: int = DEFAULT_FPS,
        init_image: Optional[str] = None,
        image_strength: float = 0.85,
    ) -> GenerationJob:
        job_id = str(uuid.uuid4())[:8]
        job = GenerationJob(
            job_id=job_id,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_frames=num_frames,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            fps=fps,
            init_image=init_image,
            image_strength=image_strength,
        )
        self.jobs[job_id] = job
        self._prune_old_jobs()
        if self._loop:
            asyncio.run_coroutine_threadsafe(self.job_queue.put(job), self._loop)
        return job

    def _prune_old_jobs(self) -> None:
        """Evict oldest completed or failed jobs when history exceeds MAX_JOBS_HISTORY."""
        if len(self.jobs) <= MAX_JOBS_HISTORY:
            return
        finished_ids = [
            jid for jid, j in self.jobs.items()
            if j.status in ("completed", "failed")
        ]
        while len(self.jobs) > MAX_JOBS_HISTORY and finished_ids:
            oldest_id = finished_ids.pop(0)
            self.jobs.pop(oldest_id, None)

    def start_download_thread(self) -> DownloadJob:
        """Launch background thread to download Wan2.2 weights."""
        if self.download_job.status == "downloading":
            return self.download_job

        self.download_job.status = "downloading"
        self.download_job.message = f"Starting download from Hugging Face: {MODEL_ID}"
        self.download_job.error = None

        thread = threading.Thread(target=self._run_download, daemon=True)
        thread.start()
        return self.download_job

    def _run_download(self) -> None:
        try:
            from huggingface_hub import snapshot_download
            from app.system_info import cleanup_orphaned_download_files, convert_model_shards_to_bf16

            logger.info(f"Cleaning stale download cache and locks before starting download...")
            cleanup_orphaned_download_files(MODEL_DIR)

            logger.info(f"Downloading model {MODEL_ID} to {MODEL_DIR}...")
            self.download_job.message = "Connecting to Hugging Face..."

            # Background poller thread to update download progress while snapshot_download runs
            stop_poller = threading.Event()

            def poll_progress():
                while not stop_poller.wait(2.0):
                    mstat = check_model_files(max_age_sec=0.5, is_active_download=True)
                    self.download_job.progress_percent = mstat.get("download_percent", 0)
                    self.download_job.message = f"Downloading: {mstat.get('download_progress_label', '')}"

            poller = threading.Thread(target=poll_progress, daemon=True)
            poller.start()

            snapshot_download(
                repo_id=MODEL_ID,
                local_dir=str(MODEL_DIR),
                local_dir_use_symlinks=False,
            )

            stop_poller.set()
            poller.join(timeout=3.0)

            logger.info("Optimizing transformer shards to bfloat16 in-place...")
            self.download_job.message = "Optimizing shards to bfloat16..."
            convert_model_shards_to_bf16(MODEL_DIR, progress_cb=lambda msg: setattr(self.download_job, "message", msg))

            mstat = check_model_files(max_age_sec=0.0, is_active_download=False)
            if mstat["is_ready"]:
                self.download_job.status = "completed"
                self.download_job.message = "Model download completed successfully!"
                self.download_job.progress_percent = 100
                logger.info("Model download complete and fully validated.")
            else:
                self.download_job.status = "idle"
                self.download_job.message = f"Partial download saved ({mstat['download_progress_label']})"
                self.download_job.progress_percent = mstat.get("download_percent", 0)

        except Exception as exc:
            logger.error(f"Failed to download model: {exc}", exc_info=True)
            self.download_job.status = "failed"
            self.download_job.error = str(exc)
            self.download_job.message = f"Download failed: {exc}"

    def build_telemetry_payload(self, status: Dict[str, Any], msg_type: str = "telemetry") -> Dict[str, Any]:
        """Build a standardized WebSocket telemetry or pong payload from get_system_status()."""
        payload: Dict[str, Any] = {
            "type": msg_type,
            "gpus": status.get("gpus", []),
            "model": {
                "is_ready": status.get("model_ready", False),
                "is_downloading": status.get("model_downloading", False),
                "status_label": status.get("model_status_label", "missing"),
                "model_size_gib": status.get("model_size_gib", 0.0),
                "total_size_gib": status.get("model_total_gib", 0.0),
                "download_percent": status.get("model_download_percent", 0),
                "download_progress_label": status.get("model_download_label", ""),
                "missing_components": status.get("missing_components", []),
            },
            "disk": status.get("disk", {}),
            "recommended_device_mapping": status.get("recommended_device_mapping", {}),
            "download": self.download_job.to_dict(),
            "active_job": self.active_job.to_dict() if self.active_job else None,
        }
        if msg_type == "pong":
            payload["timestamp"] = datetime.now().isoformat()
        return payload

    async def _telemetry_loop(self) -> None:
        """Periodically broadcast GPU metrics and download status to all connected WebSockets."""
        logger.info("Telemetry broadcast loop started.")
        while True:
            await asyncio.sleep(2.5)
            if self.active_websockets:
                try:
                    status = await asyncio.to_thread(get_system_status)
                    # If download job is running, sync progress
                    if self.download_job.status == "downloading":
                        self.download_job.progress_percent = status.get("model_download_percent", self.download_job.progress_percent)
                        self.download_job.message = f"Downloading: {status.get('model_download_label', '')}"

                    await self.broadcast_message(self.build_telemetry_payload(status, "telemetry"))
                except Exception as exc:
                    logger.debug(f"Telemetry broadcast error: {exc}")

    async def _job_worker(self) -> None:
        """Continuous background worker executing submitted generation tasks."""
        logger.info("Generation job worker started.")
        while True:
            job = await self.job_queue.get()
            self.active_job = job
            job.status = "running"
            await self.broadcast_message({"type": "job_started", "job": job.to_dict()})

            try:
                pipeline = get_pipeline()

                def on_progress(pdata: Dict[str, Any]) -> None:
                    job.current_step = pdata["step"]
                    job.progress_percent = pdata["percent"]
                    job.elapsed_sec = pdata["elapsed_sec"]
                    job.eta_sec = pdata["eta_sec"]
                    job.it_per_sec = pdata["it_per_sec"]

                    # Schedule websocket update using non-blocking cached GPU metrics
                    if self._loop:
                        asyncio.run_coroutine_threadsafe(
                            self.broadcast_message({
                                "type": "job_progress",
                                "job_id": job.job_id,
                                "progress": pdata,
                                "gpus": get_cached_gpu_info(),
                            }),
                            self._loop,
                        )

                # Execute in thread to keep asyncio event loop responsive
                result = await asyncio.to_thread(
                    pipeline.generate_video,
                    prompt=job.prompt,
                    negative_prompt=job.negative_prompt,
                    width=job.width,
                    height=job.height,
                    num_frames=job.num_frames,
                    num_inference_steps=job.num_inference_steps,
                    guidance_scale=job.guidance_scale,
                    seed=job.seed,
                    fps=job.fps,
                    init_image=job.init_image,
                    image_strength=job.image_strength,
                    progress_callback=on_progress,
                )

                job.status = "completed"
                job.progress_percent = 100
                job.completed_at = datetime.now().isoformat()
                job.result = result
                await self.broadcast_message({"type": "job_completed", "job": job.to_dict()})

            except Exception as exc:
                logger.error(f"Job {job.job_id} failed: {exc}", exc_info=True)
                job.status = "failed"
                job.error_message = str(exc)
                job.completed_at = datetime.now().isoformat()
                await self.broadcast_message({"type": "job_failed", "job": job.to_dict()})

            finally:
                job.init_image = None
                self.active_job = None
                self.job_queue.task_done()


# Global engine singleton
engine_manager = EngineManager()
