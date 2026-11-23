const form = document.querySelector("#download-form");
const input = document.querySelector("#video-url");
const status = document.querySelector("#url-status");
const pasteButton = document.querySelector("#paste-button");
const submitButton = document.querySelector("#download-button");
const fileInput = document.querySelector("#video-file");
const uploadButton = document.querySelector("#upload-button");
const uploadStatus = document.querySelector("#upload-status");
const fileDownloadLink = document.querySelector("#file-download-link");
const processButton = document.querySelector("#process-button");
const processStatus = document.querySelector("#process-status");
const operationSelect = document.querySelector("#video-operation");
const resolutionSelect = document.querySelector("#video-resolution");
let uploadedMediaId = null;
const menuButton = document.querySelector(".menu-toggle");
const nav = document.querySelector(".nav-links");

document.querySelector("#year").textContent = new Date().getFullYear();

const API_BASE = (window.TIKDOWNLOAD_API_BASE || "").replace(/\/$/, "");
const MAX_UPLOAD_MB = 80;

function showStatus(message, kind = "") {
  status.textContent = message;
  status.className = "status-message" + (kind ? " " + kind : "");
}

function showProcessStatus(message, kind = "") {\n  processStatus.textContent = message;\n  processStatus.className = "status-message" + (kind ? " " + kind : "");\n}\n\nfunction showUploadStatus(message, kind = "") {
  uploadStatus.textContent = message;
  uploadStatus.className = "status-message" + (kind ? " " + kind : "");
}

function isTikTokUrl(value) {
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase();
    const allowedHosts = ["tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"];
    return parsed.protocol === "https:" && allowedHosts.includes(host) && parsed.pathname.length > 1;
  } catch {
    return false;
  }
}

input.addEventListener("input", () => showStatus(""));

pasteButton.addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (!text) {
      showStatus("Your clipboard is empty. Copy a video link first.", "error");
      return;
    }
    input.value = text.trim();
    input.focus();
    showStatus("Link pasted. Check it before continuing.", "success");
  } catch {
    input.focus();
    showStatus("Clipboard access isn't available. Paste your link into the field manually");
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = input.value.trim();
  if (!value) {
    showStatus("Paste a TikTok video link to continue.", "error");
    input.focus();
    return;
  }
  if (!isTikTokUrl(value)) {
    showStatus("Please enter a valid HTTPS TikTok video link.", "error");
    input.focus();
    return;
  }

  submitButton.disabled = true;
  submitButton.querySelector(".button-label").textContent = "Checking link…";
  showStatus("Checking link with TikDownload API…");

  try {
    const response = await fetch(`${API_BASE}/api/v1/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: value }),
    });
    if (!response.ok) throw new Error("API request failed");
    const result = await response.json();
    if (result.valid) {
      showStatus("Link format validated. TikTok retrieval is not connected; use the file-upload tool below for videos you have.", "success");
    } else {
      showStatus(result.message || "This link is not supported.", "error");
    }
  } catch {
    showStatus("TikDownload API is unavailable. The link format looks okay, but server validation couldn't be reached.", "error");
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector(".button-label").textContent = "Check link";
  }
});

uploadButton.addEventListener("click", async () => {
  const file = fileInput.files?.[0];
  fileDownloadLink.hidden = true;
  if (!file) {
    showUploadStatus("Choose a video file first.", "error");
    return;
  }
  const allowedTypes = ["video/mp4", "video/webm", "video/quicktime"];
  if (!allowedTypes.includes(file.type)) {
    showUploadStatus("Choose an MP4, WebM, or MOV video.", "error");
    return;
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    showUploadStatus(`This file is larger than ${MAX_UPLOAD_MB} MB.`, "error");
    return;
  }
  uploadButton.disabled = true;
  uploadButton.querySelector(".button-label").textContent = "Uploading…";
  showUploadStatus("Uploading your file securely. Please keep this page open.");
  try {
    const data = new FormData();
    data.append("file", file);
    const response = await fetch(`${API_BASE}/api/v1/media/upload`, { method: "POST", body: data });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Upload failed");
    fileDownloadLink.href = `${API_BASE}${result.download_url}`;
    fileDownloadLink.textContent = "Download your video ↓";
    fileDownloadLink.hidden = false;
    showUploadStatus("Your video is ready. Download it using the link below.", "success");
  } catch (error) {
    showUploadStatus(typeof error.message === "string" ? error.message : "Upload failed. Please try again.", "error");
  } finally {
    uploadButton.disabled = false;
    uploadButton.querySelector(".button-label").textContent = "Upload and prepare download";
  }
});

processButton.addEventListener("click", async () => {
  if (!uploadedMediaId) {
    showProcessStatus("Upload a video before processing.", "error");
    return;
  }
  processButton.disabled = true;
  processButton.querySelector(".button-label").textContent = "Processing…";
  showProcessStatus("FFmpeg is processing your video. This can take a few minutes.");
  try {
    const params = new URLSearchParams({ operation: operationSelect.value, resolution: resolutionSelect.value });
    const response = await fetch(`${API_BASE}/api/v1/media/${uploadedMediaId}/process?${params.toString()}`, { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Processing failed");
    fileDownloadLink.href = `${API_BASE}${result.download_url}`;
    fileDownloadLink.textContent = `Download processed video (${result.operation}, ${result.resolution}p) ↓`;
    fileDownloadLink.hidden = false;
    showProcessStatus("Processing complete! Your MP4 is ready to download.", "success");
  } catch (error) {
    showProcessStatus(typeof error.message === "string" ? error.message : "Processing failed. Try another preset.", "error");
  } finally {
    processButton.disabled = false;
    processButton.querySelector(".button-label").textContent = "Process video";
  }
});

menuButton.addEventListener("click", () => {
  const opened = menuButton.getAttribute("aria-expanded") === "true";
  menuButton.setAttribute("aria-expanded", String(!opened));
  document.body.classList.toggle("mobile-nav-open", !opened);
  menuButton.setAttribute("aria-label", opened ? "Open navigation" : "Close navigation");
});

nav.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => {
    document.body.classList.remove("mobile-nav-open");
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.setAttribute("aria-label", "Open navigation");
  });
});
