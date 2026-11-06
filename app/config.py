# Author: François Guillemette
"""Configuration constants, presets, and model profiles for CrazyVideoGenerator."""

import os
from pathlib import Path
from typing import Any, Dict

# Base Directory Paths
APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
BRAND_DIR = ROOT_DIR / "brand"
MODELS_DIR = ROOT_DIR / "models"
OUTPUTS_DIR = ROOT_DIR / "outputs"
STATIC_DIR = APP_DIR / "static"

# Ensure runtime directories exist
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Primary Model Configuration
MODEL_ID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
MODEL_DIR = MODELS_DIR / "Wan2.2-TI2V-5B-Diffusers"
EXPECTED_MODEL_GIB = 31.9

# Server Network Defaults
SERVER_HOST = os.environ.get("HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("PORT", "8202"))

# Dual-GPU Configuration Defaults
# GPU1 is designated for the heavy 3D DiT transformer; GPU0 for text encoder, VAE, & UI
DEFAULT_DEVICES = os.environ.get("CRAZY_VIDEO_DEVICES", "cuda:1,cuda:0")

# Generation Defaults
DEFAULT_STEPS = 40
DEFAULT_CFG = 5.0
DEFAULT_FPS = 24
DEFAULT_FRAMES = 81
DEFAULT_PRESET = "hd_16_9"
DEFAULT_NEGATIVE_PROMPT = (
    "Bright lighting, overexposed, static, low quality, distorted details, "
    "blurry, watermark, text, grainy, jerky movement, artifacting"
)

# Aspect Ratio and Resolution Presets (Wan2.2 TI2V-5B requires multiples of 32 for width/height, frames must be 4k + 1)
PRESETS: Dict[str, Dict[str, Any]] = {
    "hd_16_9": {
        "id": "hd_16_9",
        "name": "720p HD Landscape",
        "badge": "HD • 1280x704",
        "width": 1280,
        "height": 704,
        "aspect_ratio": "16:9",
        "default_frames": 81,
        "duration_sec": 3.4,
        "recommended_steps": 40,
        "description": "Native Wan2.2 720p high-definition widescreen format.",
    },
    "hd_9_16": {
        "id": "hd_9_16",
        "name": "720p HD Portrait",
        "badge": "HD Mobile • 704x1280",
        "width": 704,
        "height": 1280,
        "aspect_ratio": "9:16",
        "default_frames": 81,
        "duration_sec": 3.4,
        "recommended_steps": 40,
        "description": "Native Wan2.2 720p vertical format for Reels, Shorts, and TikTok.",
    },
    "landscape_16_9": {
        "id": "landscape_16_9",
        "name": "480p Landscape",
        "badge": "Standard • 832x480",
        "width": 832,
        "height": 480,
        "aspect_ratio": "16:9",
        "default_frames": 81,
        "duration_sec": 3.4,
        "recommended_steps": 35,
        "description": "Fast 480p widescreen format for desktop and rapid iteration.",
    },
    "portrait_9_16": {
        "id": "portrait_9_16",
        "name": "480p Portrait",
        "badge": "Mobile • 480x832",
        "width": 480,
        "height": 832,
        "aspect_ratio": "9:16",
        "default_frames": 81,
        "duration_sec": 3.4,
        "recommended_steps": 35,
        "description": "Vertical 480p format optimized for mobile feeds.",
    },
    "square_1_1": {
        "id": "square_1_1",
        "name": "1:1 Square",
        "badge": "Social • 640x640",
        "width": 640,
        "height": 640,
        "aspect_ratio": "1:1",
        "default_frames": 65,
        "duration_sec": 2.7,
        "recommended_steps": 35,
        "description": "Balanced square frame (multiple of 32) for social feeds and loops.",
    },
    "draft_16_9": {
        "id": "draft_16_9",
        "name": "16:9 Quick Draft",
        "badge": "Fast • 33 Frames",
        "width": 832,
        "height": 480,
        "aspect_ratio": "16:9",
        "default_frames": 33,
        "duration_sec": 1.4,
        "recommended_steps": 25,
        "description": "Short preview clip for rapid prompt tuning and motion testing.",
    },
}

# Supported frame counts (Wan2.2 requires 4k + 1)
VALID_FRAME_COUNTS = [17, 33, 49, 65, 81, 97, 121]

# Model Profile Registry
MODEL_PROFILES: Dict[str, Dict[str, Any]] = {
    "wan22_5b": {
        "id": "wan22_5b",
        "name": "Wan2.2-TI2V-5B",
        "repo_id": MODEL_ID,
        "description": "State-of-the-art 5B Unified Text-to-Video & Image-to-Video diffusion transformer with 16x16x4 Wan2.2-VAE.",
        "category": "Wan2.2 Diffusion (Dual-GPU)",
        "engine": "diffusers",
        "local_dir": str(MODEL_DIR),
        "total_expected_gib": EXPECTED_MODEL_GIB,
        "components": {
            "transformer": {
                "name": "WanTransformer3DModel (5B)",
                "device": "cuda:1",
                "dtype": "bfloat16",
                "description": "Primary 5B 3D DiT denoising transformer hosted on dedicated GPU 1.",
            },
            "text_encoder": {
                "name": "UMT5EncoderModel",
                "device": "cuda:0",
                "dtype": "bfloat16",
                "description": "UMT5-XXL text encoder hosted on GPU 0.",
            },
            "vae": {
                "name": "AutoencoderKLWan (16x16x4)",
                "device": "cuda:0",
                "dtype": "float32",
                "description": "Wan2.2 high-compression 3D Causal VAE running on GPU 0.",
            },
        },
    }
}
