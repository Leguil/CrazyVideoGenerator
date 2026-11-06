// Author: François Guillemette
/**
 * CrazyVideoGenerator — WebSocket Telemetry Stream, GPU/Model Pills, and Diagnostics
 */

import { el, escapeHtml, normalizeModelStatus, state } from "./state.js";

export function formatDevBadge(dev) {
    if (!dev) return "N/A";
    if (dev.startsWith("cuda:")) {
        const idx = dev.split(":")[1];
        return `GPU ${idx} (${dev})`;
    }
    return dev.toUpperCase();
}

export function updateTelemetryPills(
    gpus,
    modelInfo,
    downloadInfo,
    recommendedMapping = null,
    onButtonStateChange = null
) {
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
        if (el.hwAuxDev) {
            const teDev = recommendedMapping.text_encoder_device;
            const vaeDev = recommendedMapping.vae_device;
            if (teDev && vaeDev && teDev !== vaeDev) {
                el.hwAuxDev.textContent = `${formatDevBadge(teDev)} / ${formatDevBadge(vaeDev)}`;
            } else if (vaeDev || teDev) {
                el.hwAuxDev.textContent = formatDevBadge(vaeDev || teDev);
            }
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

        if (onButtonStateChange) {
            onButtonStateChange();
        }
    }
}

export function renderDiagnostics(data) {
    if (!data) return;

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

    const { isReady, isDownloading, progressLabel, cleanSize, totalSize, missing } = normalizeModelStatus(data);

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
        <p><strong>Identifier:</strong> ${escapeHtml(data.model_id || "Wan-AI/Wan2.2-TI2V-5B-Diffusers")}</p>
        <p><strong>Status:</strong> ${statusText}</p>
        <p><strong>Clean Size:</strong> ${escapeHtml(cleanSize)} GiB (Total with cache: ${escapeHtml(totalSize)} GiB)</p>
        ${missingHtml}
    `;

    const disk = data.disk;
    if (disk) {
        el.diagDiskInfo.innerHTML = `
            <p><strong>Models Drive:</strong> ${escapeHtml(disk.models ? disk.models.free_gib : "--")} GB Free</p>
            <p><strong>Outputs Drive:</strong> ${escapeHtml(disk.outputs ? disk.outputs.free_gib : "--")} GB Free</p>
        `;
    }
}

export async function checkSystemStatus(onButtonStateChange = null) {
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

        updateTelemetryPills(data.gpus, modelObj, null, data.recommended_device_mapping, onButtonStateChange);
        renderDiagnostics(data);
    } catch (err) {
        console.error("Status check failed:", err);
    }
}

export function initWebSocket(callbacks) {
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
                updateTelemetryPills(
                    msg.gpus,
                    msg.model,
                    msg.download,
                    msg.recommended_device_mapping,
                    callbacks.onButtonStateChange
                );
                if (msg.active_job && callbacks.onSyncActiveJob) {
                    callbacks.onSyncActiveJob(msg.active_job);
                }
                if (el.diagModal && !el.diagModal.classList.contains("hidden")) {
                    renderDiagnostics(msg);
                }
            } else if (msg.type === "job_started") {
                if (msg.job && callbacks.onSyncActiveJob) {
                    callbacks.onSyncActiveJob(msg.job);
                }
            } else if (msg.type === "job_progress") {
                if (callbacks.onJobProgress) callbacks.onJobProgress(msg.progress, msg.job_id);
                if (msg.gpus) {
                    updateTelemetryPills(msg.gpus, msg.model, msg.download, null, callbacks.onButtonStateChange);
                }
            } else if (msg.type === "job_completed") {
                if (callbacks.onJobCompleted) callbacks.onJobCompleted(msg.job);
            } else if (msg.type === "job_failed") {
                if (callbacks.onJobFailed) {
                    callbacks.onJobFailed(msg.job ? msg.job.error_message : "Inference failed");
                }
            }
        } catch (err) {
            console.error("Error processing websocket payload:", err);
        }
    };

    ws.onclose = () => {
        console.warn("WebSocket disconnected. Retrying in 3 seconds...");
        if (state.heartbeatTimer) clearInterval(state.heartbeatTimer);
        setTimeout(() => initWebSocket(callbacks), 3000);
    };

    state.socket = ws;
}
