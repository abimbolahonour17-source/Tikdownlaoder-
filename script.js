const form = document.querySelector("#download-form");
const input = document.querySelector("#video-url");
const status = document.querySelector("#url-status");
const pasteButton = document.querySelector("#paste-button");
const submitButton = document.querySelector("#download-button");
const menuButton = document.querySelector(".menu-toggle");
const nav = document.querySelector(".nav-links");

document.querySelector("#year").textContent = new Date().getFullYear();

function showStatus(message, kind = "") {
  status.textContent = message;
  status.className = "status-message" + (kind ? " " + kind : "");
}

function isTikTokUrl(value) {
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase().replace(/^www\./, "");
    const allowedHosts = ["tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"];
    return parsed.protocol === "https:" && allowedHosts.some((allowed) => host === allowed || host.endsWith("." + allowed));
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
    showStatus("Clipboard access isn't available. Paste your link into the field manually.");
  }
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const value = input.value.trim();
  if (!value) {
    showStatus("Paste a TikTok video link to continue.", "error");
    input.focus();
    return;
  }
  if (!isTikTokUrl(value)) {
    showStatus("Please enter a valid HTTPS TikTok link.", "error");
    input.focus();
    return;
  }

  // The frontend is ready for API integration. No download endpoint is configured yet.
  showStatus("Link looks valid. Video processing is not connected yet—this is the website preview.", "success");
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
