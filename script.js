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
const progressWrap = document.querySelector("#processing-progress");
const progressFill = document.querySelector("#progress-fill");
const progressLabel = document.querySelector("#progress-label");
const operationSelect = document.querySelector("#video-operation");
const resolutionSelect = document.querySelector("#video-resolution");
let uploadedMediaId = null;
const menuButton = document.querySelector(".menu-toggle");
const nav = document.querySelector(".nav-links");

// Upload/conversion tools are kept for local development until a durable serverless worker is configured.
if (!["localhost", "127.0.0.1"].includes(window.location.hostname)) {
  const uploadPanel = document.querySelector(".authorized-upload");
  if (uploadPanel) uploadPanel.style.display = "none";
}
\ndocument.querySelector("#year").textContent = new Date().getFullYear();
const defaultApiBase = ["localhost", "127.0.0.1"].includes(window.location.hostname) ? "http://127.0.0.1:8000" : window.location.origin;
const API_BASE = (window.TIKDOWNLOAD_API_BASE || defaultApiBase).replace(/\/$/, "");
const MAX_UPLOAD_MB = 80;

function showStatus(message, kind = "") {
  status.textContent = message;
  status.className = "status-message" + (kind ? " " + kind : "");
}
function showUploadStatus(message, kind = "") {
  uploadStatus.textContent = message;
  uploadStatus.className = "status-message" + (kind ? " " + kind : "");
}
function showProcessStatus(message, kind = "") {
  processStatus.textContent = message;
  processStatus.className = "status-message" + (kind ? " " + kind : "");
}
function setProcessingProgress(value) {
  const safe = Math.max(0, Math.min(100, Number(value) || 0));
  progressWrap.hidden = false;
  progressFill.style.width = `${safe}%`;
  progressLabel.textContent = `${safe}%`;
}
function downloadHref(value) {
  try {
    return new URL(value, API_BASE).href;
  } catch {
    return "#";
  }
}
function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes, index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}
async function pollProcessingJob(jobId) {
  const deadline = Date.now() + 15 * 60 * 1000;
  while (Date.now() < deadline) {
    const response = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`);
    const job = await response.json();
    if (!response.ok) throw new Error(job.detail || "Could not check processing status.");
    setProcessingProgress(job.progress);
    showProcessStatus(job.message || "Processing video…");
    if (job.status === "completed") return job;
    if (job.status === "failed") throw new Error(job.message || "Processing failed.");
    await new Promise(resolve => setTimeout(resolve, 850));
  }
  throw new Error("Processing status timed out. Check again later.");
}

function isTikTokUrl(value) {
  try {
    const parsed = new URL(value);
    const allowedHosts = ["tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"];
    return parsed.protocol === "https:" && allowedHosts.includes(parsed.hostname.toLowerCase()) && parsed.pathname.length > 1;
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
    showStatus("Clipboard access isn't available. Paste your link manually.");
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
  submitButton.querySelector(".button-label").textContent = "Retrieving…";
  showStatus("Requesting authorized video retrieval. This may take a moment.");
  try {
    const response = await fetch(`${API_BASE}/api/v1/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: value }),
    });
    const result = await response.json();
    if (!response.ok) {
      const detail = typeof result.detail === "string" ? result.detail : result.detail?.message;
      throw new Error(detail || "Video retrieval is not available.");
    }
    fileDownloadLink.href = downloadHref(result.download_url);
    fileDownloadLink.textContent = `Download ${result.filename || "video"} ↓`;
    fileDownloadLink.hidden = false;
    showStatus(`Video ready (${formatBytes(result.size_bytes)}). Download below.`, "success");
  } catch (error) {
    showStatus(error.message || "Video retrieval failed. Please try again.", "error");
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector(".button-label").textContent = "Download video";
  }
});

uploadButton.addEventListener("click", async () => {
  const file = fileInput.files?.[0];
  fileDownloadLink.hidden = true;
  processButton.disabled = true;
  uploadedMediaId = null;
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
  showUploadStatus("Uploading your video. Keep this page open.");
  try {
    const data = new FormData();
    data.append("file", file);
    const response = await fetch(`${API_BASE}/api/v1/media/upload`, { method: "POST", body: data });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Upload failed");
    uploadedMediaId = result.id;
    processButton.disabled = false;
    fileDownloadLink.href = downloadHref(result.download_url);
    fileDownloadLink.textContent = "Download original upload ↓";
    fileDownloadLink.hidden = false;
    showUploadStatus("Upload complete. Choose conversion or compression options.", "success");
  } catch (error) {
    showUploadStatus(error.message || "Upload failed. Please try again.", "error");
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
  processButton.querySelector(".button-label").textContent = "Queued…";
  fileDownloadLink.hidden = true;
  setProcessingProgress(0);
  showProcessStatus("Preparing background processing job.");
  try {
    const params = new URLSearchParams({ operation: operationSelect.value, resolution: resolutionSelect.value });
    const response = await fetch(`${API_BASE}/api/v1/media/${uploadedMediaId}/process?${params}`, { method: "POST" });
    const queued = await response.json();
    if (!response.ok) throw new Error(typeof queued.detail === "string" ? queued.detail : "Could not start processing");
    const result = await pollProcessingJob(queued.job_id);
    fileDownloadLink.href = `${API_BASE}${result.download_url}`;
    const original = formatBytes(result.original_size_bytes);
    const processed = formatBytes(result.size_bytes);
    const change = result.size_change_bytes;
    const comparison = change <= 0 ? ` — saved ${formatBytes(Math.abs(change))}` : ` — increased by ${formatBytes(change)}`;
    fileDownloadLink.textContent = `Download processed MP4 (${result.operation}, ${result.resolution}) ↓`;
    fileDownloadLink.hidden = false;
    showProcessStatus(`Done! Original: ${original} · Processed: ${processed}${comparison}.`, "success");
  } catch (error) {
    showProcessStatus(error.message || "Processing failed. Try another preset.", "error");
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
