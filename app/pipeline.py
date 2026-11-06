# Author: François Guillemette
"""Dual-GPU Wan2.1-T2V-1.3B inference pipeline and video export utilities."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.config import (
    DEFAULT_CFG,
    DEFAULT_DEVICES,
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

logger = logging.getLogger("crazy_video_generator.pipeline")

try:
    import torch
except ImportError:
    torch = None

try:
    import numpy as np
    from PIL import Image as PILImage
except ImportError:
    np = None
    PILImage = None

try:
    import imageio
except ImportError:
    imageio = None


class WanDualGpuPipeline:
    """Manager for loading and running Wan2.1-T2V-1.3B distributed across dual GPUs."""

    def __init__(self, model_source: Optional[str] = None, devices: Optional[str] = None):
        self.model_source = model_source or (str(MODEL_DIR) if MODEL_DIR.exists() else MODEL_ID)
        self.devices_str = devices or DEFAULT_DEVICES
        self.pipeline: Any = None
        self.transformer_device: str = "cuda:0"
        self.text_encoder_device: str = "cuda:0"
        self.vae_device: str = "cuda:0"
        self._configure_devices()

    def _configure_devices(self) -> None:
        """Resolve device placement for dual-GPU or single-GPU environments."""
        if torch is None or not torch.cuda.is_available():
            logger.warning("CUDA is not available. Defaulting all components to CPU.")
            self.transformer_device = "cpu"
            self.text_encoder_device = "cpu"
            self.vae_device = "cpu"
            return

        cuda_count = torch.cuda.device_count()
        parsed_devs = [d.strip() for d in (self.devices_str or "").split(",") if d.strip()]
        valid_devs: List[str] = []
        for dev in parsed_devs:
            if dev == "cpu":
                valid_devs.append("cpu")
            elif dev.startswith("cuda:"):
                try:
                    idx = int(dev.split(":")[1])
                    if 0 <= idx < cuda_count:
                        valid_devs.append(f"cuda:{idx}")
                except ValueError:
                    pass
            elif dev == "cuda" and cuda_count >= 1:
                valid_devs.append("cuda:0")

        if len(valid_devs) >= 2:
            self.transformer_device = valid_devs[0]
            self.text_encoder_device = valid_devs[1]
            self.vae_device = valid_devs[1]
            logger.info(
                f"Multi-GPU setup configured from '{self.devices_str}': "
                f"Transformer -> {self.transformer_device}, "
                f"TextEncoder -> {self.text_encoder_device}, VAE -> {self.vae_device}"
            )
        elif len(valid_devs) == 1:
            self.transformer_device = valid_devs[0]
            self.text_encoder_device = valid_devs[0]
            self.vae_device = valid_devs[0]
            logger.info(f"Single device configured from '{self.devices_str}': all components -> {valid_devs[0]}.")
        elif cuda_count >= 2:
            # Optimal Split: GPU1 (0 MB display overhead) for heavy transformer
            # GPU0 (primary display card) for text encoder, VAE decoder, and video encoding
            self.transformer_device = "cuda:1"
            self.text_encoder_device = "cuda:0"
            self.vae_device = "cuda:0"
            logger.info(
                f"Dual-GPU setup configured: Transformer -> {self.transformer_device}, "
                f"TextEncoder -> {self.text_encoder_device}, VAE -> {self.vae_device}"
            )
        else:
            self.transformer_device = "cuda:0"
            self.text_encoder_device = "cuda:0"
            self.vae_device = "cuda:0"
            logger.info("Single GPU detected. All components routed to cuda:0.")

    @staticmethod
    def _move_tensors_to_device(obj: Any, device: str) -> Any:
        """Recursively move PyTorch tensors inside nested args/kwargs to target device."""
        if torch is not None and isinstance(obj, torch.Tensor):
            return obj.to(device) if str(obj.device) != device else obj
        if isinstance(obj, tuple):
            return tuple(WanDualGpuPipeline._move_tensors_to_device(x, device) for x in obj)
        if isinstance(obj, list):
            return [WanDualGpuPipeline._move_tensors_to_device(x, device) for x in obj]
        if isinstance(obj, dict):
            return {k: WanDualGpuPipeline._move_tensors_to_device(v, device) for k, v in obj.items()}
        return obj

    def _register_cross_device_hooks(self, pipe: Any) -> None:
        """Configure pipeline execution device and hooks so tensors seamlessly cross GPU boundaries."""
        primary_dev = torch.device(self.transformer_device)

        # Override _execution_device on this pipeline's class so WanPipeline.__call__
        # allocates latents, timesteps, and prompt_embeds on transformer_device (cuda:1)
        # while _get_t5_prompt_embeds and vae.decode use their own module devices (cuda:0).
        class _DualGpuWanPipeline(pipe.__class__):
            @property
            def _execution_device(self) -> torch.device:
                return primary_dev

        pipe.__class__ = _DualGpuWanPipeline

        for comp_name, target_dev in [
            ("transformer", self.transformer_device),
            ("text_encoder", self.text_encoder_device),
            ("vae", self.vae_device),
        ]:
            module = getattr(pipe, comp_name, None)
            if module is None:
                continue

            def _make_pre_hook(dev: str):
                def _pre_hook(mod: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]):
                    new_args = self._move_tensors_to_device(args, dev)
                    new_kwargs = self._move_tensors_to_device(kwargs, dev)
                    return new_args, new_kwargs
                return _pre_hook

            module.register_forward_pre_hook(_make_pre_hook(target_dev), with_kwargs=True)

        # Enable VAE tiling/slicing if supported to prevent VRAM spikes during 81-frame 3D decoding
        if getattr(pipe, "vae", None) is not None:
            if hasattr(pipe.vae, "enable_tiling"):
                pipe.vae.enable_tiling()
            if hasattr(pipe.vae, "enable_slicing"):
                pipe.vae.enable_slicing()

            if hasattr(pipe.vae, "decode"):
                orig_decode = pipe.vae.decode
                vae_dev = self.vae_device

                def _wrapped_decode(z: Any, *args: Any, **kwargs: Any) -> Any:
                    if torch is not None and torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    z_dev = self._move_tensors_to_device(z, vae_dev)
                    new_args = self._move_tensors_to_device(args, vae_dev)
                    new_kwargs = self._move_tensors_to_device(kwargs, vae_dev)
                    return orig_decode(z_dev, *new_args, **new_kwargs)

                pipe.vae.decode = _wrapped_decode

    def load_model(self) -> None:
        """Load WanPipeline and distribute components to their designated GPUs."""
        if self.pipeline is not None:
            logger.info("WanPipeline already initialized and loaded in memory.")
            return

        if torch is None:
            raise RuntimeError("PyTorch is not installed. Please install torch with CUDA support.")

        local_path = Path(self.model_source)
        if local_path.exists():
            from app.system_info import check_model_files
            mstat = check_model_files(local_path)
            if not mstat["is_ready"]:
                raise RuntimeError(
                    f"Wan2.1 model checkpoint is not complete: {mstat['download_progress_label']}. "
                    f"Missing: {', '.join(mstat['missing_components'])}"
                )

        logger.info(f"Loading Wan2.1-T2V-1.3B pipeline from: {self.model_source}")
        t0 = time.time()

        from diffusers import AutoencoderKLWan, WanPipeline

        # 1. Load VAE in float32 for numerical stability
        vae = AutoencoderKLWan.from_pretrained(
            self.model_source,
            subfolder="vae",
            torch_dtype=torch.float32,
        )

        # 2. Instantiate pipeline with bfloat16 for transformer & text_encoder
        dtype = torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16
        pipe = WanPipeline.from_pretrained(
            self.model_source,
            vae=vae,
            torch_dtype=dtype,
        )

        # 3. Apply Multi-GPU or Single-GPU component placement
        is_multi_gpu = len({self.transformer_device, self.text_encoder_device, self.vae_device}) > 1
        if is_multi_gpu:
            logger.info(f"Moving transformer to dedicated compute device: {self.transformer_device}")
            pipe.transformer.to(self.transformer_device)

            logger.info(f"Moving text_encoder to auxiliary device: {self.text_encoder_device}")
            pipe.text_encoder.to(self.text_encoder_device)

            logger.info(f"Moving VAE to auxiliary device: {self.vae_device}")
            pipe.vae.to(self.vae_device)

            self._register_cross_device_hooks(pipe)
        else:
            if self.transformer_device != "cpu" and torch.cuda.is_available():
                pipe.to(self.transformer_device)

        self.pipeline = pipe
        elapsed = round(time.time() - t0, 2)
        logger.info(f"WanPipeline loaded successfully in {elapsed}s.")

    def generate_video(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 832,
        height: int = 480,
        num_frames: int = 81,
        num_inference_steps: int = 35,
        guidance_scale: float = 5.0,
        seed: int = -1,
        fps: int = 16,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Generate a video and export MP4, thumbnail, and metadata JSON."""
        if self.pipeline is None:
            self.load_model()

        if seed is None or seed < 0:
            seed = int(torch.randint(0, 2147483647, (1,)).item()) if torch else int(time.time())

        exec_dev = getattr(self.pipeline, "_execution_device", "cpu")
        generator = torch.Generator(device=exec_dev).manual_seed(seed) if torch else None
        neg_prompt = negative_prompt if negative_prompt is not None else DEFAULT_NEGATIVE_PROMPT

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = "".join(c if c.isalnum() else "_" for c in prompt[:25].strip().lower()).strip("_")
        base_name = f"wan21_{timestamp}_{slug}_{seed}"
        video_filename = f"{base_name}.mp4"
        thumb_filename = f"{base_name}.jpg"
        meta_filename = f"{base_name}.json"

        video_path = OUTPUTS_DIR / video_filename
        thumb_path = OUTPUTS_DIR / thumb_filename
        meta_path = OUTPUTS_DIR / meta_filename

        start_time = time.time()
        logger.info(
            f"Starting generation: {width}x{height}, {num_frames} frames, "
            f"{num_inference_steps} steps, cfg={guidance_scale}, seed={seed}"
        )

        def step_callback(pipe_self: Any, step_idx: int, timestep: Any, cb_kwargs: Dict[str, Any]) -> Dict[str, Any]:
            if progress_callback:
                step_num = step_idx + 1
                percent = int((step_num / num_inference_steps) * 100)
                elapsed = time.time() - start_time
                it_per_sec = step_num / elapsed if elapsed > 0 else 0
                eta = (num_inference_steps - step_num) / it_per_sec if it_per_sec > 0 else 0
                progress_callback({
                    "step": step_num,
                    "total_steps": num_inference_steps,
                    "percent": percent,
                    "elapsed_sec": round(elapsed, 1),
                    "eta_sec": round(eta, 1),
                    "it_per_sec": round(it_per_sec, 2),
                })
            return cb_kwargs

        # Execute diffusion generation
        try:
            pipe_kwargs = {
                "prompt": prompt,
                "negative_prompt": neg_prompt,
                "height": height,
                "width": width,
                "num_frames": num_frames,
                "guidance_scale": guidance_scale,
                "num_inference_steps": num_inference_steps,
                "generator": generator,
            }
            if progress_callback is not None:
                pipe_kwargs["callback_on_step_end"] = step_callback

            output = self.pipeline(**pipe_kwargs)
            frames = output.frames[0]
        except Exception as exc:
            logger.error(f"Inference error: {exc}", exc_info=True)
            if torch and torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise

        inference_time = round(time.time() - start_time, 2)
        logger.info(f"Denoising completed in {inference_time}s. Exporting MP4...")

        # Export frames to MP4 using imageio
        self._export_frames_to_mp4(frames, video_path, fps=fps)

        # Generate and save thumbnail from middle frame
        mid_idx = len(frames) // 2
        mid_frame = frames[mid_idx]
        self._save_thumbnail(mid_frame, thumb_path)

        # Build and write metadata sidecar
        metadata = {
            "prompt": prompt,
            "negative_prompt": neg_prompt,
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "fps": fps,
            "duration_seconds": round(num_frames / fps, 2),
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "seed": seed,
            "inference_time_seconds": inference_time,
            "created_at": datetime.now().isoformat(),
            "model_id": MODEL_ID,
            "video_file": video_filename,
            "thumbnail_file": thumb_filename,
            "device_mapping": {
                "transformer": self.transformer_device,
                "text_encoder": self.text_encoder_device,
                "vae": self.vae_device,
            },
        }

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        file_size_mb = round(video_path.stat().st_size / (1024 * 1024), 2)
        logger.info(f"Video saved: {video_path} ({file_size_mb} MB)")

        return {
            "video_filename": video_filename,
            "thumbnail_filename": thumb_filename,
            "metadata_filename": meta_filename,
            "video_path": str(video_path),
            "file_size_mb": file_size_mb,
            "metadata": metadata,
        }

    @staticmethod
    def _to_uint8_array(frame: Any) -> Any:
        """Convert PIL Image, float32 [0, 1] array, or Tensor to uint8 [0, 255] NumPy array."""
        if PILImage is not None and isinstance(frame, PILImage.Image):
            return np.array(frame, dtype=np.uint8)
        if torch is not None and isinstance(frame, torch.Tensor):
            frame = frame.detach().cpu().numpy()
        if isinstance(frame, np.ndarray):
            if np.issubdtype(frame.dtype, np.floating):
                if frame.max() <= 1.0 + 1e-3:
                    frame = np.clip(frame * 255.0, 0, 255).round().astype(np.uint8)
                else:
                    frame = np.clip(frame, 0, 255).round().astype(np.uint8)
            elif frame.dtype != np.uint8:
                frame = np.clip(frame, 0, 255).astype(np.uint8)
            return frame
        return np.asarray(frame, dtype=np.uint8)

    @staticmethod
    def _export_frames_to_mp4(frames: Any, output_path: Path, fps: int = 16) -> None:
        """Export list of PIL Images or NumPy arrays to an optimized web MP4."""
        frame_arrays = [WanDualGpuPipeline._to_uint8_array(f) for f in frames]

        # Write video with H.264 web-compatible profile
        imageio.mimwrite(
            str(output_path),
            frame_arrays,
            fps=fps,
            codec="libx264",
            output_params=["-pix_fmt", "yuv420p", "-crf", "19", "-preset", "medium"],
        )

    @staticmethod
    def _save_thumbnail(frame: Any, thumb_path: Path) -> None:
        """Save representative image frame as JPEG thumbnail."""
        if PILImage is not None and isinstance(frame, PILImage.Image):
            frame.save(thumb_path, format="JPEG", quality=85)
        else:
            arr = WanDualGpuPipeline._to_uint8_array(frame)
            img = PILImage.fromarray(arr)
            img.save(thumb_path, format="JPEG", quality=85)


# Global singleton instance
global_pipeline: Optional[WanDualGpuPipeline] = None


def get_pipeline() -> WanDualGpuPipeline:
    """Get or initialize the global pipeline singleton."""
    global global_pipeline
    if global_pipeline is None:
        global_pipeline = WanDualGpuPipeline()
    return global_pipeline
