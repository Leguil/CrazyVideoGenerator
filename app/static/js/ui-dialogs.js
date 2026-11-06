// Author: François Guillemette
/**
 * CrazyVideoGenerator — Custom Dialogs, Toast Notifications, and Theme Management
 */

import { el, escapeHtml } from "./state.js";

let dialogResolve = null;

export function showToast(message, type = "info") {
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

export function showAppDialog({
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

export function closeAppDialog(result) {
    el.appDialogModal.classList.add("hidden");
    if (dialogResolve) {
        const cb = dialogResolve;
        dialogResolve = null;
        cb(result);
    }
}

export function setTheme(theme) {
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

export function initTheme() {
    const stored = localStorage.getItem("crazylogix_theme") || "dark";
    setTheme(stored);
    el.themeToggleBtn.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
        setTheme(current);
    });
}
