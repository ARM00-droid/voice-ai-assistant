import os
import sounddevice as sd
from scipy.io.wavfile import write
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from openai import OpenAI
import pygame


# ==============================
# LOAD API KEYS
# ==============================

load_dotenv()

elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")


if not elevenlabs_key:
    print("❌ ElevenLabs API key not found!")
    exit()

if not openai_key:
    print("❌ OpenAI API key not found!")
    exit()


# ==============================
# CREATE CLIENTS
# ==============================

elevenlabs = ElevenLabs(
    api_key=elevenlabs_key
)

openai_client = OpenAI(
    api_key=openai_key
)


# ==============================
# SETTINGS
# ==============================

duration = 5
sample_rate = 44100

# Your working microphone
microphone = 1

# Roger voice
voice_id = "CwhRBWXzGAHq8TQ4Fs17"


# ==============================
# CONVERSATION MEMORY
# ==============================

conversation = []


# ==============================
# START ASSISTANT
# ==============================

print("================================")
print("🤖 Roger Voice Assistant")
print("================================")
print("Say 'exit', 'quit', 'stop' or 'goodbye' to close.")
print()


while True:

    # --------------------------
    # RECORD VOICE
    # --------------------------

    print("\n🎤 Start speaking...")

    audio = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        device=microphone
    )

    sd.wait()

    print("✅ Recording finished!")


    # --------------------------
    # SAVE RECORDING
    # --------------------------

    write(
        "audio/recording.wav",
        sample_rate,
        audio
    )

    print("💾 Recording saved!")


    # --------------------------
    # SPEECH TO TEXT
    # --------------------------

    print("🔄 Converting speech to text...")

    try:

        with open("audio/recording.wav", "rb") as audio_file:

            transcription = elevenlabs.speech_to_text.convert(
                file=audio_file,
                model_id="scribe_v2"
            )

        user_text = transcription.text.strip()

    except Exception as e:

        print("❌ Speech recognition error:")
        print(e)

        continue


    print("\n📝 You said:")
    print(user_text)


    # --------------------------
    # CHECK EMPTY INPUT
    # --------------------------

    if not user_text:

        print("⚠️ I couldn't hear you.")

        continue


    # --------------------------
    # EXIT COMMAND
    # --------------------------

    if user_text.lower() in [
        "exit",
        "quit",
        "stop",
        "goodbye"
    ]:

        print("\n👋 Goodbye!")

        break


    # --------------------------
    # ADD USER MESSAGE
    # --------------------------

    conversation.append({
        "role": "user",
        "content": user_text
    })


    # --------------------------
    # AI RESPONSE
    # --------------------------

    print("\n🤖 Thinking...")


    try:

        response = openai_client.responses.create(

            # Keep the model name that worked in your setup
            model="gpt-6-luna",

            instructions="""
You are Roger, a friendly and intelligent voice assistant.

Personality:
- Friendly
- Casual
- Calm
- Helpful
- Natural
- Easy to understand

Rules:
- Keep normal answers reasonably short.
- Do not be unnecessarily formal.
- Explain difficult topics simply.
- When teaching programming or AI/ML, use simple examples.
- Remember the previous conversation.
- Answer naturally like a voice assistant.
""",

            input=conversation
        )


        ai_response = response.output_text


    except Exception as e:

        print("❌ AI error:")
        print(e)

        continue


    # --------------------------
    # SHOW AI RESPONSE
    # --------------------------

    print("\n🤖 Roger:")
    print(ai_response)


    # --------------------------
    # SAVE AI RESPONSE
    # --------------------------

    conversation.append({
        "role": "assistant",
        "content": ai_response
    })


    # --------------------------
    # TEXT TO SPEECH
    # --------------------------

    print("\n🔊 Converting response to speech...")


    try:

        audio_response = elevenlabs.text_to_speech.convert(

            text=ai_response,

            voice_id=voice_id,

            model_id="eleven_multilingual_v2"
        )


        audio_file_path = "audio/response.mp3"


        with open(
            audio_file_path,
            "wb"
        ) as audio_file:

            for chunk in audio_response:

                if chunk:

                    audio_file.write(chunk)


        print("💾 Response audio saved!")


    except Exception as e:

        print("❌ Text-to-speech error:")
        print(e)

        continue


    # --------------------------
    # PLAY AUDIO
    # --------------------------

    print("🔊 Roger is speaking...")


    try:

        pygame.mixer.init()

        pygame.mixer.music.load(
            audio_file_path
        )

        pygame.mixer.music.play()


        while pygame.mixer.music.get_busy():

            pass


        pygame.mixer.quit()


    except Exception as e:

        print("❌ Audio playback error:")
        print(e)

        try:
            pygame.mixer.quit()
        except:
            pass


    print("✅ Ready for next question!")