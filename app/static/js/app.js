// Author: François Guillemette
/**
 * CrazyVideoGenerator — CrazyLogix Video Studio Client
 */

(function () {
    "use strict";

    // ----------------------------------------------------------------------- //
    // Application State
    // ----------------------------------------------------------------------- //
    const state = {
        presets: {},
        currentPreset: "hd_16_9",
        defaultNegativePrompt: "",
        activeJobId: null,
        isGenerating: false,
        socket: null,
        lastMetadata: null,
        lastStatus: null,
        currentVideoFile: null,
        startImageDataUrl: null,
        gallery: [],
        heartbeatTimer: null,
        statusPollTimer: null,
    };

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    // ----------------------------------------------------------------------- //
    // DOM Elements
    // ----------------------------------------------------------------------- //
    const el = {
        // Headers & Pills
        themeToggleBtn: document.getElementById("themeToggleBtn"),
        themeIcon: document.getElementById("themeIcon"),
        gpu0Mem: document.getElementById("gpu0Mem"),
        gpu1Mem: document.getElementById("gpu1Mem"),
        modelDot: document.getElementById("modelDot"),
        modelStatusText: document.getElementById("modelStatusText"),
        pillModel: document.getElementById("pillModel"),
        galleryCountBadge: document.getElementById("galleryCountBadge"),

        // Action Bar Buttons
        btnGenerate: document.getElementById("btnGenerate"),
        btnRandomSeed: document.getElementById("btnRandomSeed"),
        btnReset: document.getElementById("btnReset"),
        btnDownloadModel: document.getElementById("btnDownloadModel"),
        btnSmokeTest: document.getElementById("btnSmokeTest"),
        btnToggleGallery: document.getElementById("btnToggleGallery"),

        // Form Inputs
        promptInput: document.getElementById("promptInput"),
        negPromptInput: document.getElementById("negPromptInput"),
        inputStartImage: document.getElementById("inputStartImage"),
        startImageDropzone: document.getElementById("startImageDropzone"),
        startImagePreview: document.getElementById("startImagePreview"),
        startImageThumb: document.getElementById("startImageThumb"),
        startImageName: document.getElementById("startImageName"),
        btnClearStartImage: document.getElementById("btnClearStartImage"),
        inputImageStrength: document.getElementById("inputImageStrength"),
        valImageStrength: document.getElementById("valImageStrength"),
        presetGrid: document.getElementById("presetGrid"),
        inputWidth: document.getElementById("inputWidth"),
        inputHeight: document.getElementById("inputHeight"),
        selectFrames: document.getElementById("selectFrames"),
        durationBadge: document.getElementById("durationBadge"),
        inputSteps: document.getElementById("inputSteps"),
        valSteps: document.getElementById("valSteps"),
        inputCfg: document.getElementById("inputCfg"),
        valCfg: document.getElementById("valCfg"),
        inputSeed: document.getElementById("inputSeed"),
        inputFps: document.getElementById("inputFps"),
        btnSamplePrompts: document.getElementById("btnSamplePrompts"),
        hwTransformerDev: document.getElementById("hwTransformerDev"),
        hwAuxDev: document.getElementById("hwAuxDev"),

        // Hero Viewport Elements
        heroPlaceholder: document.getElementById("heroPlaceholder"),
        generationOverlay: document.getElementById("generationOverlay"),
        genStatusTitle: document.getElementById("genStatusTitle"),
        progressBarFill: document.getElementById("progressBarFill"),
        metricStep: document.getElementById("metricStep"),
        metricSpeed: document.getElementById("metricSpeed"),
        metricEta: document.getElementById("metricEta"),
        liveGpuStrip: document.getElementById("liveGpuStrip"),
        videoContainer: document.getElementById("videoContainer"),
        heroVideo: document.getElementById("heroVideo"),
        videoMetaPrompt: document.getElementById("videoMetaPrompt"),
        videoMetaDetails: document.getElementById("videoMetaDetails"),
        btnDownloadVideo: document.getElementById("btnDownloadVideo"),
        btnReuseParams: document.getElementById("btnReuseParams"),
        btnViewMetadata: document.getElementById("btnViewMetadata"),
        btnDeleteVideo: document.getElementById("btnDeleteVideo"),

        // Gallery Drawer
        galleryDrawer: document.getElementById("galleryDrawer"),
        btnCloseGallery: document.getElementById("btnCloseGallery"),
        galleryGrid: document.getElementById("galleryGrid"),

        // Modals
        diagModalBtn: document.getElementById("diagModalBtn"),
        diagModal: document.getElementById("diagModal"),
        btnCloseDiag: document.getElementById("btnCloseDiag"),
        btnDoneDiag: document.getElementById("btnDoneDiag"),
        btnRefreshDiag: document.getElementById("btnRefreshDiag"),
        btnDiagDownload: document.getElementById("btnDiagDownload"),
        diagGpuContainer: document.getElementById("diagGpuContainer"),
        diagModelInfo: document.getElementById("diagModelInfo"),
        diagDiskInfo: document.getElementById("diagDiskInfo"),

        metaModal: document.getElementById("metaModal"),
        btnCloseMeta: document.getElementById("btnCloseMeta"),
        btnDoneMeta: document.getElementById("btnDoneMeta"),
        btnCopyJson: document.getElementById("btnCopyJson"),
        jsonViewerContent: document.getElementById("jsonViewerContent"),

        // Application Dialog & Toast
        appDialogModal: document.getElementById("appDialogModal"),
        appDialogCard: document.getElementById("appDialogCard"),
        appDialogTitle: document.getElementById("appDialogTitle"),
        appDialogIcon: document.getElementById("appDialogIcon"),
        appDialogMessage: document.getElementById("appDialogMessage"),
        appDialogDetails: document.getElementById("appDialogDetails"),
        btnAppDialogOk: document.getElementById("btnAppDialogOk"),
        btnAppDialogCancel: document.getElementById("btnAppDialogCancel"),
        btnAppDialogClose: document.getElementById("btnAppDialogClose"),
        toastContainer: document.getElementById("toastContainer"),
    };

    // ----------------------------------------------------------------------- //
    // Custom Dialog & Toast System (Same L&F as CrazyLogix Design System)
    // ----------------------------------------------------------------------- //
    let dialogResolve = null;

    function showToast(message, type = "info") {
        if (!el.toastContainer) return;
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;

        let iconSvg = "";
        if (type === "success") {
            iconSvg = `<span style="color:#10b981;font-weight:bold;">✓</span>`;
        } else if (type === "warn") {
            iconSvg = `<span style="color:#f59e0b;font-weight:bold;">⚠️</span>`;
        } else if (type === "error") {
            iconSvg = `<span style="color:#ef4444;font-weight:bold;">✕</span>`;
        } else {
            iconSvg = `<span style="color:#38bdf8;font-weight:bold;">ℹ</span>`;
        }

        toast.innerHTML = `${iconSvg}<span>${escapeHtml(message)}</span>`;
        el.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(12px) scale(0.96)";
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    function showAppDialog({
        title = "Notification",
        message = "",
        details = null,
        type = "info",
        okText = "OK",
        cancelText = "Cancel",
    }) {
        return new Promise((resolve) => {
            dialogResolve = resolve;

            el.appDialogTitle.textContent = title;
            if (type === "error") {
                el.appDialogIcon.textContent = "❌";
                el.btnAppDialogOk.className = "btn btn-primary";
                el.btnAppDialogOk.style.backgroundColor = "var(--cl-danger, #ef4444)";
                el.btnAppDialogOk.style.color = "var(--cl-danger-on, #ffffff)";
            } else if (type === "warn") {
                el.appDialogIcon.textContent = "⚠️";
                el.btnAppDialogOk.className = "btn btn-primary";
                el.btnAppDialogOk.style.backgroundColor = "var(--cl-warn, #f59e0b)";
                el.btnAppDialogOk.style.color = "var(--cl-warn-on, #2b1600)";
            } else if (type === "confirm") {
                el.appDialogIcon.textContent = "❓";
                el.btnAppDialogOk.className = "btn btn-primary";
                el.btnAppDialogOk.style.backgroundColor = "var(--cl-accent)";
                el.btnAppDialogOk.style.color = "var(--cl-accent-text)";
            } else {
                el.appDialogIcon.textContent = "ℹ️";
                el.btnAppDialogOk.className = "btn btn-primary";
                el.btnAppDialogOk.style.backgroundColor = "var(--cl-accent)";
                el.btnAppDialogOk.style.color = "var(--cl-accent-text)";
            }

            el.appDialogMessage.textContent = message;
            if (details) {
                el.appDialogDetails.textContent = details;
                el.appDialogDetails.classList.remove("hidden");
            } else {
                el.appDialogDetails.classList.add("hidden");
            }

            el.btnAppDialogOk.textContent = okText;
            if (type === "confirm") {
                el.btnAppDialogCancel.textContent = cancelText;
                el.btnAppDialogCancel.classList.remove("hidden");
            } else {
                el.btnAppDialogCancel.classList.add("hidden");
            }

            el.appDialogModal.classList.remove("hidden");
        });
    }

    function closeAppDialog(result) {
        el.appDialogModal.classList.add("hidden");
        if (dialogResolve) {
            const cb = dialogResolve;
            dialogResolve = null;
            cb(result);
        }
    }

    // ----------------------------------------------------------------------- //
    // Theme Management (Explicit opt-in dark theme per CrazyLogix CLAUDE.md)
    // ----------------------------------------------------------------------- //
    function initTheme() {
        const stored = localStorage.getItem("crazylogix_theme") || "dark";
        setTheme(stored);
        el.themeToggleBtn.addEventListener("click", () => {
            const current = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
            setTheme(current);
        });
    }

    function setTheme(theme) {
        if (theme === "dark") {
            document.documentElement.setAttribute("data-theme", "dark");
            document.documentElement.classList.add("dark");
            el.themeIcon.textContent = "🌙";
            localStorage.setItem("crazylogix_theme", "dark");
        } else {
            document.documentElement.removeAttribute("data-theme");
            document.documentElement.classList.remove("dark");
            el.themeIcon.textContent = "☀️";
            localStorage.setItem("crazylogix_theme", "light");
        }
    }

    // ----------------------------------------------------------------------- //
    // Presets & Form Sync
    // ----------------------------------------------------------------------- //
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
    // Primary Button Dynamic State Manager
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

        const isReady = state.lastStatus?.model_ready ?? state.lastStatus?.model?.is_ready ?? false;
        const isDownloading = state.lastStatus?.model_downloading ?? state.lastStatus?.model?.is_downloading ?? false;
        const pct = state.lastStatus?.model_download_percent ?? state.lastStatus?.model?.download_percent ?? 0;
        const progressLabel = state.lastStatus?.model_download_label ?? state.lastStatus?.model?.download_progress_label ?? "";

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

    // ----------------------------------------------------------------------- //
    // Video Generation Lifecycle
    // ----------------------------------------------------------------------- //
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

    async function startGeneration(customPayload = null) {
        if (state.isGenerating) return;

        const prompt = customPayload ? customPayload.prompt : el.promptInput.value.trim();
        if (!prompt) {
            showToast("Please enter a prompt describing the video sequence.", "warn");
            el.promptInput.focus();
            return;
        }

        // Check model readiness before launching
        if (state.lastStatus) {
            const isReady = state.lastStatus.model_ready ?? state.lastStatus.model?.is_ready ?? false;
            const isDownloading = state.lastStatus.model_downloading ?? state.lastStatus.model?.is_downloading ?? false;
            const dlLabel = state.lastStatus.model_download_label ?? state.lastStatus.model?.download_progress_label ?? "In progress...";
            const missing = state.lastStatus.missing_components ?? state.lastStatus.model?.missing_components ?? [];

            if (isReady === false) {
                if (isDownloading) {
                    showAppDialog({
                        title: "Model Checkpoint Still Downloading",
                        message: "The Wan2.2-TI2V-5B video model is currently downloading in the background.",
                        details: `Status: ${dlLabel}\nMissing: ${missing.join(", ")}\n\nVideo generation will unlock automatically as soon as all weight shards are downloaded.`,
                        type: "warn",
                    });
                    return;
                } else {
                    const confirmDl = await showAppDialog({
                        title: "Model Checkpoint Required",
                        message: "The Wan2.2-TI2V-5B model weights (~31.9 GB download / ~22.6 GB in bf16) have not been downloaded yet.",
                        details: "Would you like to start the background download from Hugging Face now?",
                        type: "confirm",
                        okText: "Download Weights",
                    });
                    if (confirmDl) {
                        el.btnDownloadModel.click();
                    }
                    return;
                }
            }
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

        el.generationOverlay.classList.add("hidden");
        el.heroPlaceholder.classList.add("hidden");
        el.videoContainer.classList.remove("hidden");

        const result = job.result || {};
        const meta = result.metadata || {};
        state.lastMetadata = meta;
        state.currentVideoFile = result.video_filename || null;

        // Load video into hero viewer
        const videoUrl = `/outputs/${encodeURIComponent(result.video_filename || "")}`;
        el.heroVideo.src = videoUrl;
        el.heroVideo.play().catch(() => {});

        el.videoMetaPrompt.textContent = meta.prompt || job.prompt;
        el.videoMetaDetails.textContent = `${meta.width}x${meta.height} • ${meta.num_frames} Frames • ${meta.duration_seconds}s • Seed: ${meta.seed ?? "N/A"}`;
        el.btnDownloadVideo.href = videoUrl;

        showToast("Video generated successfully!", "success");
        loadGallery();
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
    // WebSocket Telemetry & Event Stream
    // ----------------------------------------------------------------------- //
    function initWebSocket() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws/generation`;

        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("WebSocket telemetry stream connected.");
            if (state.heartbeatTimer) clearInterval(state.heartbeatTimer);
            state.heartbeatTimer = setInterval(() => {
                if (state.socket && state.socket.readyState === WebSocket.OPEN) {
                    state.socket.send("ping");
                }
            }, 15000);
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === "telemetry" || msg.type === "pong") {
                    state.lastStatus = msg;
                    updateTelemetryPills(msg.gpus, msg.model, msg.download, msg.recommended_device_mapping);
                    if (msg.active_job) {
                        syncActiveJob(msg.active_job);
                    }

                    if (el.diagModal && !el.diagModal.classList.contains("hidden")) {
                        renderDiagnostics(msg);
                    }
                } else if (msg.type === "job_started") {
                    if (msg.job) {
                        syncActiveJob(msg.job);
                    }
                } else if (msg.type === "job_progress") {
                    onJobProgress(msg.progress, msg.job_id);
                    if (msg.gpus) updateTelemetryPills(msg.gpus, msg.model, msg.download);
                } else if (msg.type === "job_completed") {
                    onJobCompleted(msg.job);
                } else if (msg.type === "job_failed") {
                    finishGeneration(false, msg.job ? msg.job.error_message : "Inference failed");
                }
            } catch (err) {
                console.error("Error processing websocket payload:", err);
            }
        };

        ws.onclose = () => {
            console.warn("WebSocket disconnected. Retrying in 3 seconds...");
            if (state.heartbeatTimer) clearInterval(state.heartbeatTimer);
            setTimeout(initWebSocket, 3000);
        };

        state.socket = ws;
    }

    // ----------------------------------------------------------------------- //
    // UI Telemetry Pill Updates
    // ----------------------------------------------------------------------- //
    function formatDevBadge(dev) {
        if (!dev) return "N/A";
        if (dev.startsWith("cuda:")) {
            const idx = dev.split(":")[1];
            return `GPU ${idx} (${dev})`;
        }
        return dev.toUpperCase();
    }

    function updateTelemetryPills(gpus, modelInfo, downloadInfo, recommendedMapping = null) {
        // 1. Update GPU Pills & Live Overlay Strip
        if (gpus && Array.isArray(gpus)) {
            if (gpus.length >= 1) {
                const g0 = gpus[0];
                el.gpu0Mem.textContent = `${g0.memory_used_gib} / ${g0.memory_total_gib} GB`;
                el.gpu0Mem.title = `GPU 0: ${g0.name} | Temp: ${g0.temperature_c ?? "--"}°C | Util: ${g0.utilization_percent ?? 0}%`;
            }
            if (gpus.length >= 2) {
                const g1 = gpus[1];
                el.gpu1Mem.textContent = `${g1.memory_used_gib} / ${g1.memory_total_gib} GB`;
                el.gpu1Mem.title = `GPU 1: ${g1.name} | Temp: ${g1.temperature_c ?? "--"}°C | Util: ${g1.utilization_percent ?? 0}%`;
            } else {
                el.gpu1Mem.textContent = "N/A";
            }

            if (el.liveGpuStrip) {
                el.liveGpuStrip.innerHTML = gpus
                    .map(
                        (g) => `
                        <div class="gpu-live-item">
                            <span>GPU ${escapeHtml(g.index)}: ${escapeHtml(g.memory_used_gib)} / ${escapeHtml(g.memory_total_gib)} GiB</span>
                            <span>${g.utilization_percent !== null && g.utilization_percent !== undefined ? `${escapeHtml(g.utilization_percent)}%` : "--"} • ${g.temperature_c !== null && g.temperature_c !== undefined ? `${escapeHtml(g.temperature_c)}°C` : "--"}</span>
                        </div>
                    `
                    )
                    .join("");
            }
        }

        // Update Sidebar Hardware Orchestration Badges
        if (recommendedMapping) {
            if (el.hwTransformerDev && recommendedMapping.transformer_device) {
                el.hwTransformerDev.textContent = formatDevBadge(recommendedMapping.transformer_device);
            }
            if (el.hwAuxDev && recommendedMapping.text_encoder_device) {
                el.hwAuxDev.textContent = formatDevBadge(recommendedMapping.text_encoder_device);
            }
        }

        // 2. Update Model Readiness Pill & Action Buttons
        if (modelInfo) {
            const isReady = modelInfo.is_ready || false;
            const isDownloading = modelInfo.is_downloading || (downloadInfo && downloadInfo.status === "downloading");
            const pct = modelInfo.download_percent || (downloadInfo && downloadInfo.progress_percent) || 0;
            const progressLabel = modelInfo.download_progress_label || (downloadInfo && downloadInfo.message) || "";

            if (isReady) {
                el.modelDot.className = "pill-dot dot-active";
                el.modelStatusText.textContent = "Ready";
                el.pillModel.title = `Wan2.2-TI2V-5B Ready (${modelInfo.model_size_gib || "22.6"} GiB loaded)`;

                el.btnDownloadModel.classList.add("hidden");
                el.btnDownloadModel.innerHTML = `<span>✓ Model Ready</span>`;
                el.btnDownloadModel.disabled = false;
                el.btnDiagDownload.innerHTML = `✓ Model Ready (${escapeHtml(modelInfo.model_size_gib || "22.6")} GiB Installed)`;
                el.btnDiagDownload.disabled = true;
            } else if (isDownloading) {
                el.modelDot.className = "pill-dot dot-warning";
                el.modelStatusText.textContent = `Downloading ${pct}%`;
                el.pillModel.title = `Wan2.2 Checkpoint Downloading: ${progressLabel}`;

                el.btnDownloadModel.classList.remove("hidden");
                el.btnDownloadModel.innerHTML = `<span>⏳ Downloading (${escapeHtml(pct)}%)</span>`;
                el.btnDownloadModel.disabled = true;
                el.btnDiagDownload.innerHTML = `⏳ Downloading Wan2.2-TI2V-5B Weights... (${escapeHtml(progressLabel)})`;
                el.btnDiagDownload.disabled = true;
            } else {
                el.btnDownloadModel.classList.remove("hidden");
                if (pct > 0) {
                    el.modelDot.className = "pill-dot dot-warning";
                    el.modelStatusText.textContent = `Incomplete (${pct}%)`;
                    el.pillModel.title = `Wan2.2 checkpoint incomplete: ${progressLabel}. Click to resume.`;

                    el.btnDownloadModel.innerHTML = `<span>⬇ Resume Download (${escapeHtml(pct)}%)</span>`;
                    el.btnDownloadModel.disabled = false;
                    el.btnDiagDownload.innerHTML = `⬇ Resume Download (${escapeHtml(pct)}% installed)`;
                    el.btnDiagDownload.disabled = false;
                } else {
                    el.modelDot.className = "pill-dot dot-danger";
                    el.modelStatusText.textContent = "Missing";
                    el.pillModel.title = "Wan2.2-TI2V-5B checkpoint not found locally. Click to download.";

                    el.btnDownloadModel.innerHTML = `<span>⬇ Download Model</span>`;
                    el.btnDownloadModel.disabled = false;
                    el.btnDiagDownload.innerHTML = `⬇ Download Wan2.2-TI2V-5B Weights (~31.9 GB)`;
                    el.btnDiagDownload.disabled = false;
                }
            }

            // Sync Primary Generate Button
            updateButtonState();
        }
    }

    // ----------------------------------------------------------------------- //
    // System Status & Diagnostics
    // ----------------------------------------------------------------------- //
    async function checkSystemStatus() {
        try {
            const res = await fetch("/api/status");
            const data = await res.json();
            state.lastStatus = data;

            const modelObj = {
                is_ready: data.model_ready,
                is_downloading: data.model_downloading,
                status_label: data.model_status_label,
                model_size_gib: data.model_size_gib,
                total_size_gib: data.model_total_gib,
                download_percent: data.model_download_percent,
                download_progress_label: data.model_download_label,
                missing_components: data.missing_components,
            };

            updateTelemetryPills(data.gpus, modelObj, null, data.recommended_device_mapping);
            renderDiagnostics(data);
        } catch (err) {
            console.error("Status check failed:", err);
        }
    }

    function renderDiagnostics(data) {
        if (!data) return;

        // Render GPUs in modal
        const gpus = data.gpus || [];
        if (gpus.length) {
            el.diagGpuContainer.innerHTML = gpus
                .map(
                    (g) => `
                <div class="diag-gpu-card">
                    <strong>GPU ${escapeHtml(g.index)}: ${escapeHtml(g.name)}</strong><br>
                    <span>VRAM: ${escapeHtml(g.memory_used_gib)} / ${escapeHtml(g.memory_total_gib)} GB</span><br>
                    <span>Free: ${escapeHtml(g.memory_free_gib)} GB</span>
                    ${g.temperature_c !== null && g.temperature_c !== undefined ? `<br><span>Temp: ${escapeHtml(g.temperature_c)}°C</span>` : ""}
                    ${g.utilization_percent !== null && g.utilization_percent !== undefined ? `<br><span>Util: ${escapeHtml(g.utilization_percent)}%</span>` : ""}
                </div>
            `
                )
                .join("");
        } else {
            el.diagGpuContainer.innerHTML = `<em>No NVIDIA GPUs detected via nvidia-smi.</em>`;
        }

        // Render model status
        const isReady = data.model_ready ?? (data.model?.is_ready ?? false);
        const isDownloading = data.model_downloading ?? (data.model?.is_downloading ?? false);
        const progressLabel = data.model_download_label ?? (data.model?.download_progress_label ?? "");
        const cleanSize = data.model_size_gib ?? (data.model?.model_size_gib ?? 0);
        const totalSize = data.model_total_gib ?? (data.model?.total_size_gib ?? cleanSize);
        const missing = data.missing_components ?? (data.model?.missing_components ?? []);

        let statusText = "❌ Not Downloaded";
        if (isReady) {
            statusText = "✅ Ready (Installed)";
        } else if (isDownloading) {
            statusText = `⏳ Downloading (${escapeHtml(progressLabel)})`;
        } else if (totalSize > 0.1) {
            statusText = `⚠️ Incomplete (${escapeHtml(progressLabel)})`;
        }

        let missingHtml = "";
        if (missing && missing.length > 0 && !isReady) {
            missingHtml = `<p><strong>Missing Shards:</strong> <span style="color:#f59e0b;font-size:0.75rem;">${escapeHtml(missing.join(", "))}</span></p>`;
        }

        el.diagModelInfo.innerHTML = `
            <p><strong>Identifier:</strong> ${escapeHtml(data.model_id || "Wan-AI/Wan2.1-T2V-1.3B-Diffusers")}</p>
            <p><strong>Status:</strong> ${statusText}</p>
            <p><strong>Clean Size:</strong> ${escapeHtml(cleanSize)} GiB (Total with cache: ${escapeHtml(totalSize)} GiB)</p>
            ${missingHtml}
        `;

        // Render disk info
        const disk = data.disk;
        if (disk) {
            el.diagDiskInfo.innerHTML = `
                <p><strong>Models Drive:</strong> ${escapeHtml(disk.models ? disk.models.free_gib : "--")} GB Free</p>
                <p><strong>Outputs Drive:</strong> ${escapeHtml(disk.outputs ? disk.outputs.free_gib : "--")} GB Free</p>
            `;
        }
    }

    // ----------------------------------------------------------------------- //
    // Gallery & Saved Outputs
    // ----------------------------------------------------------------------- //
    async function loadGallery() {
        try {
            const res = await fetch("/api/gallery");
            const data = await res.json();
            state.gallery = data.videos || [];
            el.galleryCountBadge.textContent = state.gallery.length;
            renderGallery();
        } catch (err) {
            console.error("Failed to load gallery:", err);
        }
    }

    function renderGallery() {
        if (!state.gallery.length) {
            el.galleryGrid.innerHTML = `<p style="font-size:0.8rem;color:var(--cl-muted);">No generated videos yet.</p>`;
            return;
        }

        el.galleryGrid.innerHTML = state.gallery
            .map((item) => {
                const meta = item.metadata || {};
                const prompt = meta.prompt || item.video_file;
                const thumb = item.thumbnail_url || "";
                return `
                <div class="gallery-card" data-file="${escapeHtml(item.video_file)}">
                    <div class="gallery-thumb-wrap">
                        ${thumb ? `<img src="${escapeHtml(thumb)}" class="gallery-thumb-img" alt="Thumbnail">` : `<div style="color:#666;">🎬 Video</div>`}
                        <div class="gallery-play-icon">▶</div>
                        <button type="button" class="gallery-delete-btn" data-delete-file="${escapeHtml(item.video_file)}" title="Delete video">🗑</button>
                    </div>
                    <div class="gallery-card-body">
                        <div class="gallery-card-prompt">${escapeHtml(prompt)}</div>
                        <div class="gallery-card-meta">
                            <span>${escapeHtml(meta.width || "--")}x${escapeHtml(meta.height || "--")} • ${escapeHtml(meta.duration_seconds || "--")}s</span>
                            <span>${escapeHtml(item.size_mb || 0)} MB</span>
                        </div>
                    </div>
                </div>
            `;
            })
            .join("");

        el.galleryGrid.querySelectorAll(".gallery-card").forEach((card) => {
            card.addEventListener("click", () => {
                const file = card.dataset.file;
                const item = state.gallery.find((x) => x.video_file === file);
                if (item) {
                    loadVideoIntoHero(item);
                    el.galleryDrawer.classList.remove("open");
                }
            });
        });

        el.galleryGrid.querySelectorAll(".gallery-delete-btn").forEach((btn) => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const file = btn.dataset.deleteFile;
                if (!file) return;
                await deleteVideoFile(file);
            });
        });
    }

    async function deleteVideoFile(file) {
        if (!file) return;
        const confirmed = await showAppDialog({
            title: "Delete Video",
            message: `Are you sure you want to delete "${file}" and its metadata?`,
            type: "confirm",
            okText: "Delete",
        });
        if (!confirmed) return;

        try {
            const res = await fetch(`/api/gallery/${encodeURIComponent(file)}`, { method: "DELETE" });
            if (res.ok) {
                showToast("Video deleted", "info");
                if (state.currentVideoFile === file) {
                    el.heroVideo.pause();
                    el.heroVideo.removeAttribute("src");
                    el.heroVideo.load();
                    state.currentVideoFile = null;
                    state.lastMetadata = null;
                    el.videoContainer.classList.add("hidden");
                    el.heroPlaceholder.classList.remove("hidden");
                }
                await loadGallery();
            } else {
                showToast("Failed to delete video", "error");
            }
        } catch (err) {
            showToast("Error deleting video: " + err.message, "error");
        }
    }

    function loadVideoIntoHero(item) {
        state.lastMetadata = item.metadata || {};
        state.currentVideoFile = item.video_file || null;
        el.heroPlaceholder.classList.add("hidden");
        el.generationOverlay.classList.add("hidden");
        el.videoContainer.classList.remove("hidden");

        el.heroVideo.src = item.video_url;
        el.heroVideo.play().catch(() => {});

        const meta = item.metadata || {};
        el.videoMetaPrompt.textContent = meta.prompt || item.video_file;
        el.videoMetaDetails.textContent = `${meta.width || 832}x${meta.height || 480} • ${meta.num_frames || 81} Frames • ${meta.duration_seconds || 5.0}s • Seed: ${meta.seed ?? "N/A"}`;
        el.btnDownloadVideo.href = item.video_url;
    }

    // ----------------------------------------------------------------------- //
    // Action Bar & Buttons Setup
    // ----------------------------------------------------------------------- //
    function setupActions() {
        el.btnGenerate.addEventListener("click", () => {
            if (state.isGenerating) return;

            const isReady = state.lastStatus?.model_ready ?? state.lastStatus?.model?.is_ready;
            const isDownloading = state.lastStatus?.model_downloading ?? state.lastStatus?.model?.is_downloading;
            const dlLabel = state.lastStatus?.model_download_label ?? state.lastStatus?.model?.download_progress_label ?? "In progress...";
            const missing = state.lastStatus?.missing_components ?? state.lastStatus?.model?.missing_components ?? [];

            if (isReady === false) {
                if (isDownloading) {
                    showAppDialog({
                        title: "Model Checkpoint Downloading",
                        message: "The Wan2.2-TI2V-5B video model is currently downloading in the background.",
                        details: `Status: ${dlLabel}\nMissing shards: ${missing.join(", ")}\n\nVideo generation will unlock automatically as soon as the download finishes.`,
                        type: "warn",
                    });
                    return;
                } else {
                    // Click directly triggers model download!
                    el.btnDownloadModel.click();
                    return;
                }
            }
            startGeneration();
        });

        el.btnDownloadModel.addEventListener("click", async () => {
            const pct = state.lastStatus?.model_download_percent ?? state.lastStatus?.model?.download_percent ?? 0;
            const missing = state.lastStatus?.missing_components ?? state.lastStatus?.model?.missing_components ?? [];
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
                    checkSystemStatus();
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

        // Gallery toggle
        el.btnToggleGallery.addEventListener("click", () => {
            el.galleryDrawer.classList.toggle("open");
        });
        el.btnCloseGallery.addEventListener("click", () => {
            el.galleryDrawer.classList.remove("open");
        });

        // Diagnostics modal: Instant render from cached state, then refresh
        el.diagModalBtn.addEventListener("click", () => {
            if (state.lastStatus) {
                renderDiagnostics(state.lastStatus);
            }
            checkSystemStatus();
            el.diagModal.classList.remove("hidden");
        });
        el.btnCloseDiag.addEventListener("click", () => el.diagModal.classList.add("hidden"));
        el.btnDoneDiag.addEventListener("click", () => el.diagModal.classList.add("hidden"));
        el.btnRefreshDiag.addEventListener("click", () => checkSystemStatus());
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
                const matchedPreset = Object.values(state.presets).find(
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
        setupFormListeners();
        setupActions();
        initWebSocket();
        checkSystemStatus();
        loadGallery();

        // Fallback HTTP polling only when WebSocket is disconnected
        state.statusPollTimer = setInterval(() => {
            if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
                checkSystemStatus();
            }
        }, 8000);
    });
})();
