import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write

sample_rate = 44100
microphone = 1

print("🎤 Waiting for you to speak...")

# Start recording
audio = sd.rec(
    int(10 * sample_rate),
    samplerate=sample_rate,
    channels=1,
    device=microphone
)

sd.wait()

print("✅ Recording finished!")

# Check volume
volume = np.max(np.abs(audio))

print("📊 Audio level:", volume)

if volume < 0.01:
    print("❌ No clear voice detected.")
else:
    print("✅ Voice detected!")

write(
    "audio/test.wav",
    sample_rate,
    audio
)

print("💾 Saved as audio/test.wav")