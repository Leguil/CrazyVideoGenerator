# Author: François Guillemette
"""System telemetry, GPU hardware inspection, and model readiness for CrazyVideoGenerator."""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import (
    EXPECTED_MODEL_GIB,
    MODEL_DIR,
    MODEL_ID,
    MODEL_PROFILES,
    MODELS_DIR,
    OUTPUTS_DIR,
)

logger = logging.getLogger("crazy_video_generator.system_info")

# In-memory cache for fast, non-blocking telemetry responses
_last_gpu_time: float = 0.0
_cached_gpu_info: List[Dict[str, Any]] = []

_last_model_time: float = 0.0
_cached_model_stat: Dict[str, Any] = {}


def get_gpu_info_nvidia_smi() -> List[Dict[str, Any]]:
    """Query nvidia-smi for accurate GPU metrics across all cards."""
    gpus: List[Dict[str, Any]] = []
    try:
        query_cmd = [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
        result = subprocess.run(
            query_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 7:
                    idx, name, mem_total, mem_used, mem_free, temp, util = parts[:7]
                    gpus.append({
                        "index": int(idx),
                        "name": name,
                        "device": f"cuda:{idx}",
                        "memory_total_mb": float(mem_total),
                        "memory_used_mb": float(mem_used),
                        "memory_free_mb": float(mem_free),
                        "memory_total_gib": round(float(mem_total) / 1024.0, 1),
                        "memory_used_gib": round(float(mem_used) / 1024.0, 2),
                        "memory_free_gib": round(float(mem_free) / 1024.0, 2),
                        "temperature_c": int(temp) if temp.isdigit() else None,
                        "utilization_percent": int(util) if util.isdigit() else None,
                    })
    except Exception as exc:
        logger.debug(f"nvidia-smi query failed: {exc}")
    return gpus


def get_gpu_info_torch() -> List[Dict[str, Any]]:
    """Fallback GPU inspection using PyTorch CUDA runtime."""
    gpus: List[Dict[str, Any]] = []
    try:
        import torch
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                total_mb = props.total_memory / (1024.0 * 1024.0)
                allocated_mb = torch.cuda.memory_allocated(i) / (1024.0 * 1024.0)
                reserved_mb = torch.cuda.memory_reserved(i) / (1024.0 * 1024.0)
                free_mb = max(0.0, total_mb - reserved_mb)
                gpus.append({
                    "index": i,
                    "name": props.name,
                    "device": f"cuda:{i}",
                    "memory_total_mb": round(total_mb, 1),
                    "memory_used_mb": round(reserved_mb, 1),
                    "memory_free_mb": round(free_mb, 1),
                    "memory_total_gib": round(total_mb / 1024.0, 1),
                    "memory_used_gib": round(reserved_mb / 1024.0, 2),
                    "memory_free_gib": round(free_mb / 1024.0, 2),
                    "temperature_c": None,
                    "utilization_percent": None,
                })
    except Exception:
        pass
    return gpus


def get_gpu_info(max_age_sec: float = 1.5) -> List[Dict[str, Any]]:
    """Retrieve comprehensive GPU telemetry with fast memory caching."""
    global _last_gpu_time, _cached_gpu_info
    now = time.time()
    if _cached_gpu_info and (now - _last_gpu_time) < max_age_sec:
        return _cached_gpu_info

    gpus = get_gpu_info_nvidia_smi()
    if not gpus:
        gpus = get_gpu_info_torch()

    _cached_gpu_info = gpus
    _last_gpu_time = now
    return gpus


def get_cached_gpu_info() -> List[Dict[str, Any]]:
    """Return the most recently cached GPU telemetry without blocking on subprocesses."""
    return _cached_gpu_info


def cleanup_orphaned_download_files(
    model_path: Optional[Path] = None,
    remove_incomplete: bool = False,
) -> int:
    """Remove stale .lock files (and optionally .incomplete files) from interrupted downloads."""
    path = model_path or MODEL_DIR
    cache_dir = path / ".cache" / "huggingface" / "download"
    freed_bytes = 0
    if not cache_dir.exists():
        return 0

    for f in list(cache_dir.rglob("*.lock")):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass

    if remove_incomplete:
        for f in list(cache_dir.rglob("*.incomplete")):
            try:
                sz = f.stat().st_size
                f.unlink(missing_ok=True)
                freed_bytes += sz
            except OSError:
                pass

    return freed_bytes


def check_model_files(
    model_path: Optional[Path] = None,
    max_age_sec: float = 2.0,
    is_active_download: Optional[bool] = None,
) -> Dict[str, Any]:
    """Check local presence and integrity of Wan2.1 model files, differentiating downloading vs ready."""
    global _last_model_time, _cached_model_stat
    now = time.time()
    if not model_path and is_active_download is None and _cached_model_stat and (now - _last_model_time) < max_age_sec:
        return _cached_model_stat

    path = model_path or MODEL_DIR
    expected_total_gib = EXPECTED_MODEL_GIB
    trees_dir = path / ".cache" / "huggingface" / "trees"
    if trees_dir.exists():
        try:
            tree_files = list(trees_dir.glob("*.json"))
            if tree_files:
                with open(tree_files[0], "r", encoding="utf-8") as tf:
                    tdata = json.load(tf)
                files_map = tdata.get("files", {})
                tree_bytes = sum(int(v.get("size", 0)) for v in files_map.values() if isinstance(v, dict))
                if tree_bytes > 1024 ** 3:
                    expected_total_gib = round(tree_bytes / (1024.0 ** 3), 1)
        except Exception:
            pass

    status = {
        "model_id": MODEL_ID,
        "path": str(path),
        "exists": path.exists() and path.is_dir(),
        "is_ready": False,
        "is_downloading": False,
        "status_label": "missing",
        "clean_size_gib": 0.0,
        "total_size_gib": 0.0,
        "download_percent": 0,
        "download_progress_label": f"0.0 / {expected_total_gib:.1f} GiB (0%)",
        "missing_components": [],
        "components_found": {},
    }

    if not status["exists"]:
        status["missing_components"] = ["model_dir_missing"]
        if not model_path and is_active_download is None:
            _cached_model_stat = status
            _last_model_time = now
        return status

    # Measure clean files (excluding .cache) and total files (including .cache/downloads)
    clean_bytes = 0
    total_bytes = 0

    try:
        for root, dirs, files in os.walk(path):
            is_cache = ".cache" in root
            for f in files:
                filepath = Path(root) / f
                try:
                    sz = filepath.stat().st_size
                    total_bytes += sz
                    if not is_cache:
                        clean_bytes += sz
                except OSError:
                    pass
    except Exception as exc:
        logger.debug(f"Error walking model directory: {exc}")

    clean_gib = round(clean_bytes / (1024.0 ** 3), 2)
    total_gib = round(total_bytes / (1024.0 ** 3), 2)
    status["clean_size_gib"] = clean_gib
    status["total_size_gib"] = total_gib

    # Check model_index.json
    has_index = (path / "model_index.json").exists()
    status["components_found"]["model_index"] = has_index
    if not has_index:
        status["missing_components"].append("model_index.json")

    # Check transformer shards
    tr_path = path / "transformer"
    tr_ready = False
    if tr_path.exists():
        tr_index = tr_path / "diffusion_pytorch_model.safetensors.index.json"
        if tr_index.exists():
            try:
                with open(tr_index, "r", encoding="utf-8") as fp:
                    idx_data = json.load(fp)
                needed = set(idx_data.get("weight_map", {}).values())
                existing = set(os.listdir(tr_path))
                missing = needed - existing
                tr_ready = (len(missing) == 0 and len(needed) > 0)
                if missing:
                    status["missing_components"].append(f"transformer ({len(missing)} shards missing)")
            except Exception:
                tr_ready = False
        else:
            # Check single safetensors or bin
            st_files = list(tr_path.glob("*.safetensors"))
            tr_ready = bool(st_files and sum(f.stat().st_size for f in st_files) > 2.0 * (1024**3))
    status["components_found"]["transformer"] = tr_ready
    if not tr_ready and "transformer" not in [m.split()[0] for m in status["missing_components"]]:
        status["missing_components"].append("transformer")

    # Check text_encoder shards
    te_path = path / "text_encoder"
    te_ready = False
    if te_path.exists():
        te_index = te_path / "model.safetensors.index.json"
        if te_index.exists():
            try:
                with open(te_index, "r", encoding="utf-8") as fp:
                    idx_data = json.load(fp)
                needed = set(idx_data.get("weight_map", {}).values())
                existing = set(os.listdir(te_path))
                missing = needed - existing
                te_ready = (len(missing) == 0 and len(needed) > 0)
                if missing:
                    status["missing_components"].append(f"text_encoder ({len(missing)} shards missing)")
            except Exception:
                te_ready = False
        else:
            st_files = list(te_path.glob("*.safetensors"))
            te_ready = bool(st_files and sum(f.stat().st_size for f in st_files) > 8.0 * (1024**3))
    status["components_found"]["text_encoder"] = te_ready
    if not te_ready and "text_encoder" not in [m.split()[0] for m in status["missing_components"]]:
        status["missing_components"].append("text_encoder")

    # Check VAE
    vae_path = path / "vae"
    vae_files = list(vae_path.glob("*.safetensors")) if vae_path.exists() else []
    vae_ready = bool(vae_files and sum(f.stat().st_size for f in vae_files) > 100 * (1024**2))
    status["components_found"]["vae"] = vae_ready
    if not vae_ready:
        status["missing_components"].append("vae")

    # Check Tokenizer
    tok_path = path / "tokenizer"
    tok_ready = bool(tok_path.exists() and (tok_path / "spiece.model").exists())
    status["components_found"]["tokenizer"] = tok_ready
    if not tok_ready:
        status["missing_components"].append("tokenizer")

    # Evaluate Overall Readiness
    is_ready = bool(
        has_index
        and tr_ready
        and te_ready
        and vae_ready
        and tok_ready
        and clean_gib >= 20.0
    )
    status["is_ready"] = is_ready

    # Check active downloading state:
    # Only report downloading if an active download process/thread was confirmed running!
    if is_ready:
        status["is_downloading"] = False
        status["status_label"] = "ready"
        status["download_percent"] = 100
        status["download_progress_label"] = f"{clean_gib:.1f} GiB (Ready)"
    elif is_active_download is True:
        status["is_downloading"] = True
        status["status_label"] = "downloading"
        # Combine completed clean files with currently downloading bytes
        dl_percent = min(99, max(1, int((total_gib / expected_total_gib) * 100)))
        status["download_percent"] = dl_percent
        status["download_progress_label"] = f"{total_gib:.1f} / {expected_total_gib:.1f} GiB ({dl_percent}%)"
    else:
        # Not ready and no active download running
        status["is_downloading"] = False
        progress_gib = max(clean_gib, total_gib)
        if progress_gib > 0.1:
            status["status_label"] = "incomplete"
            pct = min(99, max(1, int((progress_gib / expected_total_gib) * 100)))
            status["download_percent"] = pct
            status["download_progress_label"] = f"{progress_gib:.1f} / {expected_total_gib:.1f} GiB ({pct}% installed - Incomplete)"
        else:
            status["status_label"] = "missing"
            status["download_percent"] = 0
            status["download_progress_label"] = f"0.0 / {expected_total_gib:.1f} GiB (Not Downloaded)"

    if not model_path and is_active_download is None:
        _cached_model_stat = status
        _last_model_time = now

    return status


def convert_model_shards_to_bf16(
    model_path: Optional[Path] = None,
    progress_cb: Optional[Any] = None,
) -> None:
    """Convert any float32 safetensors shards in text_encoder/ and transformer/ to bfloat16 in-place."""
    import gc
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    path = model_path or MODEL_DIR
    for sub in ["text_encoder", "transformer"]:
        sub_dir = path / sub
        if not sub_dir.exists():
            continue

        shards = sorted(sub_dir.glob("*.safetensors"))
        total_sub_bytes = 0
        for shard in shards:
            tensors = {}
            metadata = {}
            needs_conversion = False
            with safe_open(str(shard), framework="pt", device="cpu") as f:
                meta = f.metadata()
                if meta:
                    metadata = dict(meta)
                for k in f.keys():
                    t = f.get_tensor(k)
                    if t.dtype == torch.float32:
                        t = t.to(torch.bfloat16)
                        needs_conversion = True
                    tensors[k] = t

            if not needs_conversion:
                total_sub_bytes += shard.stat().st_size
                del tensors
                gc.collect()
                continue

            if progress_cb:
                progress_cb(f"Optimizing {sub}/{shard.name} to bfloat16...")
            tmp_path = shard.with_suffix(".bf16.tmp")
            save_file(tensors, str(tmp_path), metadata=metadata or {"format": "pt"})
            del tensors
            gc.collect()
            tmp_path.replace(shard)
            total_sub_bytes += shard.stat().st_size

        for idx_file in sub_dir.glob("*.index.json"):
            try:
                with open(idx_file, "r", encoding="utf-8") as fp:
                    idx_data = json.load(fp)
                if "metadata" in idx_data and "total_size" in idx_data["metadata"]:
                    idx_data["metadata"]["total_size"] = total_sub_bytes
                    with open(idx_file, "w", encoding="utf-8") as fp:
                        json.dump(idx_data, fp, indent=2)
            except Exception:
                pass

    cache_dir = path / ".cache"
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)


def get_disk_usage() -> Dict[str, Any]:
    """Inspect disk space for models and outputs directories."""
    stats = {}
    for label, folder in [("models", MODELS_DIR), ("outputs", OUTPUTS_DIR)]:
        try:
            total, used, free = shutil.disk_usage(folder)
            stats[label] = {
                "total_gib": round(total / (1024.0 ** 3), 1),
                "used_gib": round(used / (1024.0 ** 3), 1),
                "free_gib": round(free / (1024.0 ** 3), 1),
                "percent_used": round((used / total) * 100.0, 1),
            }
        except Exception:
            stats[label] = {"total_gib": 0, "used_gib": 0, "free_gib": 0, "percent_used": 0}
    return stats


def _is_torch_cuda_available(gpus: List[Dict[str, Any]]) -> bool:
    """Safely check if PyTorch CUDA runtime is available."""
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return len(gpus) > 0


def get_system_status() -> Dict[str, Any]:
    """Provide complete status payload for web API and health checks."""
    active_dl = False
    try:
        from app.engine import engine_manager
        active_dl = (engine_manager.download_job.status == "downloading")
    except Exception:
        active_dl = False

    gpus = get_gpu_info()
    model_stat = check_model_files(is_active_download=active_dl)
    disk = get_disk_usage()

    has_dual_gpu = len(gpus) >= 2
    recommended_split = {
        "transformer_device": "cuda:1" if has_dual_gpu else ("cuda:0" if gpus else "cpu"),
        "text_encoder_device": "cuda:0" if gpus else "cpu",
        "vae_device": "cuda:0" if gpus else "cpu",
    }

    return {
        "status": "online",
        "service": "CrazyVideoGenerator",
        "model_id": MODEL_ID,
        "model_ready": model_stat["is_ready"],
        "model_downloading": model_stat["is_downloading"],
        "model_status_label": model_stat["status_label"],
        "model_size_gib": model_stat["clean_size_gib"],
        "model_total_gib": model_stat["total_size_gib"],
        "model_download_percent": model_stat["download_percent"],
        "model_download_label": model_stat["download_progress_label"],
        "missing_components": model_stat["missing_components"],
        "components_found": model_stat["components_found"],
        "gpus": gpus,
        "gpu_count": len(gpus),
        "dual_gpu_active": has_dual_gpu,
        "recommended_device_mapping": recommended_split,
        "disk": disk,
        "python_version": sys.version.split()[0],
        "torch_cuda_available": _is_torch_cuda_available(gpus),
    }
