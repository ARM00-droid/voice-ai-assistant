"""
app.py - the Flask backend for Roger.

The browser talks to this file. This file talks to OpenAI and ElevenLabs.
API keys live ONLY here (loaded from .env) and are never sent to the browser.
"""

import os
import uuid

import openai
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from openai import OpenAI

# ---------------------------------------------------------------------------
# 1. Settings
# ---------------------------------------------------------------------------
load_dotenv()  # reads your .env file

ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
TTS_MODEL = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

SYSTEM_PROMPT = (
    "You are Roger, a personal voice assistant. You are friendly, casual, calm, "
    "helpful, intelligent and natural. Keep replies short (1-3 sentences) because "
    "they will be spoken aloud. Explain technical topics in simple words. "
    "Do not use markdown, bullet points, emojis or code blocks unless asked."
)

app = Flask(__name__)
openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# Conversation memory (kept in RAM; resets when the server restarts).
history = []
MAX_HISTORY = 20  # remember the last 20 messages


class ApiError(Exception):
    """An error with a friendly message we can show in the browser."""

    def __init__(self, message, status=500):
        super().__init__(message)
        self.message = message
        self.status = status


@app.errorhandler(ApiError)
def handle_api_error(err):
    return jsonify({"error": err.message}), err.status


# ---------------------------------------------------------------------------
# 2. Helper functions (one job each)
# ---------------------------------------------------------------------------
def transcribe(audio_bytes, filename, mimetype):
    """Speech-to-text with ElevenLabs scribe_v2. Returns the text."""
    if not ELEVEN_KEY:
        raise ApiError("ELEVENLABS_API_KEY is missing in your .env file.", 500)
    try:
        r = requests.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": ELEVEN_KEY},
            data={"model_id": "scribe_v2"},
            files={"file": (filename, audio_bytes, mimetype)},
            timeout=60,
        )
    except requests.RequestException:
        raise ApiError("Couldn't reach ElevenLabs. Check your internet connection.", 502)
    if r.status_code != 200:
        print("ElevenLabs STT error:", r.status_code, r.text)
        raise ApiError(f"Speech recognition failed (ElevenLabs error {r.status_code}).", 502)
    return r.json().get("text", "").strip()


def ask_roger(user_text):
    """Send the text (plus history) to OpenAI. Returns Roger's reply."""
    if not openai_client:
        raise ApiError("OPENAI_API_KEY is missing in your .env file.", 500)
    history.append({"role": "user", "content": user_text})
    del history[:-MAX_HISTORY]  # keep only the newest messages
    try:
        result = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
        )
    except openai.AuthenticationError:
        history.pop()
        raise ApiError("OpenAI rejected your API key. Check OPENAI_API_KEY in .env.", 502)
    except openai.RateLimitError as e:
        history.pop()
        print("OpenAI error:", e)
        raise ApiError("OpenAI says you're out of quota or sending too fast. Check billing and credits on platform.openai.com.", 502)
    except openai.NotFoundError:
        history.pop()
        raise ApiError(f"OpenAI model '{OPENAI_MODEL}' isn't available to your account. Set OPENAI_MODEL in .env to a model you can use.", 502)
    except Exception as e:  # anything else: the full details are printed in the terminal
        history.pop()  # forget the message that failed
        print("OpenAI error:", e)
        raise ApiError("Roger couldn't think of a reply (OpenAI error). See the terminal for details.", 502)
    reply = (result.choices[0].message.content or "").strip()
    history.append({"role": "assistant", "content": reply})
    return reply


def speak(text):
    """Text-to-speech with ElevenLabs. Saves an mp3 and returns its URL (or None)."""
    if not ELEVEN_KEY:
        return None
    try:
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers={
                "xi-api-key": ELEVEN_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={"text": text, "model_id": TTS_MODEL},
            timeout=60,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        print("ElevenLabs TTS error:", r.status_code, r.text)
        return None

    filename = f"roger_{uuid.uuid4().hex}.mp3"
    with open(os.path.join(AUDIO_DIR, filename), "wb") as f:
        f.write(r.content)
    clean_old_audio()
    return f"/audio/{filename}"


def clean_old_audio(keep=20):
    """Delete old mp3 files so the audio folder doesn't grow forever."""
    files = [os.path.join(AUDIO_DIR, n) for n in os.listdir(AUDIO_DIR) if n.endswith(".mp3")]
    files.sort(key=os.path.getmtime, reverse=True)
    for old in files[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass


def build_response(user_text):
    """Shared by /api/chat and /api/voice."""
    reply = ask_roger(user_text)
    audio_url = speak(reply)
    data = {"user_text": user_text, "reply": reply, "audio_url": audio_url}
    if audio_url is None:
        data["warning"] = "Roger's voice is unavailable right now, so here's the text reply."
    return jsonify(data)


# ---------------------------------------------------------------------------
# 3. Routes (the URLs the browser can call)
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    # Only sends True/False - never the keys themselves.
    return jsonify({"ok": True, "openai": bool(OPENAI_KEY), "elevenlabs": bool(ELEVEN_KEY)})


@app.route("/api/chat", methods=["POST"])
def chat():
    """Typed message in -> reply text + audio out."""
    body = request.get_json(silent=True) or {}
    text = (body.get("message") or "").strip()
    if not text:
        raise ApiError("Please type a message first.", 400)
    return build_response(text)


@app.route("/api/voice", methods=["POST"])
def voice():
    """Recorded audio in -> recognized text + reply text + audio out."""
    audio = request.files.get("audio")
    if not audio:
        raise ApiError("No audio was received.", 400)
    data = audio.read()
    if len(data) < 1000:
        raise ApiError("That recording was too short. Try speaking a bit longer.", 400)
    text = transcribe(data, audio.filename or "recording.webm", audio.mimetype or "audio/webm")
    if not text:
        raise ApiError("I didn't catch that. Could you say it again?", 422)
    return build_response(text)


@app.route("/api/reset", methods=["POST"])
def reset():
    history.clear()
    return jsonify({"ok": True})


@app.route("/audio/<path:filename>")
def get_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
