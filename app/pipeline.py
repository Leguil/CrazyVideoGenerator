# Author: François Guillemette
"""Dual-GPU Wan2.2-TI2V-5B inference pipeline and video export utilities."""

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
    DEFAULT_FLOW_SHIFT,
    DEFAULT_FPS,
    DEFAULT_FRAMES,
    DEFAULT_INTERPOLATOR,
    DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_PRESET,
    DEFAULT_STEPS,
    LORAS_DIR,
    MODEL_DIR,
    MODEL_ID,
    OUTPUTS_DIR,
    PRESETS,
)
from app.media_utils import (
    export_frames_to_mp4,
    prepare_pil_image,
    save_thumbnail,
    to_uint8_array,
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


class WanDualGpuPipeline:
    """Manager for loading and running Wan2.2-TI2V-5B distributed across dual GPUs."""

    def __init__(self, model_source: Optional[str] = None, devices: Optional[str] = None):
        self.model_source = model_source or (str(MODEL_DIR) if MODEL_DIR.exists() else MODEL_ID)
        self.devices_str = devices or DEFAULT_DEVICES
        self.pipeline: Any = None
        self.i2v_pipeline: Any = None
        self.transformer_device: str = "cuda:0"
        self.text_encoder_device: str = "cuda:0"
        self.vae_device: str = "cuda:0"
        self.active_lora_name: Optional[str] = None
        self.active_lora_scale: float = 0.0
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

    def _register_cross_device_hooks(self, pipe: Any, i2v_pipe: Any = None) -> None:
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

        if i2v_pipe is not None:
            base_cb_inputs = list(
                getattr(i2v_pipe, "_callback_tensor_inputs", ["latents", "prompt_embeds", "negative_prompt_embeds"])
            )
            for extra_k in ("first_frame_mask", "condition"):
                if extra_k not in base_cb_inputs:
                    base_cb_inputs.append(extra_k)

            class _DualGpuWanI2VPipeline(i2v_pipe.__class__):
                _callback_tensor_inputs = base_cb_inputs

                @property
                def _execution_device(self) -> torch.device:
                    return primary_dev

            i2v_pipe.__class__ = _DualGpuWanI2VPipeline

        for comp_name, target_dev in [
            ("transformer", self.transformer_device),
            ("text_encoder", self.text_encoder_device),
            ("vae", self.vae_device),
        ]:
            module = getattr(pipe, comp_name, None)
            if module is None:
                continue

            def _make_pre_hook(dev: str, name: str = comp_name):
                def _pre_hook(mod: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]):
                    actual_dev = dev
                    try:
                        p = next(mod.parameters(), None)
                        if p is not None:
                            cur_dev = str(p.device)
                            if cur_dev != dev:
                                can_move = True
                                if dev.startswith("cuda") and torch is not None and torch.cuda.is_available():
                                    free_bytes, _ = torch.cuda.mem_get_info(torch.device(dev))
                                    min_bytes = int(11.2 * (1024 ** 3)) if name == "text_encoder" else int(1.0 * (1024 ** 3))
                                    if free_bytes < min_bytes:
                                        can_move = False
                                        actual_dev = cur_dev
                                if can_move:
                                    mod.to(dev)
                                    if name == "text_encoder":
                                        self.text_encoder_device = dev
                            p_after = next(mod.parameters(), None)
                            if p_after is not None:
                                actual_dev = str(p_after.device)
                    except Exception:
                        try:
                            p_fallback = next(mod.parameters(), None)
                            if p_fallback is not None:
                                actual_dev = str(p_fallback.device)
                        except Exception:
                            pass
                    new_args = self._move_tensors_to_device(args, actual_dev)
                    new_kwargs = self._move_tensors_to_device(kwargs, actual_dev)
                    return new_args, new_kwargs
                return _pre_hook

            module.register_forward_pre_hook(_make_pre_hook(target_dev, comp_name), with_kwargs=True)

        # Enable VAE tiling/slicing if supported to prevent VRAM spikes during 3D decoding
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
                        if vae_dev.startswith("cuda") and getattr(pipe, "text_encoder", None) is not None:
                            try:
                                free_bytes, _ = torch.cuda.mem_get_info(torch.device(vae_dev))
                                if free_bytes < int(3.8 * (1024 ** 3)):
                                    logger.info("Temporarily offloading text_encoder to CPU to free VRAM for 720p VAE decode...")
                                    pipe.text_encoder.to("cpu")
                                    self.text_encoder_device = "cpu"
                                    torch.cuda.empty_cache()
                            except Exception:
                                pass
                    z_dev = self._move_tensors_to_device(z, vae_dev)
                    new_args = self._move_tensors_to_device(args, vae_dev)
                    new_kwargs = self._move_tensors_to_device(kwargs, vae_dev)
                    return orig_decode(z_dev, *new_args, **new_kwargs)

                pipe.vae.decode = _wrapped_decode

            if hasattr(pipe.vae, "encode"):
                orig_encode = pipe.vae.encode
                vae_dev = self.vae_device

                def _wrapped_encode(x: Any, *args: Any, **kwargs: Any) -> Any:
                    x_dev = self._move_tensors_to_device(x, vae_dev)
                    new_args = self._move_tensors_to_device(args, vae_dev)
                    new_kwargs = self._move_tensors_to_device(kwargs, vae_dev)
                    return orig_encode(x_dev, *new_args, **new_kwargs)

                pipe.vae.encode = _wrapped_encode

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
                    f"Wan2.2 model checkpoint is not complete: {mstat['download_progress_label']}. "
                    f"Missing: {', '.join(mstat['missing_components'])}"
                )

        logger.info(f"Loading Wan2.2-TI2V-5B pipeline from: {self.model_source}")
        t0 = time.time()

        from diffusers import AutoencoderKLWan, WanImageToVideoPipeline, WanPipeline

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

        # Build companion WanImageToVideoPipeline sharing the exact same loaded modules (0 extra VRAM)
        i2v_pipe = WanImageToVideoPipeline(
            tokenizer=pipe.tokenizer,
            text_encoder=pipe.text_encoder,
            vae=pipe.vae,
            scheduler=pipe.scheduler,
            image_processor=getattr(pipe, "image_processor", None),
            image_encoder=getattr(pipe, "image_encoder", None),
            transformer=pipe.transformer,
            transformer_2=getattr(pipe, "transformer_2", None),
            boundary_ratio=getattr(pipe.config, "boundary_ratio", None),
            expand_timesteps=bool(getattr(pipe.config, "expand_timesteps", True)),
        )

        # 3. Apply Multi-GPU or Single-GPU component placement
        is_multi_gpu = len({self.transformer_device, self.text_encoder_device, self.vae_device}) > 1
        if is_multi_gpu:
            logger.info(f"Moving transformer to dedicated compute device: {self.transformer_device}")
            pipe.transformer.to(self.transformer_device)

            logger.info(f"Moving VAE to auxiliary device: {self.vae_device}")
            pipe.vae.to(self.vae_device)

            te_dev = self.text_encoder_device
            if te_dev.startswith("cuda") and torch.cuda.is_available():
                try:
                    free_bytes, _ = torch.cuda.mem_get_info(torch.device(te_dev))
                    free_gib = free_bytes / (1024.0 ** 3)
                    if free_gib < 11.2:
                        logger.info(
                            f"Auxiliary device {te_dev} has {free_gib:.2f} GiB free VRAM (< 11.2 GiB needed for UMT5-XXL). "
                            f"Keeping text_encoder on CPU to preserve GPU VRAM for 720p VAE & Transformer."
                        )
                        te_dev = "cpu"
                except Exception:
                    pass
            self.text_encoder_device = te_dev
            logger.info(f"Moving text_encoder to device: {self.text_encoder_device}")
            pipe.text_encoder.to(self.text_encoder_device)

            self._register_cross_device_hooks(pipe, i2v_pipe=i2v_pipe)
        else:
            if self.transformer_device != "cpu" and torch.cuda.is_available():
                pipe.to(self.transformer_device)

        self.pipeline = pipe
        self.i2v_pipeline = i2v_pipe
        elapsed = round(time.time() - t0, 2)
        logger.info(f"Wan2.2 TI2V-5B pipeline loaded successfully in {elapsed}s.")

    _prepare_pil_image = staticmethod(prepare_pil_image)
    _to_uint8_array = staticmethod(to_uint8_array)
    _export_frames_to_mp4 = staticmethod(export_frames_to_mp4)
    _save_thumbnail = staticmethod(save_thumbnail)

    def _encode_init_image(
        self,
        init_image: Any,
        width: int,
        height: int,
        exec_dev: Any,
    ) -> Any:
        """Decode, resize/crop, and encode a starting image into normalized Wan VAE latent space."""
        if PILImage is None or torch is None:
            raise RuntimeError("PIL and PyTorch are required for starting image conditioning.")

        img = self._prepare_pil_image(init_image, width, height)

        # Convert RGB [0, 255] -> float32 [-1.0, 1.0] with shape [1, 3, 1, H, W]
        arr = np.asarray(img, dtype=np.float32) / 127.5 - 1.0
        vae = self.pipeline.vae
        vae_dtype = getattr(vae, "dtype", torch.float32)
        img_tensor = (
            torch.from_numpy(arr)
            .permute(2, 0, 1)
            .unsqueeze(0)
            .unsqueeze(2)
            .to(device=self.vae_device, dtype=vae_dtype)
        )

        with torch.no_grad():
            enc_out = vae.encode(img_tensor)
            raw_latent = enc_out.latent_dist.mode()

        latents_mean = (
            torch.tensor(vae.config.latents_mean, device=exec_dev, dtype=torch.float32)
            .view(1, vae.config.z_dim, 1, 1, 1)
        )
        latents_std = (
            1.0
            / torch.tensor(vae.config.latents_std, device=exec_dev, dtype=torch.float32)
            .view(1, vae.config.z_dim, 1, 1, 1)
        )
        first_frame_latent = (raw_latent.to(device=exec_dev, dtype=torch.float32) - latents_mean) * latents_std
        return first_frame_latent

    def _apply_lora(self, lora_name: Optional[str], lora_scale: float = 0.8) -> None:
        """Dynamically load, adjust scale, or unload a Wan2.2-TI2V-5B LoRA adapter."""
        if self.pipeline is None:
            return

        clean_name = (lora_name or "").strip()
        if not clean_name or clean_name.lower() == "none" or lora_scale <= 0.0:
            if self.active_lora_name is not None:
                logger.info(f"Unloading active LoRA adapter: {self.active_lora_name}")
                try:
                    self.pipeline.unload_lora_weights()
                except Exception as exc:
                    logger.warning(f"Error unloading LoRA weights: {exc}")
                self.active_lora_name = None
                self.active_lora_scale = 0.0
            return

        lora_path = (LORAS_DIR / Path(clean_name).name).resolve()
        if not str(lora_path).startswith(str(LORAS_DIR.resolve())) or not lora_path.exists():
            raise FileNotFoundError(f"LoRA file '{clean_name}' not found in {LORAS_DIR}")

        clamped_scale = float(max(0.0, min(2.0, lora_scale)))
        if self.active_lora_name != lora_path.name:
            if self.active_lora_name is not None:
                logger.info(f"Unloading previous LoRA adapter '{self.active_lora_name}' before loading '{lora_path.name}'")
                try:
                    self.pipeline.unload_lora_weights()
                except Exception as exc:
                    logger.warning(f"Error unloading previous LoRA: {exc}")
                self.active_lora_name = None

            logger.info(f"Loading LoRA adapter '{lora_path.name}' (scale={clamped_scale})...")
            from safetensors.torch import load_file

            raw_sd = load_file(str(lora_path), device="cpu")
            normalized_sd: Dict[str, Any] = {}
            for k, v in raw_sd.items():
                nk = k
                if nk.startswith("base_model.model."):
                    nk = nk[len("base_model.model.") :]
                if nk.startswith("model.diffusion_model."):
                    nk = "diffusion_model." + nk[len("model.diffusion_model.") :]
                elif nk.startswith("blocks.") and (".self_attn." in nk or ".cross_attn." in nk or ".ffn." in nk):
                    nk = "diffusion_model." + nk
                normalized_sd[nk] = v

            # Load LoRA into transformer via diffusers
            self.pipeline.load_lora_weights(normalized_sd, adapter_name="active_lora")

            # Ensure all newly instantiated adapter parameters in transformer match the designated transformer device
            if self.transformer_device != "cpu" and torch is not None and torch.cuda.is_available():
                self.pipeline.transformer.to(
                    device=self.transformer_device,
                    dtype=self.pipeline.transformer.dtype,
                )

            # Mirror adapter registration to i2v_pipeline if instantiated
            if self.i2v_pipeline is not None and hasattr(self.i2v_pipeline, "_lora_loadable_modules"):
                try:
                    if hasattr(self.i2v_pipeline, "set_adapters"):
                        self.i2v_pipeline.set_adapters(["active_lora"], adapter_weights=[clamped_scale])
                except Exception as exc:
                    logger.debug(f"Note: i2v_pipeline adapter mirror notice: {exc}")

            self.active_lora_name = lora_path.name

        self.pipeline.set_adapters(["active_lora"], adapter_weights=[clamped_scale])
        if self.i2v_pipeline is not None and hasattr(self.i2v_pipeline, "set_adapters"):
            try:
                self.i2v_pipeline.set_adapters(["active_lora"], adapter_weights=[clamped_scale])
            except Exception:
                pass
        self.active_lora_scale = clamped_scale
        logger.info(f"Active LoRA set: {self.active_lora_name} @ scale {self.active_lora_scale}")

    def generate_video(
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
        flow_shift: float = DEFAULT_FLOW_SHIFT,
        interpolator: str = DEFAULT_INTERPOLATOR,
        init_image: Optional[Any] = None,
        image_strength: float = 0.85,
        lora_name: Optional[str] = None,
        lora_scale: float = 0.8,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Generate a video and export MP4, thumbnail, and metadata JSON."""
        if self.pipeline is None:
            self.load_model()

        self._apply_lora(lora_name, lora_scale)

        # Apply custom flow-matching shift to scheduler if modified
        clamped_shift = float(max(1.0, min(16.0, flow_shift if flow_shift is not None else DEFAULT_FLOW_SHIFT)))
        sched = getattr(self.pipeline, "scheduler", None)
        if sched is not None and hasattr(sched.config, "flow_shift"):
            if getattr(sched.config, "flow_shift", None) != clamped_shift:
                sched.config.flow_shift = clamped_shift
                logger.info(f"Updated scheduler flow_shift to {clamped_shift}")
        if self.i2v_pipeline is not None and hasattr(getattr(self.i2v_pipeline, "scheduler", None), "config"):
            if getattr(self.i2v_pipeline.scheduler.config, "flow_shift", None) != clamped_shift:
                self.i2v_pipeline.scheduler.config.flow_shift = clamped_shift

        if seed is None or seed < 0:
            seed = int(torch.randint(0, 2147483647, (1,)).item()) if torch else int(time.time())

        exec_dev = getattr(self.pipeline, "_execution_device", "cpu")
        generator = torch.Generator(device=exec_dev).manual_seed(seed) if torch else None
        neg_prompt = negative_prompt if negative_prompt is not None else DEFAULT_NEGATIVE_PROMPT

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = "".join(c if c.isalnum() else "_" for c in prompt[:25].strip().lower()).strip("_")
        base_name = f"wan22_{timestamp}_{slug}_{seed}"
        video_filename = f"{base_name}.mp4"
        thumb_filename = f"{base_name}.jpg"
        meta_filename = f"{base_name}.json"

        video_path = OUTPUTS_DIR / video_filename
        thumb_path = OUTPUTS_DIR / thumb_filename
        meta_path = OUTPUTS_DIR / meta_filename

        start_time = time.time()
        has_init_image = bool(init_image)
        clamped_strength = float(max(0.1, min(1.0, image_strength if image_strength is not None else 0.85)))
        use_native_i2v = bool(
            has_init_image
            and self.i2v_pipeline is not None
            and getattr(self.pipeline.config, "expand_timesteps", False)
        )
        i2v_cutoff_step = max(1, int(round(clamped_strength * num_inference_steps)))
        logger.info(
            f"Starting generation: {width}x{height}, {num_frames} frames, "
            f"{num_inference_steps} steps, cfg={guidance_scale}, seed={seed}, "
            f"init_image={has_init_image}"
            + (
                f" (native_i2v={use_native_i2v}, strength={clamped_strength}, cutoff_step={i2v_cutoff_step}/{num_inference_steps})"
                if has_init_image
                else ""
            )
        )

        pil_init_image = None
        first_frame_latent = None
        init_noise = None
        if has_init_image:
            if use_native_i2v:
                pil_init_image = self._prepare_pil_image(init_image, width, height)
            else:
                first_frame_latent = self._encode_init_image(init_image, width, height, exec_dev)
                vae_scale_temp = getattr(self.pipeline, "vae_scale_factor_temporal", 4)
                vae_scale_spat = getattr(self.pipeline, "vae_scale_factor_spatial", 16)
                in_channels = getattr(self.pipeline.transformer.config, "in_channels", 48)
                num_latent_frames = (num_frames - 1) // vae_scale_temp + 1
                latent_shape = (
                    1,
                    in_channels,
                    num_latent_frames,
                    height // vae_scale_spat,
                    width // vae_scale_spat,
                )
                init_noise = torch.randn(
                    latent_shape,
                    generator=generator,
                    device=exec_dev,
                    dtype=torch.float32,
                )

        def step_callback(pipe_self: Any, step_idx: int, timestep: Any, cb_kwargs: Dict[str, Any]) -> Dict[str, Any]:
            if (
                use_native_i2v
                and clamped_strength < 1.0
                and step_idx == (i2v_cutoff_step - 1)
                and i2v_cutoff_step < num_inference_steps
                and "first_frame_mask" in cb_kwargs
                and "condition" in cb_kwargs
                and "latents" in cb_kwargs
            ):
                latents = cb_kwargs["latents"]
                condition = cb_kwargs["condition"]
                first_frame_mask = cb_kwargs["first_frame_mask"]
                sigmas = getattr(pipe_self.scheduler, "sigmas", None)
                sigma_next = float(sigmas[step_idx + 1]) if (sigmas is not None and (step_idx + 1) < len(sigmas)) else 0.0
                # Transition frame 0 onto the active flow-matching noise trajectory for the remaining (1 - strength) steps
                latents[:, :, :1, :, :] = (
                    (1.0 - sigma_next) * condition[:, :, :1, :, :].to(latents.dtype)
                    + sigma_next * latents[:, :, :1, :, :]
                )
                first_frame_mask[:, :, :1, :, :] = 1.0
                cb_kwargs["latents"] = latents

            if first_frame_latent is not None and init_noise is not None and "latents" in cb_kwargs:
                latents = cb_kwargs["latents"]
                sigmas = getattr(pipe_self.scheduler, "sigmas", None)
                if sigmas is not None and (step_idx + 1) < len(sigmas):
                    sigma_next = float(sigmas[step_idx + 1])
                else:
                    sigma_next = 0.0

                # Exact flow-matching trajectory target for the starting image at latent frame 0
                target_first = (1.0 - sigma_next) * first_frame_latent + sigma_next * init_noise[:, :, :1, :, :]
                lat_f32 = latents[:, :, :1, :, :].float()
                latents[:, :, :1, :, :] = (
                    (1.0 - clamped_strength) * lat_f32 + clamped_strength * target_first
                ).to(latents.dtype)

                # Soft temporal ramp over latent frames 1..2 during high-noise early steps for smooth motion onset
                if sigma_next > 0.55 and latents.shape[2] > 1:
                    max_ramp = min(3, latents.shape[2])
                    for f_idx in range(1, max_ramp):
                        w = clamped_strength * (sigma_next - 0.55) * (0.45 ** f_idx)
                        target_f = (1.0 - sigma_next) * first_frame_latent + sigma_next * init_noise[:, :, f_idx : f_idx + 1, :, :]
                        cur_f = latents[:, :, f_idx : f_idx + 1, :, :].float()
                        latents[:, :, f_idx : f_idx + 1, :, :] = ((1.0 - w) * cur_f + w * target_f).to(latents.dtype)

                cb_kwargs["latents"] = latents

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
            if init_noise is not None:
                pipe_kwargs["latents"] = init_noise.clone()
            need_step_cb = (
                progress_callback is not None
                or first_frame_latent is not None
                or (use_native_i2v and clamped_strength < 1.0)
            )
            if need_step_cb:
                pipe_kwargs["callback_on_step_end"] = step_callback

            if use_native_i2v and pil_init_image is not None:
                pipe_kwargs["image"] = pil_init_image
                if clamped_strength < 1.0:
                    pipe_kwargs["callback_on_step_end_tensor_inputs"] = ["latents", "first_frame_mask", "condition"]
                output = self.i2v_pipeline(**pipe_kwargs)
            else:
                output = self.pipeline(**pipe_kwargs)
            frames = output.frames[0]
        except Exception as exc:
            logger.error(f"Inference error: {exc}", exc_info=True)
            if torch and torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise

        inference_time = round(time.time() - start_time, 2)
        logger.info(f"Denoising completed in {inference_time}s. Exporting MP4...")

        # Export frames to MP4 using imageio (with optional 2x frame interpolation)
        self._export_frames_to_mp4(frames, video_path, fps=fps, interpolator=interpolator)

        # Generate and save thumbnail from middle frame
        mid_idx = len(frames) // 2
        mid_frame = frames[mid_idx]
        self._save_thumbnail(mid_frame, thumb_path)

        effective_fps = fps * 2 if interpolator in ("rife_2x", "motion_2x", "interpolate_2x") else fps

        # Build and write metadata sidecar
        metadata = {
            "prompt": prompt,
            "negative_prompt": neg_prompt,
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "fps": fps,
            "effective_fps": effective_fps,
            "interpolator": interpolator,
            "flow_shift": clamped_shift,
            "duration_seconds": round(num_frames / fps, 2),
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "seed": seed,
            "has_init_image": has_init_image,
            "image_strength": round(clamped_strength, 2) if has_init_image else None,
            "generation_mode": "i2v" if has_init_image else "t2v",
            "lora_name": self.active_lora_name,
            "lora_scale": round(self.active_lora_scale, 2) if self.active_lora_name else None,
            "inference_time_seconds": inference_time,
            "generation_time_seconds": inference_time,
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


# Global singleton instance
global_pipeline: Optional[WanDualGpuPipeline] = None


def get_pipeline() -> WanDualGpuPipeline:
    """Get or initialize the global pipeline singleton."""
    global global_pipeline
    if global_pipeline is None:
        global_pipeline = WanDualGpuPipeline()
    return global_pipeline
