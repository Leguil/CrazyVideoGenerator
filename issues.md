<!-- Author: François Guillemette -->
# CrazyVideoGenerator — Codebase Analysis & Issues Report

**Author:** François Guillemette  
**Date:** 2026-11-06  
**Project:** CrazyLogix CrazyVideoGenerator (`Wan2.1-T2V-1.3B-Diffusers`)

---

## Executive Summary

A static and architectural analysis of the **CrazyVideoGenerator** codebase (`app/`, `cli.py`, `brand/`, Docker configuration, and launch scripts) identified **22 issues** across 5 categories:

- **Critical (3):** Blockers affecting dual-GPU execution, RTX 50-series CUDA compatibility, and interrupted model download resumption.
- **High (6):** Frontend XSS vulnerabilities, broken light-theme styling due to mismatched `--cl-*` design tokens, missing API/CLI dimension & frame-count validation, and multi-client state desynchronization.
- **Medium (8):** Backend telemetry bugs, memory leaks in job tracking, blocking subprocess calls in inference callbacks, and incomplete UI controls.
- **Low (5):** Script parameter bugs, CSS comment syntax, hardcoded UI strings, and documentation formatting errors.

---

## 1. Critical Issues

### ISSUE-01: Cross-GPU Tensor Device Mismatch in `WanDualGpuPipeline`
- **Location:** [`app/pipeline.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/pipeline.py#L126-L165)
- **Problem:**  
  In `WanDualGpuPipeline.load_model()`, submodules are manually moved across GPUs without registering `accelerate` execution hooks or overriding tensor device transfers:
  ```python
  pipe.transformer.to(self.transformer_device)    # cuda:1
  pipe.text_encoder.to(self.text_encoder_device)  # cuda:0
  pipe.vae.to(self.vae_device)                    # cuda:0
  ```
  Meanwhile, `generate_video()` creates the random number generator on `self.transformer_device` (`cuda:1`):
  ```python
  generator = torch.Generator(device=self.transformer_device).manual_seed(seed)
  ```
  Inside Hugging Face `diffusers.WanPipeline.__call__()`:
  1. `self._execution_device` resolves to `cuda:0` (via `text_encoder`).
  2. `prepare_latents()` attempts to sample initial Gaussian noise on `device=cuda:0` using `generator` on `cuda:1`, raising `RuntimeError: Expected a 'cuda:0' generator device, but found 'cuda:1'`.
  3. Even if `generator` is placed on `cuda:0`, `prompt_embeds` (`cuda:0`) and `latents` (`cuda:0`) are passed directly into `self.transformer` (`cuda:1`), raising `RuntimeError: Expected all tensors to be on the same device, but found at least two devices, cuda:1 and cuda:0!`.
  4. After denoising on `cuda:1`, output latents on `cuda:1` are passed to `self.vae.decode()` on `cuda:0`, causing another cross-device `RuntimeError`.
- **Recommendation:**  
  Transfer `prompt_embeds` and `latents` explicitly or wrap `pipe.transformer` and `pipe.vae` forward passes (or use `accelerate.hooks.AlignDevicesHook` / custom pre-forward hooks on `pipe.transformer` and `pipe.vae`) so input tensors are automatically moved to the target submodule's device (`cuda:1` for `transformer`, `cuda:0` for `vae`).

---

### ISSUE-02: `cleanup_orphaned_download_files()` Deletes Resumable `.incomplete` Shards
- **Location:** [`app/system_info.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/system_info.py#L117-L139), [`app/engine.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/engine.py#L204), [`cli.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/cli.py#L97)
- **Problem:**  
  Both `EngineManager._run_download()` and `cli.py:cmd_download()` call `cleanup_orphaned_download_files(MODEL_DIR)` immediately before `snapshot_download()`. That function deletes all `*.incomplete` files inside `.cache/huggingface/download/`:
  ```python
  for f in list(cache_dir.rglob("*.incomplete")):
      f.unlink(missing_ok=True)
  ```
  `huggingface_hub.snapshot_download()` uses `.incomplete` files to **resume** interrupted downloads via HTTP `Range` requests. Deleting them forces multi-gigabyte shards (such as `text_encoder` and `transformer` shards currently partially downloaded in `./models/Wan2.1-T2V-1.3B-Diffusers/.cache/`) to restart from 0%, contradicting the UI's `"Resume Download"` action.
- **Recommendation:**  
  Only remove stale `*.lock` files prior to calling `snapshot_download()`. Keep `*.incomplete` files so `huggingface_hub` can resume partial shard downloads, and provide a separate explicit action if a full cache wipe is desired.

---

### ISSUE-03: Default `CUDA_WHL=cu124` Does Not Support RTX 5070 Ti (Blackwell `sm_120`)
- **Location:** [`Dockerfile`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/Dockerfile#L23), [`build.ps1`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/build.ps1#L8), [`build.bat`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/build.bat#L34), [`requirements.txt`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/requirements.txt#L5)
- **Problem:**  
  The project is designed for dual **NVIDIA GeForce RTX 5070 Ti** GPUs (Blackwell architecture, compute capability `sm_120`), but `Dockerfile`, `build.ps1`, and `build.bat` default to `CUDA_WHL=cu124`. PyTorch builds for CUDA 12.4 do not include `sm_120` kernels and fail at runtime on RTX 50-series cards with `CUDA error: no kernel image is available for execution on the device`.
- **Recommendation:**  
  Update the default `CUDA_WHL` argument in `Dockerfile`, `build.ps1`, `build.bat`, and `requirements.txt` comments to `cu128` (CUDA 12.8, which provides native `sm_120` Blackwell support).

---

## 2. High-Severity Issues

### ISSUE-04: Cross-Site Scripting (XSS) via Unescaped `innerHTML` in Frontend
- **Location:** [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L135), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L678-L720), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L753-L774)
- **Problem:**  
  User-controlled prompts, error messages, and metadata fields are interpolated directly into `innerHTML` without sanitization or HTML entity escaping:
  - `renderGallery()` injects `meta.prompt`, `item.video_file`, and `item.thumbnail_url` directly into `.gallery-card` HTML.
  - `showToast()` injects `message` into `toast.innerHTML`.
  - `renderDiagnostics()` injects GPU names and `missing_components` into `innerHTML`.
  A prompt containing HTML/JS payloads (e.g., `<img src=x onerror=alert(1)>`) will execute arbitrary JavaScript whenever the gallery is rendered.
- **Recommendation:**  
  Introduce an `escapeHtml()` helper or construct DOM nodes using `document.createElement()` and `.textContent` instead of `innerHTML`.

---

### ISSUE-05: Broken Light Theme Due to Non-Existent `--cl-*` Token Names in `app.css` & `app.js`
- **Location:** [`app/static/css/app.css`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/css/app.css#L17-L960), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L170-L177), [`brand/tokens.css`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/brand/tokens.css#L61-L320)
- **Problem:**  
  `app.css` imports `/brand/tokens.css` and attempts to use `--cl-*` custom properties, but references several variable names that **do not exist** in `brand/tokens.css`, causing hard-coded dark-theme fallback hex values to be used even when the user switches to Light Theme:
  1. `var(--cl-ground, #0f172a)` is used 13 times in `app.css`, but `tokens.css` defines `--cl-surface` and `--cl-panel-sunken` (not `--cl-ground`).
  2. `var(--cl-text-muted, #94a3b8)` is used 16 times in `app.css`, but `tokens.css` defines `--cl-muted` and `--cl-chrome-muted` (not `--cl-text-muted`).
  3. `var(--cl-accent-ink, #022c22)` is used in `app.css` (lines 183, 951) and `app.js` (lines 171, 176), but `tokens.css` defines `--cl-accent-text`. In Light Theme, `--cl-accent` is `#0e6b3f` (dark forest green), so falling back to `#022c22` renders dark text on a dark green button (violating the 4.5:1 contrast floor in `brand/CLAUDE.md`).
  4. `var(--cl-accent-lift, #34d399)` is used in `app.css` (lines 188, 956), whereas `tokens.css` defines `--cl-accent-hover`.
  5. `var(--cl-chrome, #1e293b)` is applied to `.sidebar-panel`, `.btn-secondary`, `.chip`, `.progress-box`, `.video-meta-bar`, `.gallery-drawer`, `.modal-card`, and `.toast`. Per `brand/tokens.css`, `--cl-chrome` (`#0f172a`) is always near-black in both themes and reserved strictly for the top application bar, while panels/modals/drawers must use `--cl-panel` (`#ffffff` in light, `#1e293b` in dark). Conversely, `.action-bar` and `.telemetry-pill` use `var(--cl-panel, #0b1329)` with white text, turning white-on-white in Light Theme.
- **Recommendation:**  
  Map all CSS variables in `app.css` and `app.js` to the canonical token names in `brand/tokens.css` (`--cl-surface`, `--cl-panel`, `--cl-panel-sunken`, `--cl-muted`, `--cl-accent-text`, `--cl-accent-hover`, `--cl-chrome-border`).

---

### ISSUE-06: Missing Validation for `num_frames` ($4k + 1$) and `width`/`height` Multiples of 16
- **Location:** [`app/main.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/main.py#L88-L99), [`cli.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/cli.py#L208-L210)
- **Problem:**  
  The Wan2.1 3D Causal VAE and patchifying transformer require:
  - `num_frames` to satisfy $(num\_frames - 1) \pmod 4 == 0$ (e.g., `VALID_FRAME_COUNTS = [17, 33, 49, 65, 81]`).
  - `width` and `height` to be divisible by 16.
  `GenerateRequest` in `app/main.py` only checks `256 <= width, height <= 1280` and places no bounds or validator on `num_frames` (not even `ge=1`). Passing an invalid frame count (e.g., `30` or `-5`) or non-divisible resolution via REST API or CLI causes a tensor shape mismatch crash during inference after loading the pipeline.
- **Recommendation:**  
  Add Pydantic `@field_validator` checks on `GenerateRequest` (and argument checks in `cli.py`) verifying `width % 16 == 0`, `height % 16 == 0`, and `num_frames in VALID_FRAME_COUNTS` (or `num_frames >= 17 and (num_frames - 1) % 4 == 0`).

---

### ISSUE-07: Active Job State Lost on Browser Refresh & Multi-Client WebSocket Collisions
- **Location:** [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L471-L558), [`app/engine.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/engine.py#L275-L338)
- **Problem:**  
  1. When a browser tab refreshes or connects while a generation job is already running on the server, the server includes `active_job` in the `telemetry` WebSocket payload (`app/engine.py:275`) and `/api/jobs` response, but `app.js` ignores `msg.active_job`. Because `state.isGenerating` defaults to `false`, `onJobProgress()` exits immediately at `if (!state.isGenerating) return;` (`app.js:472`), leaving the UI in the idle placeholder state until `job_completed` fires.
  2. `EngineManager` broadcasts `job_started` (`app/engine.py:287`), which `app.js` never handles.
  3. `app.js` does not filter `job_progress`, `job_completed`, or `job_failed` events by `job_id`, nor does it handle queued jobs when multiple requests are submitted.
- **Recommendation:**  
  In `app.js`, inspect `msg.active_job` upon receiving `telemetry` and handle `job_started` messages to restore the progress overlay and set `state.isGenerating = true` and `state.activeJobId = job.job_id`.

---

### ISSUE-08: `torch_cuda_available` Hardcoded to `False` in `get_system_status()`
- **Location:** [`app/system_info.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/system_info.py#L373)
- **Problem:**  
  `get_system_status()` returns `"torch_cuda_available": False` as a hardcoded literal at line 373 instead of querying PyTorch or checking `len(gpus) > 0`. Any consumer of `/api/status` checking `torch_cuda_available` will always see `False`.
- **Recommendation:**  
  Check `torch.cuda.is_available()` (with a safe `try/except ImportError`) or cache the boolean at module initialization.

---

### ISSUE-09: `CRAZY_VIDEO_DEVICES` (`DEFAULT_DEVICES`) Environment Variable Is Ignored
- **Location:** [`app/config.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/config.py#L30), [`app/pipeline.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/pipeline.py#L52-L86), [`docker-compose.yml`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/docker-compose.yml#L17)
- **Problem:**  
  `docker-compose.yml` sets `CRAZY_VIDEO_DEVICES=cuda:1,cuda:0`, `app/config.py` reads it into `DEFAULT_DEVICES`, and `WanDualGpuPipeline.__init__()` stores it in `self.devices_str`. However, `_configure_devices()` never parses `self.devices_str` and instead hardcodes `"cuda:1"` and `"cuda:0"`. Users cannot customize GPU assignment (e.g., `cuda:0,cuda:1` or single-GPU override on a dual-GPU host) via `CRAZY_VIDEO_DEVICES`.
- **Recommendation:**  
  Parse `self.devices_str` (e.g., `[d.strip() for d in self.devices_str.split(",") if d.strip()]`) in `_configure_devices()` and validate the specified device indices against `torch.cuda.device_count()`.

---

## 3. Medium-Severity Issues

### ISSUE-10: Redundant Triplicate Telemetry Polling Between Client and Server
- **Location:** [`app/engine.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/engine.py#L247-L279), [`app/main.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/main.py#L298-L316), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L534-L538), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L945)
- **Problem:**  
  Telemetry is fetched and transmitted via three overlapping mechanisms simultaneously:
  1. Server `_telemetry_loop()` broadcasts full status every **2.5s** (`app/engine.py:251`).
  2. Client WebSocket `heartbeatTimer` sends `"ping"` every **2.5s** (`app.js:534`), and the server responds to every `"ping"` by running `get_system_status()` and sending a full telemetry payload (`app/main.py:299-316`).
  3. Client `statusPollTimer` polls `GET /api/status` via HTTP every **8.0s** (`app.js:945`).
  This doubles WebSocket traffic for every connected client and triggers redundant `os.walk()` and `nvidia-smi` calls whenever the 1.5s–2.0s cache TTL expires.
- **Recommendation:**  
  Keep `_telemetry_loop()` on the server as the single push mechanism when WebSockets are connected, make WebSocket `"ping"` return a lightweight `{"type": "pong"}` heartbeat, and only run the HTTP `statusPollTimer` fallback when `state.socket.readyState !== WebSocket.OPEN`.

---

### ISSUE-11: Synchronous `get_gpu_info()` Subprocess Call Inside Inference Step Callback
- **Location:** [`app/engine.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/engine.py#L292-L309)
- **Problem:**  
  Inside `on_progress()`, which executes synchronously on the PyTorch denoising thread at the end of every diffusion step, `get_gpu_info()` is called directly on line 306. Whenever the 1.5s cache expires, `get_gpu_info()` spawns a blocking `nvidia-smi` subprocess inside the inference thread, stalling the next denoising step.
- **Recommendation:**  
  Remove `"gpus": get_gpu_info()` from the synchronous `on_progress` callback (since `_telemetry_loop` already broadcasts GPU metrics every 2.5s asynchronously), or read `_cached_gpu_info` without spawning `nvidia-smi`.

---

### ISSUE-12: Unbounded In-Memory `EngineManager.jobs` Dictionary
- **Location:** [`app/engine.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/engine.py#L122), [`app/engine.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/engine.py#L180)
- **Problem:**  
  `self.jobs: Dict[str, GenerationJob] = {}` stores every submitted job in memory indefinitely without eviction or a maximum history cap. Over long server uptimes, this dictionary grows without bound.
- **Recommendation:**  
  Use a bounded `collections.deque` or evict oldest completed/failed jobs once `len(self.jobs)` exceeds a configurable limit (e.g., 100 jobs).

---

### ISSUE-13: Missing Video Delete Control in Gallery UI & Ambiguous `DELETE` Response
- **Location:** [`app/main.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/main.py#L232-L247), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L747-L801)
- **Problem:**  
  - The backend exposes `DELETE /api/gallery/{filename}`, but the frontend gallery drawer (`renderGallery()`) and video player toolbar have no delete button to invoke it.
  - In `api_delete_video()`, if the requested file does not exist, it returns `200 OK` with `{"deleted": []}` instead of raising a `404 Not Found` `HTTPException`.
- **Recommendation:**  
  Add a delete button on gallery cards (and/or the hero player toolbar) with a confirmation dialog calling `DELETE /api/gallery/{filename}`, and return `404` when no matching files exist.

---

### ISSUE-14: Preset Override Condition in `api_generate` & `cli.py` Ignores Custom Dimensions
- **Location:** [`app/main.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/main.py#L160-L166), [`cli.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/cli.py#L129-L135)
- **Problem:**  
  - In `cli.py:129-135`, `--preset` defaults to `"landscape_16_9"`. Consequently, `if args.preset and args.preset in PRESETS:` is **always true**, unconditionally overwriting any custom `-w/--width`, `-H/--height`, or `-f/--frames` flags passed by the CLI user!
  - In `app/main.py:163`, if a user selects `draft_16_9` (which also has `width=832, height=480`) and customizes `num_frames` to `49`, the check `if req.width == 832 and req.height == 480 and req.preset != "landscape_16_9":` overwrites `num_frames` back to `p["default_frames"]` (`33`).
- **Recommendation:**  
  In `cli.py`, set `--preset` default to `None` so explicit `--width`, `--height`, and `--frames` arguments are respected unless `--preset` is explicitly provided. In `app/main.py`, only apply preset defaults when `req.width`, `req.height`, or `req.num_frames` are `None`.

---

### ISSUE-15: Falsy Value Handling for `seed = 0`, `fps`, and `negative_prompt` on Reuse/Reset
- **Location:** [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L308-L319), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L799), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L904-L929)
- **Problem:**  
  1. In `loadVideoIntoHero()` (`app.js:799`), `Seed: ${meta.seed || "N/A"}` evaluates `0 || "N/A"` to `"N/A"` when `seed` is `0`. Use `meta.seed ?? "N/A"`.
  2. In `btnReuseParams` (`app.js:904-929`), `m.fps` is never restored to `el.inputFps.value`, and `state.currentPreset` / `.preset-card.active` is not updated to match the restored dimensions.
  3. In `btnReset` (`app.js:308-319`), `el.negPromptInput.value` is not reset to `default_negative_prompt`.
- **Recommendation:**  
  Use nullish coalescing (`??`) for numeric metadata fields, restore `m.fps` in `btnReuseParams`, and reset `el.negPromptInput` in `btnReset`.

---

### ISSUE-16: Invalid CORS Configuration (`allow_origins=["*"]` with `allow_credentials=True`)
- **Location:** [`app/main.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/main.py#L63-L69)
- **Problem:**  
  `CORSMiddleware` is configured with both `allow_origins=["*"]` and `allow_credentials=True`. Per the Fetch/CORS specification, browsers block responses that combine a wildcard origin `*` with `Access-Control-Allow-Credentials: true`.
- **Recommendation:**  
  Set `allow_credentials=False` (since the application does not use cookies/auth headers) or configure explicit allowed origins via an environment variable.

---

### ISSUE-17: Missing `ftfy` Package in `requirements.txt`
- **Location:** [`requirements.txt`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/requirements.txt)
- **Problem:**  
  `diffusers`'s `WanPipeline` imports `ftfy` (`ftfy.fix_text`) during prompt preprocessing (`prompt_clean`). Without `ftfy` installed in the environment or Docker image, `diffusers` either raises an `ImportError` or logs degraded text-cleaning warnings.
- **Recommendation:**  
  Add `ftfy>=6.1.0` to `requirements.txt`.

---

## 4. Low-Severity & Polish Issues

### ISSUE-18: Unclosed CSS Block Comment on Line 1 of `app/static/css/app.css`
- **Location:** [`app/static/css/app.css`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/css/app.css#L1-L2)
- **Problem:**  
  Line 1 starts with `/* Author: François Guillemette` without a closing `*/`, relying on the end of line 2 (`/* CrazyVideoGenerator — CrazyLogix Video Studio Stylesheet */`) to close the comment block.
- **Recommendation:**  
  Close the comment on line 1: `/* Author: François Guillemette */`.

---

### ISSUE-19: Dead / Unpopulated UI Elements (`#liveGpuStrip`, `#hwTransformerDev`, `#hwAuxDev`)
- **Location:** [`app/static/index.html`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/index.html#L215-L219), [`app/static/index.html`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/index.html#L261), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L840)
- **Problem:**  
  - `#liveGpuStrip` (`<div class="gpu-live-strip" id="liveGpuStrip">`) inside the generation progress overlay has a comment `<!-- GPU load bars populated via websocket -->`, but is never populated in `app.js` or styled in `app.css`.
  - `#hwTransformerDev` and `#hwAuxDev` in the sidebar Hardware Orchestration Card are static strings (`GPU 1 (cuda:1)` and `GPU 0 (cuda:0)`) and are never updated from `status.recommended_device_mapping` on single-GPU or CPU systems.
  - `app.js:840` hardcodes `"Hardware: Dual RTX 5070 Ti (GPU1 compute + GPU0 auxiliary)"` in the download confirmation dialog regardless of the actual detected GPUs.
- **Recommendation:**  
  Populate `#liveGpuStrip`, `#hwTransformerDev`, and `#hwAuxDev` dynamically from telemetry data, and use detected GPU names in the download modal.

---

### ISSUE-20: Inconsistent Expected Model Size Constants Across Codebase
- **Location:** [`app/config.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/config.py#L120), [`app/system_info.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/system_info.py#L154), [`app/system_info.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/system_info.py#L279), [`app/static/index.html`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/index.html#L334), [`README.md`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/README.md#L143)
- **Problem:**  
  The expected size of `Wan2.1-T2V-1.3B-Diffusers` is defined inconsistently across files:
  - `app/config.py:120`: `"total_expected_gib": 12.5`
  - `app/system_info.py:154`: `expected_total_gib = 13.5`
  - `app/system_info.py:279`: `clean_gib >= 11.0`
  - `app/static/index.html:334` & `README.md:143`: `~12 GB`
  - `app/static/js/app.js:379,635`: `~13.5 GB`
- **Recommendation:**  
  Reference `MODEL_PROFILES["wan21_13b"]["total_expected_gib"]` from `app/config.py` as the single source of truth across backend and frontend status payloads.

---

### ISSUE-21: `build.ps1` and `build.bat` Ignore Custom Image Tag Parameter
- **Location:** [`build.ps1`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/build.ps1#L9-L72), [`build.bat`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/build.bat#L35-L74)
- **Problem:**  
  `build.ps1` accepts a `-Tag` parameter (`[string]$Tag = "crazylogix/crazy-video-generator:latest"`), displays `Target Image : $Tag`, and runs `docker images $Tag` after building, but runs `docker compose build` without passing `$Tag`, so custom `-Tag` values have no effect on the built image tag.
- **Recommendation:**  
  Either tag the built image with `docker tag crazylogix/crazy-video-generator:latest $Tag` when a custom `-Tag` is provided, or pass it via environment variable into `docker-compose.yml`.

---

### ISSUE-22: Malformed Markdown Code Fences in `README.md`
- **Location:** [`README.md`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/README.md#L68-L76)
- **Problem:**  
  Lines 68–76 of `README.md` contain corrupted single-backtick code blocks (` ` at ` and `` `powershell ``) instead of triple-backtick fenced blocks (` ```bat ` and ` ```powershell `), breaking Markdown rendering of the Quick Start section.
- **Recommendation:**  
  Replace the broken fences on lines 68–76 with standard triple-backtick code fences.

---

## Summary Table

| ID | Severity | Status | Component | Title |
|---|---|---|---|---|
| **ISSUE-01** | 🔴 Critical | ✅ Resolved | `app/pipeline.py` | Cross-GPU tensor device mismatch (`cuda:0` vs `cuda:1`) in `WanDualGpuPipeline` |
| **ISSUE-02** | 🔴 Critical | ✅ Resolved | `app/system_info.py` | `cleanup_orphaned_download_files()` deletes resumable `.incomplete` shards |
| **ISSUE-03** | 🔴 Critical | ✅ Resolved | `Dockerfile` / `build.*` | Default `CUDA_WHL=cu124` lacks RTX 5070 Ti (`sm_120` Blackwell) kernel support |
| **ISSUE-04** | 🟠 High | ✅ Resolved | `app/static/js/app.js` | XSS via unescaped `innerHTML` in gallery, toasts, and diagnostics |
| **ISSUE-05** | 🟠 High | ✅ Resolved | `app/static/css/app.css` | Non-existent `--cl-*` token names break Light Theme and contrast floors |
| **ISSUE-06** | 🟠 High | ✅ Resolved | `app/main.py` / `cli.py` | Missing validation for `num_frames` ($4k+1$) and `width`/`height` ($\div 16$) |
| **ISSUE-07** | 🟠 High | ✅ Resolved | `app/static/js/app.js` | Active job state lost on browser refresh & unhandled `job_started` event |
| **ISSUE-08** | 🟠 High | ✅ Resolved | `app/system_info.py` | `torch_cuda_available` hardcoded to `False` in `/api/status` |
| **ISSUE-09** | 🟠 High | ✅ Resolved | `app/pipeline.py` | `CRAZY_VIDEO_DEVICES` (`DEFAULT_DEVICES`) environment variable is ignored |
| **ISSUE-10** | 🟡 Medium | ✅ Resolved | `app/engine.py` / `app.js` | Redundant triplicate telemetry polling (WS loop + WS ping + HTTP poll) |
| **ISSUE-11** | 🟡 Medium | ✅ Resolved | `app/engine.py` | Blocking `get_gpu_info()` (`nvidia-smi`) called inside denoising step callback |
| **ISSUE-12** | 🟡 Medium | ✅ Resolved | `app/engine.py` | Unbounded in-memory `EngineManager.jobs` dictionary |
| **ISSUE-13** | 🟡 Medium | ✅ Resolved | `app/main.py` / `app.js` | Missing delete button in Gallery UI & `200 OK` on non-existent file deletion |
| **ISSUE-14** | 🟡 Medium | ✅ Resolved | `cli.py` / `app/main.py` | `--preset` default in `cli.py` overwrites custom `--width`/`--height`/`--frames` |
| **ISSUE-15** | 🟡 Medium | ✅ Resolved | `app/static/js/app.js` | Falsy bug on `seed = 0`, missing `fps` on reuse, and `negPrompt` on reset |
| **ISSUE-16** | 🟡 Medium | ✅ Resolved | `app/main.py` | Invalid CORS combination (`allow_origins=["*"]` with `allow_credentials=True`) |
| **ISSUE-17** | 🟡 Medium | ✅ Resolved | `requirements.txt` | Missing `ftfy` dependency used by `diffusers.WanPipeline` |
| **ISSUE-18** | 🔵 Low | ✅ Resolved | `app/static/css/app.css` | Unclosed CSS comment on line 1 |
| **ISSUE-19** | 🔵 Low | ✅ Resolved | `index.html` / `app.js` | Unpopulated `#liveGpuStrip`, static hardware badges, and hardcoded GPU name |
| **ISSUE-20** | 🔵 Low | ✅ Resolved | `config.py` / `system_info.py` | Inconsistent expected model size constants (`11.0`, `12.0`, `12.5`, `13.5` GiB) |
| **ISSUE-21** | 🔵 Low | ✅ Resolved | `build.ps1` / `build.bat` | `$Tag` / `%TAG%` parameter is not applied to the built Docker image |
| **ISSUE-22** | 🔵 Low | ✅ Resolved | `README.md` | Corrupted Markdown code fences in Quick Start section |
