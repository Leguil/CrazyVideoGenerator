// Author: François Guillemette
/**
 * CrazyVideoGenerator — Output Video Gallery & Hero Video Player Management
 */

import { el, escapeHtml, state } from "./state.js";
import { showAppDialog, showToast } from "./ui-dialogs.js";

export async function loadGallery() {
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

export function renderGallery() {
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

export function loadVideoIntoHero(item) {
    state.lastMetadata = item.metadata || {};
    state.currentVideoFile = item.video_file || null;
    el.heroPlaceholder.classList.add("hidden");
    el.generationOverlay.classList.add("hidden");
    el.videoContainer.classList.remove("hidden");

    el.heroVideo.src = item.video_url;
    el.heroVideo.play().catch(() => {});

    const meta = item.metadata || {};
    el.videoMetaPrompt.textContent = meta.prompt || item.video_file;
    el.videoMetaDetails.textContent = `${meta.width || 1280}x${meta.height || 704} • ${meta.num_frames || 81} Frames • ${meta.duration_seconds || 3.4}s • Seed: ${meta.seed ?? "N/A"}`;
    el.btnDownloadVideo.href = item.video_url;
}
