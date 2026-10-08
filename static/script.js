// script.js - the browser side of Roger.
// It records your voice, talks to the Flask backend, shows messages and plays Roger's audio.
// No API keys are here: the browser only ever talks to our own Flask server.

const app = document.getElementById("app");
const statusEl = document.getElementById("status");
const micBtn = document.getElementById("micBtn");
const cancelBtn = document.getElementById("cancelBtn");
const messagesEl = document.getElementById("messages");
const composer = document.getElementById("composer");
const textInput = document.getElementById("textInput");
const toast = document.getElementById("toast");
const settingsDialog = document.getElementById("settings");
const autoplayBox = document.getElementById("autoplay");

// ---------- State ----------
const STATUS_TEXT = {
  idle: "Ready",
  listening: "Listening...",
  thinking: "Thinking...",
  speaking: "Roger is speaking...",
};
let state = "idle";
let stream = null;
let recorder = null;
let chunks = [];
let cancelled = false;
let pressStart = 0;
let currentAudio = null;
let abortController = null;
let typingEl = null;
let toastTimer = null;

// Settings are remembered in this browser only.
let autoplay = localStorage.getItem("rogerAutoplay") !== "false";
autoplayBox.checked = autoplay;

function setState(next) {
  state = next;
  app.dataset.state = next;
  statusEl.textContent = STATUS_TEXT[next];
  micBtn.classList.toggle("recording", next === "listening");
  cancelBtn.hidden = next === "idle";
  cancelBtn.textContent = next === "speaking" ? "Stop" : "Cancel";
}

// ---------- Messages ----------
function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.textContent = text; // textContent keeps user text safe from HTML injection
  messagesEl.appendChild(div);
  scrollDown();
}

function showTyping() {
  typingEl = document.createElement("div");
  typingEl.className = "msg roger typing";
  typingEl.innerHTML = "<i></i><i></i><i></i>";
  messagesEl.appendChild(typingEl);
  scrollDown();
}

function hideTyping() {
  if (typingEl) typingEl.remove();
  typingEl = null;
}

function scrollDown() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showError(message) {
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toast.hidden = true), 6000);
}

// ---------- Talking to the backend ----------
async function callBackend(url, options) {
  abortController = new AbortController();
  const res = await fetch(url, { ...options, signal: abortController.signal });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Something went wrong. Please try again.");
  return data;
}

async function sendText(text) {
  setState("thinking");
  showTyping();
  try {
    const data = await callBackend("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    handleReply(data);
  } catch (err) {
    handleFailure(err);
  }
}

async function sendVoice(blob) {
  setState("thinking");
  showTyping();
  const form = new FormData();
  const ext = blob.type.includes("mp4") ? "mp4" : blob.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", blob, "recording." + ext);
  try {
    const data = await callBackend("/api/voice", { method: "POST", body: form });
    handleReply(data);
  } catch (err) {
    handleFailure(err);
  }
}

function handleReply(data) {
  hideTyping();
  addMessage("user", data.user_text);
  addMessage("roger", data.reply);
  if (data.warning) showError(data.warning);
  if (data.audio_url && autoplay) playAudio(data.audio_url);
  else setState("idle");
}

function handleFailure(err) {
  hideTyping();
  if (err.name === "AbortError") return; // the user pressed Cancel
  addMessage("error", err.message === "Failed to fetch"
    ? "Can't reach the Roger server. Is `python app.py` still running?"
    : err.message);
  setState("idle");
}

// ---------- Audio playback ----------
function playAudio(url) {
  stopAudio();
  currentAudio = new Audio(url);
  currentAudio.onplay = () => setState("speaking");
  currentAudio.onended = () => setState("idle");
  currentAudio.onerror = () => { showError("Couldn't play Roger's audio."); setState("idle"); };
  currentAudio.play().catch(() => {
    showError("Your browser blocked audio. Tap the mic once, then try again.");
    setState("idle");
  });
}

function stopAudio() {
  if (currentAudio) {
    currentAudio.onended = currentAudio.onerror = currentAudio.onplay = null;
    currentAudio.pause();
    currentAudio = null;
  }
}

// ---------- Recording ----------
function micErrorMessage(err) {
  if (err.name === "NotAllowedError" || err.name === "SecurityError")
    return "Microphone access was blocked. Click the lock icon in the address bar, allow the microphone, then reload.";
  if (err.name === "NotFoundError") return "No microphone found. Plug one in and try again.";
  if (err.name === "NotReadableError") return "Your microphone is busy in another app. Close it and try again.";
  return "Couldn't start the microphone: " + err.message;
}

async function startRecording() {
  if (state !== "idle") return;
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    showError("This browser can't record audio. Open http://localhost:5000 in Chrome, Edge, Firefox or Safari.");
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    showError(micErrorMessage(err));
    return;
  }
  chunks = [];
  cancelled = false;
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  recorder.onstop = onRecordingStopped;
  recorder.start();
  pressStart = Date.now();
  setState("listening");
}

function stopRecording() {
  if (recorder && recorder.state === "recording") recorder.stop();
}

function onRecordingStopped() {
  stream.getTracks().forEach((t) => t.stop()); // turns the mic light off
  if (cancelled) { setState("idle"); return; }
  const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
  if (blob.size < 1000) {
    showError("That was too short. Hold the mic a little longer.");
    setState("idle");
    return;
  }
  sendVoice(blob);
}

// Hold to talk: press, speak, release. Quick tap: starts recording; tap again to send.
micBtn.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  if (state === "listening") stopRecording();
  else startRecording();
});
micBtn.addEventListener("pointerup", () => {
  if (state === "listening" && Date.now() - pressStart > 600) stopRecording(); // it was a hold
});
micBtn.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    if (state === "listening") stopRecording();
    else startRecording();
  }
});

cancelBtn.addEventListener("click", () => {
  if (state === "listening") { cancelled = true; stopRecording(); }
  else if (state === "thinking") { if (abortController) abortController.abort(); hideTyping(); setState("idle"); }
  else if (state === "speaking") { stopAudio(); setState("idle"); }
});

// ---------- Typed messages ----------
composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = textInput.value.trim();
  if (!text || state !== "idle") return;
  textInput.value = "";
  sendText(text);
});

// ---------- Settings ----------
document.getElementById("settingsBtn").addEventListener("click", () => settingsDialog.showModal());
document.getElementById("closeSettings").addEventListener("click", () => settingsDialog.close());
autoplayBox.addEventListener("change", () => {
  autoplay = autoplayBox.checked;
  localStorage.setItem("rogerAutoplay", autoplay);
});
document.getElementById("clearBtn").addEventListener("click", async () => {
  try { await fetch("/api/reset", { method: "POST" }); } catch (e) { /* ignore */ }
  messagesEl.innerHTML = "";
  addMessage("roger", "Fresh start. What's on your mind?");
  settingsDialog.close();
});

// ---------- Online status ----------
async function checkHealth() {
  const box = document.getElementById("online");
  const label = document.getElementById("onlineText");
  try {
    const h = await (await fetch("/api/health")).json();
    if (h.openai && h.elevenlabs) { box.className = "online ok"; label.textContent = "Online"; }
    else { box.className = "online warn"; label.textContent = "Missing API key"; showError("An API key is missing from your .env file. Check the variable names."); }
  } catch (e) {
    box.className = "online off";
    label.textContent = "Offline";
  }
}

// ---------- Start ----------
addMessage("roger", "Hey, I'm Roger. Hold the mic and talk to me, or just type.");
checkHealth();
