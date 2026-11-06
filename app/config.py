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
MODEL_ID = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
MODEL_DIR = MODELS_DIR / "Wan2.1-T2V-1.3B-Diffusers"
EXPECTED_MODEL_GIB = 13.7

# Server Network Defaults
SERVER_HOST = os.environ.get("HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("PORT", "8202"))

# Dual-GPU Configuration Defaults
# GPU1 is designated for the heavy 3D DiT transformer; GPU0 for text encoder, VAE, & UI
DEFAULT_DEVICES = os.environ.get("CRAZY_VIDEO_DEVICES", "cuda:1,cuda:0")

# Generation Defaults
DEFAULT_STEPS = 35
DEFAULT_CFG = 5.0
DEFAULT_FPS = 16
DEFAULT_FRAMES = 81
DEFAULT_PRESET = "landscape_16_9"
DEFAULT_NEGATIVE_PROMPT = (
    "Bright lighting, overexposed, static, low quality, distorted details, "
    "blurry, watermark, text, grainy, jerky movement, artifacting"
)

# Aspect Ratio and Resolution Presets (Wan2.1 480p standard, frames must be 4k + 1)
PRESETS: Dict[str, Dict[str, Any]] = {
    "landscape_16_9": {
        "id": "landscape_16_9",
        "name": "16:9 Landscape",
        "badge": "Cinematic • 832x480",
        "width": 832,
        "height": 480,
        "aspect_ratio": "16:9",
        "default_frames": 81,
        "duration_sec": 5.0,
        "recommended_steps": 35,
        "description": "Standard cinematic widescreen format for desktop, YouTube, and horizontal displays.",
    },
    "portrait_9_16": {
        "id": "portrait_9_16",
        "name": "9:16 Portrait",
        "badge": "Mobile • 480x832",
        "width": 480,
        "height": 832,
        "aspect_ratio": "9:16",
        "default_frames": 81,
        "duration_sec": 5.0,
        "recommended_steps": 35,
        "description": "Vertical format optimized for mobile feeds, TikTok, Instagram Reels, and Shorts.",
    },
    "square_1_1": {
        "id": "square_1_1",
        "name": "1:1 Square",
        "badge": "Social • 624x624",
        "width": 624,
        "height": 624,
        "aspect_ratio": "1:1",
        "default_frames": 65,
        "duration_sec": 4.0,
        "recommended_steps": 35,
        "description": "Balanced square frame for social feeds, album covers, and avatar loops.",
    },
    "classic_4_3": {
        "id": "classic_4_3",
        "name": "4:3 Classic",
        "badge": "Retro • 704x544",
        "width": 704,
        "height": 544,
        "aspect_ratio": "4:3",
        "default_frames": 49,
        "duration_sec": 3.0,
        "recommended_steps": 30,
        "description": "Traditional television and animation aspect ratio.",
    },
    "draft_16_9": {
        "id": "draft_16_9",
        "name": "16:9 Quick Draft",
        "badge": "Fast • 33 Frames",
        "width": 832,
        "height": 480,
        "aspect_ratio": "16:9",
        "default_frames": 33,
        "duration_sec": 2.0,
        "recommended_steps": 25,
        "description": "Short preview clip for rapid prompt tuning and motion testing.",
    },
}

# Supported frame counts (Wan2.1 requires 4k + 1)
VALID_FRAME_COUNTS = [17, 33, 49, 65, 81]

# Model Profile Registry
MODEL_PROFILES: Dict[str, Dict[str, Any]] = {
    "wan21_13b": {
        "id": "wan21_13b",
        "name": "Wan2.1-T2V-1.3B",
        "repo_id": MODEL_ID,
        "description": "State-of-the-art 1.3B Text-to-Video diffusion transformer with 3D Causal VAE.",
        "category": "Wan2.1 Diffusion (Dual-GPU)",
        "engine": "diffusers",
        "local_dir": str(MODEL_DIR),
        "total_expected_gib": EXPECTED_MODEL_GIB,
        "components": {
            "transformer": {
                "name": "WanTransformer3DModel",
                "device": "cuda:1",
                "dtype": "bfloat16",
                "description": "Primary 3D DiT denoising transformer hosted on dedicated GPU 1.",
            },
            "text_encoder": {
                "name": "UMT5EncoderModel",
                "device": "cuda:0",
                "dtype": "bfloat16",
                "description": "UMT5-XXL text encoder hosted on GPU 0 with prompt caching.",
            },
            "vae": {
                "name": "AutoencoderKLWan",
                "device": "cuda:0",
                "dtype": "float32",
                "description": "3D Causal VAE decoder running on GPU 0.",
            },
        },
    }
}
