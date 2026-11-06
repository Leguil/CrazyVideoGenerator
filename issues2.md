# Author: François Guillemette
# CrazyVideoGenerator — Code Analysis & Issues Report (`issues2.md`)

**Date:** 2026-11-06  
**Scope:** Full-stack analysis following the transition to **Wan2.2-TI2V-5B (`Wan-AI/Wan2.2-TI2V-5B-Diffusers`)**, Starting Image (I2V) conditioning, and Studio UI updates.

---

## Summary Table

| ID | Severity | Component | Title | Status |
| :--- | :--- | :--- | :--- | :--- |
| **ISS2-01** | 🔴 Critical | `app/pipeline.py` | Potential `cpu` vs `cuda:0` device mismatch in `_make_pre_hook` after `text_encoder` VRAM offload | ✅ Resolved |
| **ISS2-02** | 🟠 High | `app/pipeline.py` | `image_strength` slider has no effect when using native Wan2.2 `WanImageToVideoPipeline` | ✅ Resolved |
| **ISS2-03** | 🟠 High | `app/engine.py` / `app/main.py` | Base64 `init_image` retained in memory across job history (`MAX_JOBS_HISTORY = 100`) & lacks size validation | ✅ Resolved |
| **ISS2-04** | 🟡 Medium | `app/static/js/app.js` | `selectPreset()` does not update `inputSteps` / `valSteps` to the preset's `recommended_steps` | ✅ Resolved |
| **ISS2-05** | 🟡 Medium | `app/system_info.py` | `recommended_device_mapping` ignores runtime `text_encoder` CPU offload state | ✅ Resolved |
| **ISS2-06** | 🟡 Medium | `docker-compose.yml` | `cli.py` is not bind-mounted into the container, leaving container CLI out of sync with host edits | ✅ Resolved |
| **ISS2-07** | 🟡 Medium | `requirements.txt` | `diffusers>=0.33.0` minimum version is too old for `Wan2.2-TI2V-5B` (`>=0.35.0` required) | ✅ Resolved |
| **ISS2-08** | 🟢 Low | `app/pipeline.py` / `app/engine.py` | Function signature defaults and `cmd_smoke_test` still use legacy Wan2.1 values (`832x480`, `35` steps, `16` FPS) | ✅ Resolved |
| **ISS2-09** | 🟢 Low | `app/pipeline.py` | Duplicate `-pix_fmt yuv420p` flag in `imageio.mimwrite` triggers FFmpeg stream warning on every export | ✅ Resolved |
| **ISS2-10** | 🟢 Low | `app/static/*` / `README.md` | Stale `Wan2.1-T2V-1.3B` references, `832x480` fallbacks, and outdated documentation in `README.md` | ✅ Resolved |

---

## Detailed Findings

### ISS2-01 (🔴 Critical): Potential `cpu` vs `cuda:0` Device Mismatch in `_make_pre_hook` After `text_encoder` VRAM Offload
- **Location:** [`app/pipeline.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/pipeline.py#L165-L202)
- **Description:**
  During 720p VAE decoding (`_wrapped_decode`, lines 194–202), if `cuda:0` has less than `3.8 GiB` of free VRAM, `pipe.text_encoder` (`10.58 GiB`) is offloaded to `"cpu"` to prevent a `CUDA out of memory` error.
  On the next generation job, `_make_pre_hook` (lines 166–176) attempts `mod.to(dev)` (`"cuda:0"`), catching any OOM exception with `except Exception: pass`, and then unconditionally moves `args` and `kwargs` (`input_ids` and `attention_mask`) to `dev` (`"cuda:0"`):
  ```python
  try:
      p = next(mod.parameters(), None)
      if p is not None and str(p.device) != dev:
          mod.to(dev)
  except Exception:
      pass
  new_args = self._move_tensors_to_device(args, dev)
  new_kwargs = self._move_tensors_to_device(kwargs, dev)
  ```
  If `mod.to("cuda:0")` fails because `cuda:0` still has `< 11.2 GiB` free VRAM, `mod` remains on `"cpu"` while `new_args` are moved to `"cuda:0"`, raising `RuntimeError: Expected all tensors to be on the same device, but found at least two devices, cpu and cuda:0!`.
- **Recommendation:**
  Check available VRAM before moving `text_encoder` back to `cuda:0`, and always resolve `actual_dev = str(next(mod.parameters()).device)` after the `try` block so input tensors are moved to the module's actual device.

---

### ISS2-02 (🟠 High): `image_strength` Slider Has No Effect in Native Wan2.2 `WanImageToVideoPipeline`
- **Location:** [`app/pipeline.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/pipeline.py#L438-L541)
- **Description:**
  When `use_native_i2v` is `True` (the default path for `Wan2.2-TI2V-5B-Diffusers` since `expand_timesteps=True`), `generate_video()` delegates to `self.i2v_pipeline(image=pil_init_image, ...)`.
  However, `WanImageToVideoPipeline` does not take an `image_strength` parameter—it pins the first latent frame via `first_frame_mask[:, :, 0] = 0` across all timesteps regardless of what the user sets on the **Image Strength** slider (`#inputImageStrength`, `0.10`–`1.00`).
- **Recommendation:**
  Support `image_strength` in the native I2V path (e.g., by blending or releasing the conditioning constraint after `int(num_inference_steps * clamped_strength)` steps or blending initial latent conditioning according to `clamped_strength`).

---

### ISS2-03 (🟠 High): Base64 `init_image` Retained in Memory Across Job History & Lacks Input Validation
- **Location:** [`app/engine.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/engine.py#L48-L62), [`app/main.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/main.py#L99-L100)
- **Description:**
  1. `GenerationJob` stores `self.init_image` (a base64 data URL that can be 2–15 MB per image) and keeps up to `MAX_JOBS_HISTORY = 100` jobs in `engine_manager.jobs`. Even after a job finishes or fails, `self.init_image` is never cleared, retaining ratusan MB of base64 strings in RAM.
  2. `GenerateRequest.init_image` has no max-length or format validator in `app/main.py`, so invalid or oversized payloads are not rejected with `HTTP 422` at request time.
- **Recommendation:**
  Add a `@field_validator("init_image")` in `GenerateRequest` to validate base64 image headers/size (e.g. max 20 MB), store `self.has_init_image = bool(init_image)` on `GenerationJob`, and set `job.init_image = None` inside `_job_worker`'s `finally` block once inference completes.

---

### ISS2-04 (🟡 Medium): `selectPreset()` Does Not Sync `inputSteps` to `recommended_steps`
- **Location:** [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L293-L308)
- **Description:**
  Each preset in `app/config.py` specifies `"recommended_steps"` (`40` for 720p HD presets, `35` for 480p presets, `25` for `draft_16_9`). However, `selectPreset(presetId)` only updates `inputWidth`, `inputHeight`, and `selectFrames`. Selecting `draft_16_9` (or clicking **⚡ Smoke Test**) leaves `Steps` at `40` instead of `25`.
- **Recommendation:**
  In `selectPreset(presetId)`, also update `el.inputSteps.value` and `el.valSteps.textContent` when `p.recommended_steps` is defined.

---

### ISS2-05 (🟡 Medium): `recommended_device_mapping` Ignores Runtime `text_encoder` Placement
- **Location:** [`app/system_info.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/system_info.py#L444-L450)
- **Description:**
  `get_system_status()` statically reports `"text_encoder_device": "cuda:0"` whenever any GPU is present, even if `WanDualGpuPipeline` placed `text_encoder` on `"cpu"` because `cuda:0` had `< 11.2 GiB` of free VRAM.
- **Recommendation:**
  If `global_pipeline` in `app.pipeline` is initialized, report its actual `transformer_device`, `text_encoder_device`, and `vae_device` in `get_system_status()`.

---

### ISS2-06 (🟡 Medium): `cli.py` Is Not Bind-Mounted in `docker-compose.yml`
- **Location:** [`docker-compose.yml`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/docker-compose.yml#L20-L25)
- **Description:**
  `docker-compose.yml` bind-mounts `./app:/app/app`, `./brand:/app/brand:ro`, `./models:/app/models`, and `./outputs:/app/outputs`, but omits `./cli.py:/app/cli.py`. Host updates to `cli.py` require a full Docker image rebuild to take effect inside the container.
- **Recommendation:**
  Add `- ./cli.py:/app/cli.py` to `volumes` in `docker-compose.yml`.

---

### ISS2-07 (🟡 Medium): `requirements.txt` Minimum `diffusers` Version Too Low for Wan2.2
- **Location:** [`requirements.txt`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/requirements.txt#L16)
- **Description:**
  `requirements.txt` specifies `diffusers>=0.33.0`, but `Wan-AI/Wan2.2-TI2V-5B-Diffusers` (`model_index.json` `_diffusers_version: "0.35.0.dev0"`, `expand_timesteps=True`, and 48-channel `AutoencoderKLWan` with `scale_factor_spatial=16`) requires `diffusers>=0.35.0`.
- **Recommendation:**
  Update `requirements.txt` to `diffusers>=0.35.0`.

---

### ISS2-08 (🟢 Low): Legacy Wan2.1 Default Arguments in Pipeline, Engine, and CLI Smoke Test
- **Location:** [`app/pipeline.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/pipeline.py#L398-L412), [`app/engine.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/engine.py#L42-L48), [`cli.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/cli.py#L183-L192)
- **Description:**
  - `WanDualGpuPipeline.generate_video()`, `GenerationJob.__init__()`, and `EngineManager.submit_job()` still use default parameters `width=832, height=480, num_inference_steps=35, fps=16` instead of `1280, 704, DEFAULT_STEPS (40), DEFAULT_FPS (24)`.
  - `cli.py:cmd_smoke_test()` still passes `fps=16` instead of `DEFAULT_FPS` (`24`).
- **Recommendation:**
  Align all default argument values with `app/config.py` constants (`DEFAULT_STEPS`, `DEFAULT_FPS`, `DEFAULT_FRAMES`, `1280x704`).

---

### ISS2-09 (🟢 Low): Duplicate `-pix_fmt yuv420p` Option in `imageio.mimwrite`
- **Location:** [`app/pipeline.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/pipeline.py#L624-L630)
- **Description:**
  `imageio.mimwrite` passes `-pix_fmt yuv420p` by default via its `pixelformat` parameter. Also passing `"-pix_fmt", "yuv420p"` in `output_params` logs:
  `[vost#0:0/libx264] Multiple -pix_fmt options specified for stream 0, only the last option '-pix_fmt yuv420p' will be used.`
- **Recommendation:**
  Pass `pixelformat="yuv420p"` and `output_params=["-crf", "19", "-preset", "medium"]` in `_export_frames_to_mp4`.

---

### ISS2-10 (🟢 Low): Stale `Wan2.1` Strings & Outdated `README.md`
- **Location:** [`app/pipeline.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/pipeline.py#L2), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L892), [`app/static/index.html`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/index.html#L289-L310), [`README.md`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/README.md)
- **Description:**
  - `app/pipeline.py:2` module docstring still says `Wan2.1-T2V-1.3B`.
  - `app/static/js/app.js:892` (`renderDiagnostics`) falls back to `"Wan-AI/Wan2.1-T2V-1.3B-Diffusers"`.
  - `app/static/js/app.js:1018` (`loadVideoIntoHero`) and `app/static/index.html:289, 310` still have `832x480 • 81 Frames • 5.0s` and `Step: 0 / 35` placeholders.
  - `README.md` still documents `Wan2.1-T2V-1.3B`, `16 FPS`, `624x624` square preset, and lacks documentation for Starting Image (I2V) conditioning and `Wan2.2-TI2V-5B`.
- **Recommendation:**
  Update all remaining fallback strings and `README.md` to reflect `Wan2.2-TI2V-5B`, 720p/480p presets, 24 FPS, and Starting Image conditioning.
