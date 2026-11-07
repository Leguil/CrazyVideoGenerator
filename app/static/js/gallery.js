// Author: François Guillemette
/**
 * CrazyVideoGenerator — Output Video Gallery & Hero Video Player Management
 */

import { el, escapeHtml, state } from "./state.js";
import { showAppDialog, showToast } from "./ui-dialogs.js";

export async function loadGallery(selectTarget = null) {
    try {
        const res = await fetch("/api/gallery");
        const data = await res.json();
        state.gallery = data.videos || [];
        renderGallery(selectTarget);
    } catch (err) {
        console.error("Failed to load gallery:", err);
    }
}

export function renderGallery(selectTarget = null) {
    const count = state.gallery.length;
    if (el.galleryCountBadge) {
        el.galleryCountBadge.textContent = count;
    }
    if (el.galleryCount) {
        el.galleryCount.textContent = `${count} video${count === 1 ? "" : "s"}`;
    }

    if (!count) {
        state.currentVideoFile = null;
        state.lastMetadata = null;
        if (el.heroVideo) {
            el.heroVideo.pause();
            el.heroVideo.removeAttribute("src");
            el.heroVideo.load();
        }
        if (el.videoContainer) el.videoContainer.classList.add("hidden");
        if (el.metadataCard) el.metadataCard.classList.add("hidden");
        if (!state.isGenerating && el.heroPlaceholder) {
            el.heroPlaceholder.classList.remove("hidden");
        }
        if (el.videoMetaPrompt) el.videoMetaPrompt.textContent = "No video selected";
        if (el.videoMetaDetails) el.videoMetaDetails.textContent = "--";
        el.galleryGrid.innerHTML = `<div style="grid-column:1/-1;text-align:center;color:var(--cl-muted);font-size:0.8rem;padding:1.25rem;">No generated videos yet. Run a generation job to populate outputs!</div>`;
        return;
    }

    let targetIndex = -1;
    if (typeof selectTarget === "string") {
        targetIndex = state.gallery.findIndex((x) => x.video_file === selectTarget);
    } else if (selectTarget === true || !state.currentVideoFile) {
        targetIndex = 0;
    } else {
        targetIndex = state.gallery.findIndex((x) => x.video_file === state.currentVideoFile);
    }
    if (targetIndex < 0) targetIndex = 0;

    const selectedFile = state.gallery[targetIndex]?.video_file || null;

    el.galleryGrid.innerHTML = state.gallery
        .map((item) => {
            const meta = item.metadata || {};
            const prompt = meta.prompt || item.video_file;
            const thumb = item.thumbnail_url || "";
            const isActive = item.video_file === selectedFile;
            const durationLabel = meta.duration_seconds ? `${meta.duration_seconds}s` : `${item.size_mb || 0}MB`;
            return `
            <div class="gallery-item ${isActive ? "active" : ""}" data-file="${escapeHtml(item.video_file)}" title="${escapeHtml(prompt)}">
                ${
                    thumb
                        ? `<img src="${escapeHtml(thumb)}" alt="${escapeHtml(item.video_file)}" loading="lazy">`
                        : `<div class="gallery-item-fallback">🎬</div>`
                }
                <div class="gallery-play-icon">▶</div>
                <span class="gallery-item-badge">${escapeHtml(durationLabel)}</span>
                <button type="button" class="gallery-delete-btn" data-delete-file="${escapeHtml(item.video_file)}" title="Delete video">🗑</button>
            </div>
        `;
        })
        .join("");

    el.galleryGrid.querySelectorAll(".gallery-item").forEach((tile) => {
        tile.addEventListener("click", () => {
            const file = tile.dataset.file;
            const item = state.gallery.find((x) => x.video_file === file);
            if (item) {
                el.galleryGrid.querySelectorAll(".gallery-item").forEach((n) => n.classList.remove("active"));
                tile.classList.add("active");
                loadVideoIntoHero(item, true);
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

    if (selectTarget !== null || !state.currentVideoFile) {
        const targetItem = state.gallery[targetIndex];
        if (targetItem && !state.isGenerating) {
            loadVideoIntoHero(targetItem, typeof selectTarget === "string");
        }
    }
}

export async function deleteVideoFile(file) {
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
            const wasActive = state.currentVideoFile === file;
            if (wasActive) {
                state.currentVideoFile = null;
                state.lastMetadata = null;
            }
            await loadGallery(wasActive ? true : null);
        } else {
            showToast("Failed to delete video", "error");
        }
    } catch (err) {
        showToast("Error deleting video: " + err.message, "error");
    }
}

export function loadVideoIntoHero(item, autoPlay = false) {
    const meta = item.metadata || {};
    state.lastMetadata = meta;
    state.currentVideoFile = item.video_file || null;

    el.heroPlaceholder.classList.add("hidden");
    el.generationOverlay.classList.add("hidden");
    el.videoContainer.classList.remove("hidden");

    if (el.heroVideo.getAttribute("src") !== item.video_url) {
        el.heroVideo.src = item.video_url;
    }
    if (autoPlay) {
        el.heroVideo.play().catch(() => {});
    }

    const width = meta.width || 1280;
    const height = meta.height || 704;
    const frames = meta.num_frames || 81;
    const fps = meta.fps || 24;
    const duration = meta.duration_seconds ?? (frames / fps).toFixed(1);
    const seed = meta.seed ?? "N/A";
    const steps = meta.num_inference_steps ?? "--";
    const cfg = meta.guidance_scale ?? "--";
    const elapsed = (meta.generation_time_seconds ?? meta.inference_time_seconds) != null
        ? `${meta.generation_time_seconds ?? meta.inference_time_seconds}s`
        : "--";
    const modeLabel = meta.generation_mode === "i2v" || meta.has_init_image ? "Image-to-Video (I2V)" : "Text-to-Video (T2V)";
    const loraSuffix = meta.lora_name ? ` + LoRA: ${meta.lora_name} (${meta.lora_scale ?? 0.8}x)` : "";
    const modelName = (meta.model_id ? `${meta.model_id} (${modeLabel})` : `Wan2.2-TI2V-5B (${modeLabel})`) + loraSuffix;

    el.videoMetaPrompt.textContent = meta.prompt || item.video_file || "Generated Video";
    el.videoMetaDetails.textContent = `${width}×${height} • ${frames} Frames (${duration}s @ ${fps}fps) • Seed: ${seed}`;
    el.btnDownloadVideo.href = item.video_url;

    if (el.metadataCard) {
        el.metadataCard.classList.remove("hidden");
        if (el.metaPrompt) el.metaPrompt.textContent = meta.prompt || "--";
        if (el.metaDims) el.metaDims.textContent = `${width}×${height} • ${frames}f (${duration}s @ ${fps}fps)`;
        if (el.metaSeed) el.metaSeed.textContent = String(seed);
        if (el.metaStepsCfg) el.metaStepsCfg.textContent = `${steps} steps / CFG ${cfg}`;
        if (el.metaElapsed) el.metaElapsed.textContent = elapsed;
        if (el.metaModel) el.metaModel.textContent = modelName;
    }
}
