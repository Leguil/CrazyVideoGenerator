// Author: François Guillemette
/**
 * CrazyVideoGenerator — Shared Client State, DOM Registry, and Format Helpers
 */

export const state = {
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
    loras: [],
    recommendedLoras: [],
    gallery: [],
    heartbeatTimer: null,
    statusPollTimer: null,
};

export function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

export function normalizeModelStatus(data, downloadInfo = null) {
    if (!data) {
        return {
            isReady: false,
            isDownloading: false,
            pct: 0,
            progressLabel: "",
            cleanSize: 0,
            totalSize: 0,
            missing: [],
        };
    }
    const m = data.model || {};
    const dl = downloadInfo || data.download || {};
    const cleanSize = data.model_size_gib ?? m.model_size_gib ?? 0;
    return {
        isReady: Boolean(data.model_ready ?? m.is_ready ?? false),
        isDownloading: Boolean((data.model_downloading ?? m.is_downloading) || dl.status === "downloading"),
        pct: data.model_download_percent ?? m.download_percent ?? dl.progress_percent ?? 0,
        progressLabel: data.model_download_label ?? m.download_progress_label ?? dl.message ?? "",
        cleanSize: cleanSize,
        totalSize: data.model_total_gib ?? m.total_size_gib ?? cleanSize,
        missing: data.missing_components ?? m.missing_components ?? [],
    };
}

export const el = {
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
    selectLora: document.getElementById("selectLora"),
    btnRefreshLoras: document.getElementById("btnRefreshLoras"),
    btnOpenLoraModal: document.getElementById("btnOpenLoraModal"),
    loraScaleGroup: document.getElementById("loraScaleGroup"),
    inputLoraScale: document.getElementById("inputLoraScale"),
    valLoraScale: document.getElementById("valLoraScale"),
    presetGrid: document.getElementById("presetGrid"),
    inputWidth: document.getElementById("inputWidth"),
    inputHeight: document.getElementById("inputHeight"),
    selectFrames: document.getElementById("selectFrames"),
    durationBadge: document.getElementById("durationBadge"),
    inputSteps: document.getElementById("inputSteps"),
    valSteps: document.getElementById("valSteps"),
    inputCfg: document.getElementById("inputCfg"),
    valCfg: document.getElementById("valCfg"),
    inputFlowShift: document.getElementById("inputFlowShift"),
    valFlowShift: document.getElementById("valFlowShift"),
    selectInterpolator: document.getElementById("selectInterpolator"),
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
    btnCopyPrompt: document.getElementById("btnCopyPrompt"),
    btnDownloadVideo: document.getElementById("btnDownloadVideo"),
    btnReuseParams: document.getElementById("btnReuseParams"),
    btnViewMetadata: document.getElementById("btnViewMetadata"),
    btnDeleteVideo: document.getElementById("btnDeleteVideo"),

    // Synthesis Inspector & Provenance Card
    metadataCard: document.getElementById("metadataCard"),
    metaPrompt: document.getElementById("metaPrompt"),
    metaDims: document.getElementById("metaDims"),
    metaSeed: document.getElementById("metaSeed"),
    metaStepsCfg: document.getElementById("metaStepsCfg"),
    metaElapsed: document.getElementById("metaElapsed"),
    metaModel: document.getElementById("metaModel"),

    // Generated Outputs Section
    gallerySection: document.getElementById("gallerySection"),
    galleryCount: document.getElementById("galleryCount"),
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

    // LoRA Manager Modal
    loraModal: document.getElementById("loraModal"),
    btnCloseLoraModal: document.getElementById("btnCloseLoraModal"),
    btnDoneLoraModal: document.getElementById("btnDoneLoraModal"),
    recommendedLorasList: document.getElementById("recommendedLorasList"),
    inputCustomLoraRepo: document.getElementById("inputCustomLoraRepo"),
    inputCustomLoraFile: document.getElementById("inputCustomLoraFile"),
    btnDownloadCustomLora: document.getElementById("btnDownloadCustomLora"),

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
