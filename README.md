# Author: François Guillemette
# CrazyVideoGenerator — CrazyLogix Video Studio

**CrazyVideoGenerator** is a containerized, high-performance web studio for text-to-video synthesis using Alibaba's **Wan2.1-T2V-1.3B** model (`Wan-AI/Wan2.1-T2V-1.3B-Diffusers`). Engineered for dual-GPU workstations (such as dual NVIDIA GeForce RTX 5070 Ti 16 GB cards), it balances intensive 3D diffusion computation with zero-overhead memory partitioning.

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
  • UMT5-XXL Text Encoder                           • WanTransformer3DModel
  • Prompt Embeddings                               • 3D Video DiT Denoising
  • 3D Causal VAE Decoder                           • Active Timesteps Loop
  • MP4 / H.264 Video Exporter                      • 0 MB Windows Overhead
```

- **GPU 1 (`cuda:1`)**: Receives prompt embeddings and runs the intensive 3D Diffusion Transformer (`WanTransformer3DModel`) through all 30–50 denoising steps. Because GPU 1 has no OS display overhead, it operates with peak throughput and zero memory thrashing.
- **GPU 0 (`cuda:0`)**: Primary display card handling prompt encoding (`UMT5EncoderModel`), VAE temporal decoding (`AutoencoderKLWan`), web server request routing, and MP4 assembly.

---

## Features

- **CrazyLogix Brand Design System**:
  - Implements `brand/tokens.css` with standard `--cl-*` variables.
  - **Two-Tier Application Bar**:
    - **Tier 1 (Main Header)**: Brand lockup with `crazylogix_logo.svg`, live dual-GPU VRAM telemetry pills, model readiness badge, light/dark theme switcher, and diagnostics.
    - **Tier 2 (Action Bar)**: Immediate workflow triggers (*Generate Video*, *Random Seed*, *Reset*, *Download Model*, *Smoke Test*, *Output Gallery*).
  - Explicit dark theme selector (`:root[data-theme="dark"]`) synced to `localStorage["crazylogix_theme"]`.
- **Wan2.1-T2V-1.3B Native Support**:
  - Native Hugging Face `diffusers` `WanPipeline` integration.
  - Standard 480p motion presets:
    - **16:9 Landscape**: $832 \times 480$, 81 frames (~5.0s @ 16 FPS).
    - **9:16 Portrait**: $480 \times 832$, 81 frames (~5.0s @ 16 FPS).
    - **1:1 Square**: $624 \times 624$, 65 frames (~4.0s @ 16 FPS).
    - **4:3 Classic**: $704 \times 544$, 49 frames (~3.0s @ 16 FPS).
    - **Quick Draft**: $832 \times 480$, 33 frames (~2.0s @ 16 FPS).
- **Interactive Video Studio**:
  - Real-time denoising progress over WebSockets (step counter, speed metrics, ETA, and live dual-GPU VRAM monitors).
  - Integrated HTML5 hero video player with autoplay, looping, frame-stepping, and direct MP4 export.
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

# 2. Download Wan2.1 model checkpoint (~13.5 GB)
python cli.py download

# 3. Generate a video from the command line
python cli.py generate --prompt "A red fox walking through fresh snow at sunset" --preset landscape_16_9 --steps 35

# 4. Run an end-to-end smoke test
python cli.py smoke-test
```

---

## REST & WebSocket API

| Endpoint | Method | Description |
|---|---|---|
| `/api/status` | `GET` | System health, GPU telemetry, and model status |
| `/api/presets` | `GET` | List aspect ratios and resolution presets |
| `/api/generate` | `POST` | Queue a new video generation task |
| `/api/jobs/{id}` | `GET` | Query generation job status |
| `/api/gallery` | `GET` | List generated video clips and metadata |
| `/api/gallery/{file}` | `DELETE`| Remove video, thumbnail, and metadata |
| `/api/model/download` | `POST`| Start background download of Wan2.1 weights |
| `/ws/generation` | `WS` | Live WebSocket progress, ETA, and GPU metrics |

---

## License & Attribution

- **Author**: François Guillemette
- **Design System**: CrazyLogix Shared Brand System (`brand/tokens.css`)
- **Base Model**: Alibaba [Wan2.1-T2V-1.3B](https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B-Diffusers)
