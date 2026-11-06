# Author: François Guillemette
# CrazyVideoGenerator — CrazyLogix Video Studio

**CrazyVideoGenerator** is a containerized, high-performance web studio for text-to-video and image-to-video synthesis using Alibaba's **Wan2.2-TI2V-5B** model (`Wan-AI/Wan2.2-TI2V-5B-Diffusers`). Engineered for dual-GPU workstations (such as dual NVIDIA GeForce RTX 5070 Ti 16 GB cards), it balances intensive 5B 3D diffusion computation with zero-overhead memory partitioning.

The application follows the official **CrazyLogix Brand Design System** (`brand/tokens.css`) with an explicit opt-in dark theme, the signature CrazyLogix Green accents, and a standardized Two-Tier Application Bar.

---

## Architecture & Dual-GPU Allocation

```
+-----------------------------------------------------------------------------+
|                          CrazyVideoGenerator Web UI                         |
|                 (Two-Tier Application Bar • WebSocket Stream)               |
+-----------------------------------------------------------------------------+
                                      │
                                      ▼
                        FastAPI Server (Port 8202)
                                      │
             ┌────────────────────────┴────────────────────────┐
             ▼                                                 ▼
      GPU 0 (RTX 5070 Ti)                               GPU 1 (RTX 5070 Ti)
  (Display Adapter + Aux)                           (100% Free Compute Card)
 ─────────────────────────                         ─────────────────────────
  • UMT5-XXL Text Encoder                           • WanTransformer3DModel (5B)
  • Prompt Embeddings                               • 3D Video DiT Denoising
  • Wan2.2 16×16×4 3D VAE                           • T2V & Native I2V Conditioning
  • MP4 / H.264 Video Exporter                      • 0 MB Windows Overhead
```

- **GPU 1 (`cuda:1`)**: Receives prompt and image embeddings and runs the 5B 3D Diffusion Transformer (`WanTransformer3DModel`, ~9.55 GiB in `bfloat16`) through all denoising steps. Because GPU 1 has no OS display overhead, it operates with peak throughput and zero memory thrashing.
- **GPU 0 (`cuda:0`)**: Primary display card handling prompt encoding (`UMT5EncoderModel`, with automatic CPU offload when display VRAM is constrained), high-compression 16×16×4 3D Causal VAE encoding/decoding (`AutoencoderKLWan`), web server request routing, and MP4 assembly.

---

## Features

- **CrazyLogix Brand Design System**:
  - Implements `brand/tokens.css` with standard `--cl-*` variables.
  - **Two-Tier Application Bar**:
    - **Tier 1 (Main Header)**: Brand lockup (`CrazyLogix - Insanely Simple`) with `crazylogix_logo.svg`, live dual-GPU VRAM telemetry pills, model readiness badge, light/dark theme switcher, and diagnostics.
    - **Tier 2 (Action Bar)**: Immediate workflow triggers (*Generate Video*, *Reset*, *Smoke Test*, *Output Gallery*).
  - Explicit dark theme selector (`:root[data-theme="dark"]`) synced to `localStorage["crazylogix_theme"]`.
- **Wan2.2-TI2V-5B Text-to-Video & Image-to-Video Support**:
  - Native Hugging Face `diffusers` `WanPipeline` (T2V) and `WanImageToVideoPipeline` (I2V) integration sharing weights in memory (`0` extra VRAM).
  - Optional **Starting Image Conditioning** with adjustable **Image Strength** (`0.10`–`1.00`).
  - Automatic in-place `float32` → `bfloat16` shard optimization after download (reducing disk footprint from ~31.9 GiB to ~22.6 GiB).
  - 720p HD & 480p motion presets (@ 24 FPS, dimensions divisible by 32):
    - **720p HD 16:9**: `1280 × 704`, 81 frames (~3.4s @ 24 FPS) or 121 frames (~5.0s @ 24 FPS).
    - **720p HD 9:16**: `704 × 1280`, 81 frames (~3.4s @ 24 FPS).
    - **480p Fast 16:9**: `832 × 480`, 81 frames (~3.4s @ 24 FPS).
    - **480p Fast 9:16**: `480 × 832`, 81 frames (~3.4s @ 24 FPS).
    - **1:1 Square**: `640 × 640`, 81 frames (~3.4s @ 24 FPS).
    - **Quick Draft**: `832 × 480`, 33 frames (~1.4s @ 24 FPS).
- **Interactive Video Studio**:
  - Real-time denoising progress over WebSockets (step counter, speed metrics, ETA, and live dual-GPU VRAM monitors).
  - Integrated HTML5 hero video player with autoplay, looping, direct MP4 export, and one-click video deletion.
  - Automatic thumbnail generation and JSON metadata sidecars.
  - "Reuse Settings" to instantly restore prompt, seed, dimensions, and CFG into the controls.
  - Slide-over Gallery drawer with recent clips, quick playback, and one-click deletion.

---

## Quick Start

### Option A: Docker (Recommended)

#### 1. Build the Docker Image

```bat
build.bat
```

Or using PowerShell:

```powershell
.\build.ps1
```

#### 2. Start the Container

Start the containerized studio with NVIDIA GPU acceleration:

```bat
start.bat
```

Or using PowerShell:

```powershell
.\start.ps1
```

To stop the container:

```bat
stop.bat
```

Or using PowerShell:

```powershell
.\stop.ps1
```

The container automatically mounts:
- `./models:/app/models` to persist model weights across container rebuilds.
- `./outputs:/app/outputs` to persist generated MP4 clips and sidecar JSON files.
- All host GPUs via the NVIDIA Container Toolkit.

---

### Option B: Local Python Web Server

On Windows, run:

```powershell
.\run.ps1
```

Or using batch:

```bat
run.bat
```

Or directly with Python:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8202 --reload
```

Open your browser to: **http://localhost:8202**

---

## Command-Line Interface (CLI)

The included `cli.py` allows diagnostics, model management, and headless video synthesis:

```powershell
# 1. Inspect hardware, PyTorch, CUDA, and model readiness
python cli.py doctor

# 2. Download Wan2.2-TI2V-5B model checkpoint (~31.9 GB download -> ~22.6 GB bfloat16)
python cli.py download

# 3. Convert any float32 shards to bfloat16 in-place
python cli.py convert-bf16

# 4. Generate a video from the command line
python cli.py generate --prompt "A red fox walking through fresh snow at sunset" --preset hd_16_9 --steps 40

# 5. Run an end-to-end smoke test
python cli.py smoke-test
```

---

## REST & WebSocket API

| Endpoint | Method | Description |
|---|---|---|
| `/api/status` | `GET` | System health, GPU telemetry, and model status |
| `/api/presets` | `GET` | List aspect ratios and resolution presets |
| `/api/generate` | `POST` | Queue a new video generation task (T2V or I2V) |
| `/api/jobs/{id}` | `GET` | Query generation job status |
| `/api/gallery` | `GET` | List generated video clips and metadata |
| `/api/gallery/{file}` | `DELETE`| Remove video, thumbnail, and metadata |
| `/api/model/download` | `POST`| Start background download of Wan2.2-TI2V-5B weights |
| `/ws/generation` | `WS` | Live WebSocket progress, ETA, and GPU metrics |

---

## License & Attribution

- **Author**: François Guillemette
- **Design System**: CrazyLogix Shared Brand System (`brand/tokens.css`)
- **Base Model**: Alibaba [Wan2.2-TI2V-5B](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B-Diffusers)
