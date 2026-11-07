# Author: François Guillemette
# CrazyVideoGenerator — Code Analysis & Issues Report (`issues3.md`)

**Date:** 2026-11-07  
**Scope:** Full-stack codebase audit following the inline Synthesis Inspector / Generated Outputs UI migration and community Wan2.2-TI2V-5B LoRA adapter integration.

---

## Summary Table

| ID | Severity | Component | Title | Status |
| :--- | :--- | :--- | :--- | :--- |
| **ISS3-01** | 🔴 Critical | `app/pipeline.py` | `_apply_lora()` loads LoRA onto CPU/cuda:0 instead of keeping transformer weights on designated GPU 1 | ✅ Resolved |
| **ISS3-02** | 🟠 High | `app/pipeline.py` | LoRA weights loaded on `self.pipeline` are not registered into companion `self.i2v_pipeline` | ✅ Resolved |
| **ISS3-03** | 🟠 High | `app/static/js/app.js` | Custom LoRA modal download button (`#btnDownloadCustomLora`) lacks input validation and sanitization | ✅ Resolved |
| **ISS3-04** | 🟡 Medium | `cli.py` | `cli.py generate` command lacks `--lora` and `--lora-scale` arguments | ✅ Resolved |
| **ISS3-05** | 🟡 Medium | `app/static/js/app.js` | `loadVideoIntoHero()` fails to update active state of the `#selectLora` dropdown and scale slider | ✅ Resolved |
| **ISS3-06** | 🟡 Medium | `app/main.py` | Synchronous filesystem iteration in `GET /api/loras` blocks the event loop on slow storage | ✅ Resolved |
| **ISS3-07** | 🟢 Low | `app/static/index.html` | Modal backdrop overlay for `#loraModal` lacks keyboard escape handler and outer click dismiss | ✅ Resolved |
| **ISS3-08** | 🟢 Low | `app/config.py` | Curated LoRA URLs lack direct Civitai / Hugging Face model documentation links in UI | ✅ Resolved |

---

## Detailed Findings

### ISS3-01 (🔴 Critical): `_apply_lora()` Loads LoRA Onto Default Device Instead of Keeping Transformer on GPU 1
- **Location:** [`app/pipeline.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/pipeline.py#L418-L435)
- **Description:**
  When `self.pipeline.load_lora_weights()` is invoked, PEFT instantiates adapter linear layers on the default PyTorch device (`cuda:0` or `cpu`) rather than `self.transformer_device` (`cuda:1`). While `self.pipeline.transformer.to(device=self.transformer_device)` is called afterwards, in a multi-GPU environment where `transformer` is on `cuda:1` and `text_encoder`/`vae` are on `cuda:0`, PEFT hooks or adapter layers loaded without explicit device mapping can lead to:
  `RuntimeError: Expected all tensors to be on the same device, but found at least two devices, cuda:0 and cuda:1!`.
- **Recommendation:**
  Explicitly pass device mapping or run `self.pipeline.transformer.to(self.transformer_device)` and verify all newly registered adapter modules in `transformer` reside on `self.transformer_device`.

---

### ISS3-02 (🟠 High): LoRA Weights Loaded on `self.pipeline` Are Not Mirrored to `self.i2v_pipeline`
- **Location:** [`app/pipeline.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/pipeline.py#L425-L438)
- **Description:**
  `WanDualGpuPipeline` initializes both `self.pipeline` (for Text-to-Video) and `self.i2v_pipeline` (for native Image-to-Video). In `_apply_lora()`, `self.pipeline.load_lora_weights()` and `self.pipeline.set_adapters()` are called solely on `self.pipeline`. Although both pipelines share the same `transformer` instance, Diffusers pipelines maintain internal adapter tracking (`self._lora_loadable_modules`, `self._merged_adapters`, and `active_adapters`). When generating via `self.i2v_pipeline(**pipe_kwargs)`, diffusers may fail to forward the active adapter state during native I2V inference.
- **Recommendation:**
  Ensure adapter state is synchronized across both pipelines, or invoke `set_adapters` on both `self.pipeline` and `self.i2v_pipeline`.

---

### ISS3-03 (🟠 High): Custom LoRA Modal Download Lacks Rigorous Filename & Repo Sanitization
- **Location:** [`app/main.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/main.py#L201-L252), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L265-L295)
- **Description:**
  In `POST /api/loras/download`, if a user provides an arbitrary repo string or a filename with invalid characters or path traversal components, `hf_hub_download` can raise unhandled exceptions or attempt invalid file writes. Furthermore, if a large multi-gigabyte repo is requested, the endpoint blocks the worker thread without a download timeout.
- **Recommendation:**
  Validate that `repo_id` matches the standard Hugging Face format (`^[a-zA-Z0-9_\-\.]+\/[a-zA-Z0-9_\-\.]+$`), sanitize `filename` with `Path(filename).name`, and ensure it strictly ends with `.safetensors`.

---

### ISS3-04 (🟡 Medium): `cli.py generate` Lacks `--lora` and `--lora-scale` CLI Arguments
- **Location:** [`cli.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/cli.py#L227-L245)
- **Description:**
  The web UI now supports selecting any `.safetensors` LoRA and setting its scale. However, the command-line interface `python cli.py generate` does not expose `--lora` or `--lora-scale`, making it impossible to test or run LoRA inference headlessly or via automation scripts.
- **Recommendation:**
  Add `--lora` (default `None`) and `--lora-scale` (default `0.8`, `float`) arguments to `gen_parser` in [`cli.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/cli.py) and pass them to `pipe.generate_video()`.

---

### ISS3-05 (🟡 Medium): Clicking a Generated Video Tile Does Not Pre-Select Its LoRA in the UI
- **Location:** [`app/static/js/gallery.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/gallery.js#L140-L180)
- **Description:**
  When a user clicks on an item in the **Generated Outputs** strip, `loadVideoIntoHero()` populates the video player and the **Synthesis Inspector & Provenance** card. While the inspector correctly displays the LoRA badge (e.g., `+ LoRA: wan22_5b_anime_v01_lora.safetensors (0.8x)`), the active sidebar controls (`#selectLora` and `#inputLoraScale`) are only updated when the user explicitly clicks the `↺ Reuse` button, rather than providing an option to view or auto-sync the selected output's LoRA state.
- **Recommendation:**
  Keep the inspector and sidebar in clear harmony, and ensure `↺ Reuse` completely restores both the LoRA dropdown selection and the strength slider.

---

### ISS3-06 (🟡 Medium): Synchronous Filesystem Operations in `GET /api/loras`
- **Location:** [`app/main.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/main.py#L172-L198)
- **Description:**
  `api_loras()` executes synchronous `LORAS_DIR.glob("*.safetensors")` and `stat()` operations directly inside an `async def` endpoint. On network-attached storage or during heavy concurrent disk I/O, this can block the FastAPI event loop and delay telemetry WebSocket updates.
- **Recommendation:**
  Wrap the directory scan inside `await asyncio.to_thread(_scan_loras)`.

---

### ISS3-07 (🟢 Low): Modal Dialogs Lack Escape Key and Outside-Click Dismissal
- **Location:** [`app/static/index.html`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/index.html#L399-L455), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js)
- **Description:**
  The new `#loraModal` (and existing `#diagModal` and `#metaModal`) require clicking the `✕` close button or `Close` footer button. Pressing the `Escape` key or clicking on the darkened backdrop outside the card does not dismiss the modal, which is standard web UX.
- **Recommendation:**
  Add a global `keydown` listener for `Escape` and backdrop click listeners that close any open modal backdrop.

---

### ISS3-08 (🟢 Low): Curated LoRAs Lack Direct External Links in Manager Modal
- **Location:** [`app/config.py`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/config.py#L127-L162), [`app/static/js/app.js`](file:///d:/Work/CrazyLogix/CrazyVideoGenerator/app/static/js/app.js#L35-L60)
- **Description:**
  In the **🧩 Community LoRA Manager** modal, curated LoRAs display their name, description, and repo ID, but do not provide a clickable hyperlink to the Hugging Face model card for users to read prompt triggers, sample generations, or license details.
- **Recommendation:**
  Add an external link icon pointing to `https://huggingface.co/{repo_id}` for each curated LoRA card in the modal.
