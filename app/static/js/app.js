// Author: François Guillemette
/**
 * CrazyVideoGenerator — Main Studio Controller (Presets, Form Controls, & Generation Workflow)
 */

import { deleteVideoFile, loadGallery, loadVideoIntoHero } from "./gallery.js";
import { el, escapeHtml, normalizeModelStatus, state } from "./state.js";
import { checkSystemStatus, initWebSocket, renderDiagnostics } from "./telemetry.js";
import { closeAppDialog, initTheme, showAppDialog, showToast } from "./ui-dialogs.js";

// ----------------------------------------------------------------------- //
// Presets, LoRAs & Form Sync
// ----------------------------------------------------------------------- //
async function loadLoras(selectFilename = null) {
    try {
        const res = await fetch("/api/loras");
        const data = await res.json();
        state.loras = data.installed || [];
        state.recommendedLoras = data.recommended || [];

        if (el.selectLora) {
            const currentVal = selectFilename || el.selectLora.value || "none";
            el.selectLora.innerHTML =
                `<option value="none">None (Base Wan2.2-TI2V-5B)</option>` +
                state.loras
                    .map(
                        (l) =>
                            `<option value="${escapeHtml(l.filename)}">${escapeHtml(l.filename)} (${escapeHtml(l.size_mb)} MB)</option>`
                    )
                    .join("");
            if (state.loras.some((l) => l.filename === currentVal)) {
                el.selectLora.value = currentVal;
            } else {
                el.selectLora.value = "none";
            }
            if (el.loraScaleGroup) {
                el.loraScaleGroup.classList.toggle("hidden", el.selectLora.value === "none");
            }
        }
        renderRecommendedLoras();
    } catch (err) {
        console.error("Failed to load LoRAs:", err);
    }
}

function renderRecommendedLoras() {
    if (!el.recommendedLorasList) return;
    if (!state.recommendedLoras.length) {
        el.recommendedLorasList.innerHTML = `<div style="font-size:0.8rem;color:var(--cl-muted);">No curated LoRAs configured.</div>`;
        return;
    }
    el.recommendedLorasList.innerHTML = state.recommendedLoras
        .map(
            (r) => `
            <div style="display:flex;align-items:center;justify-content:space-between;gap:0.75rem;padding:0.6rem 0.75rem;border:1px solid var(--cl-border);border-radius:var(--radius-sm);background:rgba(0,0,0,0.2);">
                <div style="min-width:0;flex:1;">
                    <div style="font-size:0.82rem;font-weight:700;color:var(--cl-text);">${escapeHtml(r.name)}</div>
                    <div style="font-size:0.72rem;color:var(--cl-muted);">${escapeHtml(r.description)}</div>
                    <div style="font-size:0.68rem;color:var(--cl-accent);font-family:var(--font-mono);margin-top:0.15rem;">${escapeHtml(r.repo_id)}</div>
                </div>
                <div>
                    ${
                        r.installed
                            ? `<span class="badge-accent" style="font-size:0.72rem;padding:0.25rem 0.55rem;">✓ Installed</span>`
                            : `<button type="button" class="btn btn-secondary btn-sm btn-dl-curated-lora" data-preset="${escapeHtml(r.id)}">⬇ Download</button>`
                    }
                </div>
            </div>
        `
        )
        .join("");

    el.recommendedLorasList.querySelectorAll(".btn-dl-curated-lora").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const presetId = btn.dataset.preset;
            if (!presetId) return;
            const origText = btn.textContent;
            btn.disabled = true;
            btn.textContent = "Downloading...";
            try {
                const res = await fetch("/api/loras/download", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ preset_id: presetId }),
                });
                const data = await res.json();
                if (!res.ok) {
                    throw new Error(data.detail || "Failed to download LoRA");
                }
                showToast(`LoRA downloaded: ${data.filename} (${data.size_mb} MB)`, "success");
                await loadLoras(data.filename);
            } catch (err) {
                showToast("LoRA download failed: " + err.message, "error");
                btn.disabled = false;
                btn.textContent = origText;
            }
        });
    });
}

async function loadPresets() {
    try {
        const res = await fetch("/api/presets");
        const data = await res.json();
        state.presets = data.presets || {};
        renderPresetCards();
        if (data.default_negative_prompt) {
            state.defaultNegativePrompt = data.default_negative_prompt;
            if (!el.negPromptInput.value) {
                el.negPromptInput.value = data.default_negative_prompt;
            }
        }
    } catch (err) {
        console.error("Failed to load presets:", err);
    }
}

function renderPresetCards() {
    el.presetGrid.innerHTML = "";
    Object.values(state.presets).forEach((p) => {
        const card = document.createElement("div");
        card.className = `preset-card ${p.id === state.currentPreset ? "active" : ""}`;
        card.dataset.id = p.id;
        card.innerHTML = `
            <div class="preset-title">${escapeHtml(p.name)}</div>
            <div class="preset-sub">${escapeHtml(p.width)}x${escapeHtml(p.height)} • ${escapeHtml(p.badge)}</div>
        `;
        card.addEventListener("click", () => selectPreset(p.id));
        el.presetGrid.appendChild(card);
    });
}

function selectPreset(presetId) {
    const p = state.presets[presetId];
    if (!p) return;
    state.currentPreset = presetId;

    document.querySelectorAll(".preset-card").forEach((c) => {
        c.classList.toggle("active", c.dataset.id === presetId);
    });

    el.inputWidth.value = p.width;
    el.inputHeight.value = p.height;
    if (p.default_frames) {
        el.selectFrames.value = String(p.default_frames);
        updateDurationBadge();
    }
    if (p.recommended_steps && el.inputSteps && el.valSteps) {
        el.inputSteps.value = String(p.recommended_steps);
        el.valSteps.textContent = String(p.recommended_steps);
    }
}

function updateDurationBadge() {
    const frames = parseInt(el.selectFrames.value, 10) || 81;
    const fps = parseInt(el.inputFps.value, 10) || 24;
    const duration = (frames / fps).toFixed(1);
    el.durationBadge.textContent = `~${duration} sec @ ${fps} FPS`;
}

function clearStartImage() {
    state.startImageDataUrl = null;
    if (el.inputStartImage) el.inputStartImage.value = "";
    if (el.startImageThumb) el.startImageThumb.src = "";
    if (el.startImagePreview) el.startImagePreview.classList.add("hidden");
    if (el.startImageDropzone) el.startImageDropzone.classList.remove("hidden");
}

function handleStartImageFile(file) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
        showToast("Please select a valid PNG, JPEG, or WebP image.", "warn");
        return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => {
        const dataUrl = ev.target.result;
        state.startImageDataUrl = dataUrl;
        if (el.startImageThumb) el.startImageThumb.src = dataUrl;
        if (el.startImageName) el.startImageName.textContent = file.name;
        if (el.startImageDropzone) el.startImageDropzone.classList.add("hidden");
        if (el.startImagePreview) el.startImagePreview.classList.remove("hidden");
        showToast(`Starting image loaded: ${file.name}`, "info");
    };
    reader.readAsDataURL(file);
}

function setupFormListeners() {
    el.selectFrames.addEventListener("change", updateDurationBadge);
    el.inputFps.addEventListener("input", updateDurationBadge);

    if (el.startImageDropzone && el.inputStartImage) {
        el.startImageDropzone.addEventListener("click", () => el.inputStartImage.click());
        el.inputStartImage.addEventListener("change", (e) => {
            const file = e.target.files && e.target.files[0];
            if (file) handleStartImageFile(file);
        });
        el.startImageDropzone.addEventListener("dragover", (e) => {
            e.preventDefault();
            el.startImageDropzone.classList.add("drag-over");
        });
        el.startImageDropzone.addEventListener("dragleave", () => {
            el.startImageDropzone.classList.remove("drag-over");
        });
        el.startImageDropzone.addEventListener("drop", (e) => {
            e.preventDefault();
            el.startImageDropzone.classList.remove("drag-over");
            const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
            if (file) handleStartImageFile(file);
        });
    }

    if (el.btnClearStartImage) {
        el.btnClearStartImage.addEventListener("click", () => {
            clearStartImage();
            showToast("Starting image removed", "info");
        });
    }

    if (el.inputImageStrength && el.valImageStrength) {
        el.inputImageStrength.addEventListener("input", (e) => {
            el.valImageStrength.textContent = parseFloat(e.target.value).toFixed(2);
        });
    }

    if (el.selectLora) {
        el.selectLora.addEventListener("change", () => {
            if (el.loraScaleGroup) {
                el.loraScaleGroup.classList.toggle("hidden", el.selectLora.value === "none");
            }
        });
    }

    if (el.inputLoraScale && el.valLoraScale) {
        el.inputLoraScale.addEventListener("input", (e) => {
            el.valLoraScale.textContent = parseFloat(e.target.value).toFixed(2);
        });
    }

    if (el.btnRefreshLoras) {
        el.btnRefreshLoras.addEventListener("click", async () => {
            await loadLoras();
            showToast(`LoRA folder rescanned (${state.loras.length} found)`, "info");
        });
    }

    if (el.btnOpenLoraModal && el.loraModal) {
        el.btnOpenLoraModal.addEventListener("click", () => {
            loadLoras();
            el.loraModal.classList.remove("hidden");
        });
    }
    if (el.btnCloseLoraModal && el.loraModal) {
        el.btnCloseLoraModal.addEventListener("click", () => el.loraModal.classList.add("hidden"));
    }
    if (el.btnDoneLoraModal && el.loraModal) {
        el.btnDoneLoraModal.addEventListener("click", () => el.loraModal.classList.add("hidden"));
    }
    if (el.btnDownloadCustomLora) {
        el.btnDownloadCustomLora.addEventListener("click", async () => {
            const repoId = (el.inputCustomLoraRepo?.value || "").trim();
            const filename = (el.inputCustomLoraFile?.value || "").trim();
            if (!repoId) {
                showToast("Please enter a Hugging Face Repo ID (e.g. user/repo)", "warn");
                return;
            }
            const origText = el.btnDownloadCustomLora.textContent;
            el.btnDownloadCustomLora.disabled = true;
            el.btnDownloadCustomLora.textContent = "Fetching...";
            try {
                const res = await fetch("/api/loras/download", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ repo_id: repoId, filename: filename || undefined }),
                });
                const data = await res.json();
                if (!res.ok) {
                    throw new Error(data.detail || "Failed to fetch LoRA");
                }
                showToast(`Downloaded ${data.filename} (${data.size_mb} MB)`, "success");
                if (el.inputCustomLoraRepo) el.inputCustomLoraRepo.value = "";
                if (el.inputCustomLoraFile) el.inputCustomLoraFile.value = "";
                await loadLoras(data.filename);
            } catch (err) {
                showToast("Custom LoRA download error: " + err.message, "error");
            } finally {
                el.btnDownloadCustomLora.disabled = false;
                el.btnDownloadCustomLora.textContent = origText;
            }
        });
    }

    el.inputSteps.addEventListener("input", (e) => {
        el.valSteps.textContent = e.target.value;
    });

    el.inputCfg.addEventListener("input", (e) => {
        el.valCfg.textContent = parseFloat(e.target.value).toFixed(1);
    });

    el.btnRandomSeed.addEventListener("click", () => {
        const randomVal = Math.floor(Math.random() * 2147483647);
        el.inputSeed.value = randomVal;
        showToast(`Random seed set: ${randomVal}`, "info");
    });

    el.btnReset.addEventListener("click", () => {
        el.promptInput.value = "";
        el.negPromptInput.value = state.defaultNegativePrompt || "";
        clearStartImage();
        if (el.inputImageStrength && el.valImageStrength) {
            el.inputImageStrength.value = "0.85";
            el.valImageStrength.textContent = "0.85";
        }
        if (el.selectLora) {
            el.selectLora.value = "none";
            if (el.loraScaleGroup) el.loraScaleGroup.classList.add("hidden");
        }
        if (el.inputLoraScale && el.valLoraScale) {
            el.inputLoraScale.value = "0.80";
            el.valLoraScale.textContent = "0.80";
        }
        selectPreset("hd_16_9");
        el.inputSteps.value = "40";
        el.valSteps.textContent = "40";
        el.inputCfg.value = "5.0";
        el.valCfg.textContent = "5.0";
        el.inputSeed.value = "-1";
        el.inputFps.value = "24";
        updateDurationBadge();
        showToast("Settings reset to defaults", "info");
    });

    document.querySelectorAll(".chip").forEach((btn) => {
        btn.addEventListener("click", () => {
            const text = btn.dataset.sample;
            if (text) {
                el.promptInput.value = text;
                el.promptInput.focus();
                showToast("Sample prompt loaded!", "info");
            }
        });
    });

    el.btnSamplePrompts.addEventListener("click", () => {
        const samples = [
            "A cinematic drone shot through misty emerald valleys, cascading waterfalls in golden morning light, 4k.",
            "High speed slow motion of a splash of water forming a delicate glass rose, neon studio backlighting.",
            "A cute cozy cottage in autumn woods, smoke rising gently from chimney, falling leaves, atmospheric lighting.",
        ];
        const pick = samples[Math.floor(Math.random() * samples.length)];
        el.promptInput.value = pick;
        showToast("Applied creative prompt idea", "info");
    });

    // App Dialog button listeners
    el.btnAppDialogOk.addEventListener("click", () => closeAppDialog(true));
    el.btnAppDialogCancel.addEventListener("click", () => closeAppDialog(false));
    el.btnAppDialogClose.addEventListener("click", () => closeAppDialog(false));
}

// ----------------------------------------------------------------------- //
// Primary Button Dynamic State Manager & Video Generation Lifecycle
// ----------------------------------------------------------------------- //
function updateButtonState() {
    if (!el.btnGenerate) return;

    if (state.isGenerating) {
        el.btnGenerate.className = "btn btn-primary";
        el.btnGenerate.disabled = true;
        el.btnGenerate.innerHTML = `<span class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;margin-right:5px;"></span><span>Generating...</span>`;
        if (el.btnSmokeTest) el.btnSmokeTest.disabled = true;
        return;
    }

    if (el.btnSmokeTest) el.btnSmokeTest.disabled = false;

    const { isReady, isDownloading, pct, progressLabel } = normalizeModelStatus(state.lastStatus);

    if (isReady) {
        el.btnGenerate.className = "btn btn-primary";
        el.btnGenerate.innerHTML = `<span class="btn-icon">▶</span><span>Generate Video</span>`;
        el.btnGenerate.disabled = false;
        el.btnGenerate.title = "Generate motion video with Wan2.2-TI2V-5B";
    } else if (isDownloading) {
        el.btnGenerate.className = "btn btn-secondary btn-downloading-state";
        el.btnGenerate.innerHTML = `<span class="spinner" style="width:13px;height:13px;border-width:2px;display:inline-block;margin-right:6px;border-top-color:#f59e0b;"></span><span>Downloading Model (${escapeHtml(pct)}%)</span>`;
        el.btnGenerate.disabled = false;
        el.btnGenerate.title = `Model weights are currently downloading (${progressLabel}). Click for status.`;
    } else {
        el.btnGenerate.className = "btn btn-primary btn-download-model";
        const btnLabel = pct > 0 ? `Resume Download (${pct}%)` : `Download Wan2.2 (~31.9 GB)`;
        el.btnGenerate.innerHTML = `<span class="btn-icon">⬇</span><span>${escapeHtml(btnLabel)}</span>`;
        el.btnGenerate.disabled = false;
        el.btnGenerate.title = "Wan2.2-TI2V-5B model checkpoint is missing or incomplete. Click to download from Hugging Face.";
    }
}

function showGeneratingOverlay(job = null) {
    el.heroPlaceholder.classList.add("hidden");
    el.videoContainer.classList.add("hidden");
    el.generationOverlay.classList.remove("hidden");

    if (job && job.current_step > 0) {
        el.progressBarFill.style.width = `${job.progress_percent || 0}%`;
        el.metricStep.textContent = `Step: ${job.current_step} / ${job.total_steps} (${job.progress_percent || 0}%)`;
        el.metricSpeed.textContent = `${job.it_per_sec || "--"} it/s`;
        el.metricEta.textContent = `ETA: ${job.eta_sec ?? "--"}s`;
    } else {
        el.progressBarFill.style.width = "0%";
        el.metricStep.textContent = `Initializing Dual-GPU Pipeline...`;
        el.metricSpeed.textContent = `-- s/it`;
        el.metricEta.textContent = `ETA: --s`;
    }
}

async function ensureModelReady() {
    if (!state.lastStatus) return true;
    const { isReady, isDownloading, progressLabel, missing } = normalizeModelStatus(state.lastStatus);
    if (isReady) return true;

    if (isDownloading) {
        showAppDialog({
            title: "Model Checkpoint Downloading",
            message: "The Wan2.2-TI2V-5B video model is currently downloading in the background.",
            details: `Status: ${progressLabel || "In progress..."}\nMissing shards: ${missing.join(", ")}\n\nVideo generation will unlock automatically as soon as the download finishes.`,
            type: "warn",
        });
        return false;
    }

    el.btnDownloadModel.click();
    return false;
}

async function startGeneration(customPayload = null) {
    if (state.isGenerating) return;
    if (!(await ensureModelReady())) return;

    const prompt = customPayload ? customPayload.prompt : el.promptInput.value.trim();
    if (!prompt) {
        showToast("Please enter a prompt describing the video sequence.", "warn");
        el.promptInput.focus();
        return;
    }

    const payload = customPayload || {
        prompt: prompt,
        negative_prompt: el.negPromptInput.value.trim() || undefined,
        preset: state.currentPreset,
        width: parseInt(el.inputWidth.value, 10),
        height: parseInt(el.inputHeight.value, 10),
        num_frames: parseInt(el.selectFrames.value, 10),
        num_inference_steps: parseInt(el.inputSteps.value, 10),
        guidance_scale: parseFloat(el.inputCfg.value),
        seed: parseInt(el.inputSeed.value, 10),
        fps: parseInt(el.inputFps.value, 10),
        init_image: state.startImageDataUrl || undefined,
        image_strength: state.startImageDataUrl && el.inputImageStrength ? parseFloat(el.inputImageStrength.value) : undefined,
        lora_name: el.selectLora && el.selectLora.value !== "none" ? el.selectLora.value : undefined,
        lora_scale: el.selectLora && el.selectLora.value !== "none" && el.inputLoraScale ? parseFloat(el.inputLoraScale.value) : undefined,
    };

    state.isGenerating = true;
    updateButtonState();
    showGeneratingOverlay();

    try {
        const res = await fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (res.status >= 400) {
            finishGeneration(false, data.detail || "Server rejected generation request");
            return;
        }
        if (data.job_id) {
            state.activeJobId = data.job_id;
        }
    } catch (err) {
        console.error("Failed to submit generation job:", err);
        finishGeneration(false, "Failed to submit job to server: " + err.message);
    }
}

function syncActiveJob(activeJob) {
    if (activeJob && (activeJob.status === "running" || activeJob.status === "queued")) {
        state.activeJobId = activeJob.job_id;
        if (!state.isGenerating) {
            state.isGenerating = true;
            updateButtonState();
            showGeneratingOverlay(activeJob);
        }
    }
}

function onJobProgress(p, jobId = null) {
    if (jobId && state.activeJobId && jobId !== state.activeJobId) return;
    if (!state.isGenerating) {
        state.isGenerating = true;
        updateButtonState();
        showGeneratingOverlay();
    }
    el.progressBarFill.style.width = `${p.percent}%`;
    el.metricStep.textContent = `Step: ${p.step} / ${p.total_steps} (${p.percent}%)`;
    el.metricSpeed.textContent = `${p.it_per_sec} it/s`;
    el.metricEta.textContent = `ETA: ${p.eta_sec}s`;
}

function onJobCompleted(job) {
    state.isGenerating = false;
    state.activeJobId = null;
    updateButtonState();

    const result = job.result || {};
    const meta = result.metadata || {};
    const videoFile = result.video_filename || "";
    loadVideoIntoHero(
        {
            video_file: videoFile,
            video_url: `/outputs/${encodeURIComponent(videoFile)}`,
            metadata: { ...meta, prompt: meta.prompt || job.prompt },
        },
        true
    );

    showToast("Video generated successfully!", "success");
    loadGallery(videoFile);
}

function finishGeneration(success, errMsg = null) {
    state.isGenerating = false;
    state.activeJobId = null;
    updateButtonState();
    el.generationOverlay.classList.add("hidden");

    if (!success) {
        const detailStr = typeof errMsg === "string" ? errMsg : JSON.stringify(errMsg, null, 2);
        showAppDialog({
            title: "Generation Error",
            message: "An issue occurred during video synthesis.",
            details: detailStr || "Unknown issue occurred.",
            type: "error",
        });
        el.heroPlaceholder.classList.remove("hidden");
    }
}

// ----------------------------------------------------------------------- //
// Action Bar & Buttons Setup
// ----------------------------------------------------------------------- //
function setupActions() {
    el.btnGenerate.addEventListener("click", () => {
        startGeneration();
    });

    el.btnDownloadModel.addEventListener("click", async () => {
        const { pct, missing } = normalizeModelStatus(state.lastStatus);
        const gpus = state.lastStatus?.gpus || [];
        const hwDesc = gpus.length
            ? gpus.map((g) => `GPU ${g.index}: ${g.name}`).join(" + ")
            : "Local Compute Environment";
        const isResume = pct > 0;

        const confirmed = await showAppDialog({
            title: isResume ? "Resume Wan2.2 Download" : "Download Wan2.2-TI2V-5B Checkpoint",
            message: isResume
                ? `Resume downloading missing Wan2.2-TI2V-5B weights (${pct}% already downloaded)?`
                : "Download Wan2.2-TI2V-5B weights (~31.9 GB download, auto-optimized to ~22.6 GB bfloat16) from Hugging Face in the background?",
            details: `Repository: Wan-AI/Wan2.2-TI2V-5B-Diffusers\nHardware: ${hwDesc}\nLocal Directory: ./models/Wan2.2-TI2V-5B-Diffusers\nMissing shards: ${missing.join(", ") || "None"}`,
            type: "confirm",
            okText: isResume ? "Resume Download" : "Start Download",
        });

        if (confirmed) {
            try {
                const res = await fetch("/api/model/download", { method: "POST" });
                const data = await res.json();
                showToast(data.message || "Download initiated in background!", "success");
                checkSystemStatus(updateButtonState);
            } catch (err) {
                showAppDialog({
                    title: "Download Failed",
                    message: "Could not trigger model download.",
                    details: err.message,
                    type: "error",
                });
            }
        }
    });

    el.btnSmokeTest.addEventListener("click", async () => {
        const smokePrompt = "A glowing neon origami crane folding itself on dark water, bioluminescent ripples, high detail";
        el.promptInput.value = smokePrompt;
        selectPreset("draft_16_9");
        showToast("Loaded smoke test prompt & draft preset", "info");
        startGeneration();
    });

    // Scroll to Generated Outputs strip
    if (el.btnToggleGallery) {
        el.btnToggleGallery.addEventListener("click", () => {
            el.gallerySection?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        });
    }

    // Copy Prompt button
    if (el.btnCopyPrompt) {
        el.btnCopyPrompt.addEventListener("click", () => {
            const promptText = state.lastMetadata?.prompt || "";
            if (!promptText) {
                showToast("No prompt available to copy", "warn");
                return;
            }
            navigator.clipboard.writeText(promptText);
            showToast("Prompt copied to clipboard!", "success");
        });
    }

    // Diagnostics modal: Instant render from cached state, then refresh
    el.diagModalBtn.addEventListener("click", () => {
        if (state.lastStatus) {
            renderDiagnostics(state.lastStatus);
        }
        checkSystemStatus(updateButtonState);
        el.diagModal.classList.remove("hidden");
    });
    el.btnCloseDiag.addEventListener("click", () => el.diagModal.classList.add("hidden"));
    el.btnDoneDiag.addEventListener("click", () => el.diagModal.classList.add("hidden"));
    el.btnRefreshDiag.addEventListener("click", () => checkSystemStatus(updateButtonState));
    el.btnDiagDownload.addEventListener("click", () => el.btnDownloadModel.click());

    // Metadata modal
    el.btnViewMetadata.addEventListener("click", () => {
        el.jsonViewerContent.textContent = JSON.stringify(state.lastMetadata || {}, null, 2);
        el.metaModal.classList.remove("hidden");
    });
    el.btnCloseMeta.addEventListener("click", () => el.metaModal.classList.add("hidden"));
    el.btnDoneMeta.addEventListener("click", () => el.metaModal.classList.add("hidden"));
    el.btnCopyJson.addEventListener("click", () => {
        navigator.clipboard.writeText(el.jsonViewerContent.textContent);
        showToast("Metadata JSON copied to clipboard!", "success");
    });

    // Reuse parameters button
    el.btnReuseParams.addEventListener("click", () => {
        if (!state.lastMetadata) return;
        const m = state.lastMetadata;
        if (m.prompt) el.promptInput.value = m.prompt;
        if (m.negative_prompt !== undefined) el.negPromptInput.value = m.negative_prompt;
        if (m.width && m.height) {
            el.inputWidth.value = m.width;
            el.inputHeight.value = m.height;
            const matchedPreset =
                Object.values(state.presets).find(
                    (p) => p.width === m.width && p.height === m.height && (!m.num_frames || p.default_frames === m.num_frames)
                ) || Object.values(state.presets).find((p) => p.width === m.width && p.height === m.height);
            if (matchedPreset) {
                state.currentPreset = matchedPreset.id;
                document.querySelectorAll(".preset-card").forEach((c) => {
                    c.classList.toggle("active", c.dataset.id === matchedPreset.id);
                });
            }
        }
        if (m.fps) {
            el.inputFps.value = String(m.fps);
        }
        if (m.num_frames) {
            el.selectFrames.value = String(m.num_frames);
        }
        updateDurationBadge();
        if (m.num_inference_steps) {
            el.inputSteps.value = String(m.num_inference_steps);
            el.valSteps.textContent = String(m.num_inference_steps);
        }
        if (m.guidance_scale !== undefined) {
            el.inputCfg.value = String(m.guidance_scale);
            el.valCfg.textContent = parseFloat(m.guidance_scale).toFixed(1);
        }
        if (m.seed !== undefined) {
            el.inputSeed.value = String(m.seed);
        }
        if (el.selectLora) {
            if (m.lora_name && state.loras.some((l) => l.filename === m.lora_name)) {
                el.selectLora.value = m.lora_name;
                if (el.loraScaleGroup) el.loraScaleGroup.classList.remove("hidden");
            } else {
                el.selectLora.value = "none";
                if (el.loraScaleGroup) el.loraScaleGroup.classList.add("hidden");
            }
        }
        if (m.lora_scale !== undefined && m.lora_scale !== null && el.inputLoraScale && el.valLoraScale) {
            el.inputLoraScale.value = String(m.lora_scale);
            el.valLoraScale.textContent = parseFloat(m.lora_scale).toFixed(2);
        }
        showToast("Parameters restored into sidebar controls!", "success");
    });

    // Delete current video button in hero player
    if (el.btnDeleteVideo) {
        el.btnDeleteVideo.addEventListener("click", () => {
            if (state.currentVideoFile) {
                deleteVideoFile(state.currentVideoFile);
            }
        });
    }
}

// ----------------------------------------------------------------------- //
// Initialization
// ----------------------------------------------------------------------- //
document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    loadPresets();
    loadLoras();
    setupFormListeners();
    setupActions();
    initWebSocket({
        onButtonStateChange: updateButtonState,
        onSyncActiveJob: syncActiveJob,
        onJobProgress: onJobProgress,
        onJobCompleted: onJobCompleted,
        onJobFailed: (errMsg) => finishGeneration(false, errMsg),
    });
    checkSystemStatus(updateButtonState);
    loadGallery(true);

    // Fallback HTTP polling only when WebSocket is disconnected
    state.statusPollTimer = setInterval(() => {
        if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
            checkSystemStatus(updateButtonState);
        }
    }, 8000);
});
