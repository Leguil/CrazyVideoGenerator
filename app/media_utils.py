# Author: François Guillemette
"""Image conditioning preparation, frame conversion, and MP4/JPEG export utilities."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from app.config import DEFAULT_FPS

try:
    import torch
except ImportError:
    torch = None

try:
    import numpy as np
    from PIL import Image as PILImage
    from PIL import ImageOps as PILImageOps
except ImportError:
    np = None
    PILImage = None
    PILImageOps = None

try:
    import imageio
except ImportError:
    imageio = None


def prepare_pil_image(init_image: Any, width: int, height: int) -> Any:
    """Decode and center-crop/resize an input image to exact (width, height)."""
    if PILImage is None:
        raise RuntimeError("Pillow is required for starting image conditioning.")

    if isinstance(init_image, PILImage.Image):
        img = init_image
    elif isinstance(init_image, Path) or (
        isinstance(init_image, str)
        and not init_image.startswith("data:")
        and len(init_image) < 260
        and Path(init_image).exists()
    ):
        img = PILImage.open(init_image)
    elif isinstance(init_image, str):
        b64_data = init_image.split(",", 1)[1] if "," in init_image else init_image
        raw_bytes = base64.b64decode(b64_data)
        img = PILImage.open(io.BytesIO(raw_bytes))
    else:
        raise ValueError("Unsupported init_image format.")

    img = img.convert("RGB")
    resample = getattr(PILImage, "Resampling", PILImage).LANCZOS
    if PILImageOps is not None:
        img = PILImageOps.fit(img, (width, height), method=resample)
    else:
        img = img.resize((width, height), resample)
    return img


def to_uint8_array(frame: Any) -> Any:
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


def export_frames_to_mp4(
    frames: Any,
    output_path: Path,
    fps: int = DEFAULT_FPS,
    interpolator: str = "none",
) -> None:
    """Export list of PIL Images or NumPy arrays to an optimized web MP4.
    
    If interpolator is 'rife_2x' or 'motion_2x', applies motion-compensated frame interpolation
    via FFmpeg's minterpolate filter to double the frame rate (e.g. 24 -> 48 fps) for ultra-smooth motion.
    """
    frame_arrays = [to_uint8_array(f) for f in frames]
    target_fps = int(fps)

    # Use a temporary intermediate path if interpolation is requested
    write_target = output_path if interpolator in ("none", "", None) else output_path.with_name(f"raw_{output_path.name}")

    # Write video with H.264 web-compatible profile (imageio-ffmpeg sets -pix_fmt yuv420p by default)
    imageio.mimwrite(
        str(write_target),
        frame_arrays,
        fps=target_fps,
        codec="libx264",
        output_params=["-crf", "19", "-preset", "medium"],
    )

    if interpolator in ("rife_2x", "motion_2x", "interpolate_2x"):
        import subprocess
        smooth_fps = target_fps * 2
        logger.info(f"Applying 2x motion-compensated frame interpolation: {target_fps} fps -> {smooth_fps} fps...")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(write_target),
            "-filter:v",
            f"minterpolate='fps={smooth_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1'",
            "-c:v",
            "libx264",
            "-crf",
            "19",
            "-preset",
            "fast",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            try:
                write_target.unlink()
            except Exception:
                pass
            logger.info(f"Frame interpolation complete -> {output_path} ({smooth_fps} fps)")
        else:
            logger.warning(f"FFmpeg interpolation error (falling back to raw video): {res.stderr}")
            if write_target != output_path and write_target.exists():
                write_target.replace(output_path)


def save_thumbnail(frame: Any, thumb_path: Path) -> None:
    """Save representative image frame as JPEG thumbnail."""
    if PILImage is not None and isinstance(frame, PILImage.Image):
        frame.save(thumb_path, format="JPEG", quality=85)
    else:
        arr = to_uint8_array(frame)
        img = PILImage.fromarray(arr)
        img.save(thumb_path, format="JPEG", quality=85)
