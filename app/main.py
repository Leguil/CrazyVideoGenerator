# Author: François Guillemette
"""FastAPI web application server for CrazyLogix CrazyVideoGenerator."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.config import (
    BRAND_DIR,
    DEFAULT_CFG,
    DEFAULT_FPS,
    DEFAULT_FRAMES,
    DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_PRESET,
    DEFAULT_STEPS,
    LORAS_DIR,
    MODEL_ID,
    OUTPUTS_DIR,
    PRESETS,
    RECOMMENDED_LORAS,
    SERVER_HOST,
    SERVER_PORT,
    STATIC_DIR,
    VALID_FRAME_COUNTS,
)
from app.engine import engine_manager
from app.system_info import check_model_files, get_gpu_info, get_system_status

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("crazy_video_generator")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifespan."""
    loop = asyncio.get_running_loop()
    engine_manager.register_loop(loop)
    logger.info("CrazyVideoGenerator server initialized and ready.")
    yield
    logger.info("CrazyVideoGenerator server shutting down.")


app = FastAPI(
    title="CrazyLogix CrazyVideoGenerator",
    description="Studio Web Interface for Wan2.2-TI2V-5B Video Generation with Dual-GPU Orchestration",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for local cross-origin development if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    """Prevent client browsers from caching studio scripts, CSS, and API state."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/") or path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# --------------------------------------------------------------------------- #
# Request Schemas
# --------------------------------------------------------------------------- #

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=2, description="Text prompt describing the video sequence")
    negative_prompt: Optional[str] = Field(None, description="Elements to discourage or avoid")
    preset: Optional[str] = Field(DEFAULT_PRESET, description="Aspect ratio preset identifier")
    width: Optional[int] = Field(None, ge=256, le=1280)
    height: Optional[int] = Field(None, ge=256, le=1280)
    num_frames: Optional[int] = Field(None, ge=17, le=161, description="Number of frames (must be 4k + 1)")
    num_inference_steps: Optional[int] = Field(DEFAULT_STEPS, ge=10, le=100)
    guidance_scale: Optional[float] = Field(DEFAULT_CFG, ge=1.0, le=20.0)
    seed: Optional[int] = Field(-1, description="-1 for random seed")
    fps: Optional[int] = Field(DEFAULT_FPS, ge=8, le=30)
    init_image: Optional[str] = Field(None, description="Optional base64-encoded starting image")
    image_strength: Optional[float] = Field(0.85, ge=0.1, le=1.0, description="Starting image conditioning strength")
    lora_name: Optional[str] = Field(None, description="Optional LoRA .safetensors filename inside models/loras")
    lora_scale: Optional[float] = Field(0.8, ge=0.0, le=2.0, description="LoRA adapter strength multiplier")

    @field_validator("width", "height")
    @classmethod
    def validate_dimensions_multiple_of_32(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v % 32 != 0:
            raise ValueError("Width and height must be multiples of 32 for Wan2.2-VAE.")
        return v

    @field_validator("num_frames")
    @classmethod
    def validate_frame_count_4k_plus_1(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v - 1) % 4 != 0:
            raise ValueError(f"num_frames must satisfy 4k + 1 (e.g. {VALID_FRAME_COUNTS}).")
        return v

    @field_validator("init_image")
    @classmethod
    def validate_init_image_payload(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        max_b64_chars = 20 * 1024 * 1024  # ~15 MB decoded image limit
        if len(v) > max_b64_chars:
            raise ValueError("Starting image exceeds maximum allowed size (15 MB).")
        return v


# --------------------------------------------------------------------------- #
# Static Asset Mounts
# --------------------------------------------------------------------------- #

if BRAND_DIR.exists():
    app.mount("/brand", StaticFiles(directory=str(BRAND_DIR)), name="brand")

if OUTPUTS_DIR.exists():
    app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --------------------------------------------------------------------------- #
# REST Endpoints
# --------------------------------------------------------------------------- #

@app.get("/")
async def get_index() -> FileResponse:
    """Serve main Single Page Application studio."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Index HTML not found")
    return FileResponse(index_file)


@app.get("/api/status")
async def api_status() -> Dict[str, Any]:
    """Retrieve full system health, GPU metrics, and model status (non-blocking)."""
    return await asyncio.to_thread(get_system_status)


class LoraDownloadRequest(BaseModel):
    preset_id: Optional[str] = Field(None, description="Curated LoRA preset ID from RECOMMENDED_LORAS")
    repo_id: Optional[str] = Field(None, description="Custom Hugging Face repo ID (e.g. user/repo)")
    filename: Optional[str] = Field(None, description=".safetensors filename inside the HF repo")
    local_filename: Optional[str] = Field(None, description="Optional local target filename in models/loras")


@app.get("/api/loras")
async def api_loras() -> Dict[str, Any]:
    """List installed .safetensors LoRA files in models/loras and curated HF LoRAs."""
    LORAS_DIR.mkdir(parents=True, exist_ok=True)
    installed: List[Dict[str, Any]] = []
    installed_names = set()

    for sf in sorted(LORAS_DIR.glob("*.safetensors"), key=lambda p: p.name.lower()):
        installed_names.add(sf.name)
        installed.append({
            "filename": sf.name,
            "size_mb": round(sf.stat().st_size / (1024 * 1024), 2),
            "modified_at": datetime.fromtimestamp(sf.stat().st_mtime).isoformat(),
        })

    recommended = []
    for item in RECOMMENDED_LORAS.values():
        recommended.append({
            **item,
            "installed": item["local_filename"] in installed_names or item["filename"] in installed_names,
        })

    return {
        "loras_dir": str(LORAS_DIR),
        "installed": installed,
        "recommended": recommended,
    }


@app.post("/api/loras/download")
async def api_download_lora(req: LoraDownloadRequest) -> Dict[str, Any]:
    """Download a Wan2.2-TI2V-5B LoRA from Hugging Face into models/loras."""
    LORAS_DIR.mkdir(parents=True, exist_ok=True)

    repo_id = (req.repo_id or "").strip()
    filename = (req.filename or "").strip()
    local_filename = (req.local_filename or "").strip()

    if req.preset_id and req.preset_id in RECOMMENDED_LORAS:
        p = RECOMMENDED_LORAS[req.preset_id]
        repo_id = p["repo_id"]
        filename = p["filename"]
        local_filename = p["local_filename"]

    if not repo_id:
        raise HTTPException(status_code=400, detail="Either preset_id or repo_id is required.")

    def _fetch_lora() -> Dict[str, Any]:
        import shutil
        from huggingface_hub import HfApi, hf_hub_download

        target_file = filename
        if not target_file:
            api = HfApi()
            info = api.model_info(repo_id)
            st_files = [s.rfilename for s in (info.siblings or []) if s.rfilename.endswith(".safetensors")]
            if not st_files:
                raise ValueError(f"No .safetensors files found in Hugging Face repository '{repo_id}'.")
            target_file = st_files[0]

        out_name = Path(local_filename or target_file).name
        if not out_name.endswith(".safetensors"):
            out_name += ".safetensors"

        cached_path = hf_hub_download(repo_id=repo_id, filename=target_file)
        dest_path = LORAS_DIR / out_name
        shutil.copy2(cached_path, dest_path)
        size_mb = round(dest_path.stat().st_size / (1024 * 1024), 2)
        return {
            "status": "completed",
            "filename": out_name,
            "size_mb": size_mb,
            "repo_id": repo_id,
        }

    try:
        return await asyncio.to_thread(_fetch_lora)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to download LoRA from {repo_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to download LoRA: {exc}")


@app.get("/api/presets")
async def api_presets() -> Dict[str, Any]:
    """Return available aspect ratio and resolution presets."""
    return {
        "presets": PRESETS,
        "valid_frame_counts": VALID_FRAME_COUNTS,
        "default_preset": DEFAULT_PRESET,
        "default_negative_prompt": DEFAULT_NEGATIVE_PROMPT,
    }


@app.post("/api/generate")
async def api_generate(req: GenerateRequest) -> Dict[str, Any]:
    """Queue a video generation task."""
    mstat = check_model_files()
    if not mstat["is_ready"]:
        if mstat["is_downloading"]:
            detail = f"Wan2.2 model is currently downloading ({mstat['download_progress_label']}). Please wait for download to finish."
        else:
            detail = "Wan2.2 model checkpoint is not installed. Please click 'Download Model' to fetch weights first."
        raise HTTPException(status_code=400, detail=detail)

    preset_cfg = PRESETS.get(req.preset or DEFAULT_PRESET, PRESETS[DEFAULT_PRESET])
    width = req.width if req.width is not None else preset_cfg["width"]
    height = req.height if req.height is not None else preset_cfg["height"]
    num_frames = req.num_frames if req.num_frames is not None else preset_cfg["default_frames"]

    job = engine_manager.submit_job(
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        width=width,
        height=height,
        num_frames=num_frames,
        num_inference_steps=req.num_inference_steps if req.num_inference_steps is not None else DEFAULT_STEPS,
        guidance_scale=req.guidance_scale if req.guidance_scale is not None else DEFAULT_CFG,
        seed=req.seed if req.seed is not None else -1,
        fps=req.fps if req.fps is not None else DEFAULT_FPS,
        init_image=req.init_image,
        image_strength=req.image_strength if req.image_strength is not None else 0.85,
        lora_name=req.lora_name,
        lora_scale=req.lora_scale if req.lora_scale is not None else 0.8,
    )

    return {"status": "queued", "job_id": job.job_id, "job": job.to_dict()}


@app.get("/api/jobs")
async def api_get_jobs() -> Dict[str, Any]:
    """List all recent generation jobs."""
    return {
        "jobs": [j.to_dict() for j in reversed(list(engine_manager.jobs.values()))],
        "active_job": engine_manager.active_job.to_dict() if engine_manager.active_job else None,
    }


@app.get("/api/jobs/{job_id}")
async def api_get_job(job_id: str) -> Dict[str, Any]:
    """Inspect state of a specific generation job."""
    job = engine_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.get("/api/gallery")
async def api_gallery() -> Dict[str, Any]:
    """Retrieve list of generated videos, thumbnails, and sidecar metadata."""
    items: List[Dict[str, Any]] = []

    if OUTPUTS_DIR.exists():
        video_files = sorted(OUTPUTS_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        for vf in video_files:
            meta_path = vf.with_suffix(".json")
            thumb_path = vf.with_suffix(".jpg")

            meta: Dict[str, Any] = {}
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                except Exception:
                    pass

            items.append({
                "video_file": vf.name,
                "video_url": f"/outputs/{vf.name}",
                "thumbnail_url": f"/outputs/{thumb_path.name}" if thumb_path.exists() else None,
                "metadata": meta,
                "created_at": datetime.fromtimestamp(vf.stat().st_mtime).isoformat(),
                "size_mb": round(vf.stat().st_size / (1024 * 1024), 2),
            })

    return {"count": len(items), "videos": items}


@app.delete("/api/gallery/{filename}")
async def api_delete_video(filename: str) -> Dict[str, Any]:
    """Delete video and its associated thumbnail and metadata."""
    base = Path(filename).stem
    if not base or base in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    deleted = []
    for ext in [".mp4", ".jpg", ".json"]:
        target = OUTPUTS_DIR / f"{base}{ext}"
        if target.exists():
            try:
                target.unlink()
                deleted.append(target.name)
            except Exception as exc:
                logger.error(f"Failed to delete {target}: {exc}")

    if not deleted:
        raise HTTPException(status_code=404, detail="Video not found")

    return {"deleted": deleted}


@app.post("/api/model/download")
async def api_start_model_download() -> Dict[str, Any]:
    """Start background checkpoint download from Hugging Face."""
    djob = engine_manager.start_download_thread()
    return djob.to_dict()


@app.get("/api/model/download")
async def api_get_model_download() -> Dict[str, Any]:
    """Check current model download progress."""
    return engine_manager.download_job.to_dict()


# --------------------------------------------------------------------------- #
# WebSocket Live Telemetry & Progress
# --------------------------------------------------------------------------- #

async def _handle_websocket_connection(websocket: WebSocket) -> None:
    """Core WebSocket handler for progress, telemetry, and heartbeats."""
    await websocket.accept()
    await engine_manager.register_websocket(websocket)

    # Immediately push full system telemetry upon connect
    try:
        status = await asyncio.to_thread(get_system_status)
        await websocket.send_json(engine_manager.build_telemetry_payload(status, "telemetry"))
    except Exception as exc:
        logger.debug(f"Initial telemetry push error: {exc}")

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                status = await asyncio.to_thread(get_system_status)
                await websocket.send_json(engine_manager.build_telemetry_payload(status, "pong"))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug(f"WebSocket client disconnected: {exc}")
    finally:
        engine_manager.unregister_websocket(websocket)


@app.websocket("/ws/generation")
async def websocket_generation(websocket: WebSocket) -> None:
    """Primary WebSocket endpoint for video generation and live metrics."""
    await _handle_websocket_connection(websocket)


@app.websocket("/ws/stream")
async def websocket_stream_alias(websocket: WebSocket) -> None:
    """Backward-compatible WebSocket alias for /ws/stream."""
    await _handle_websocket_connection(websocket)
