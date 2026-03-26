import asyncio
import os
import wave
import tempfile
import time
from dotenv import load_dotenv

import pyaudio
from google import genai
from google.genai import types
from gtts import gTTS
import pygame   # pip install pygame  -- much better playback control

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY missing in .env!")
    exit(1)

client = genai.Client(api_key=API_KEY)

SYSTEM_INSTRUCTION = """
You are Aria, a warm, caring, emotionally intelligent female voice assistant.
- Carefully detect the user's emotion from voice tone (happy, sad, frustrated, excited, lonely, angry, tired, etc.).
- Respond with matching empathy, warmth, and natural feminine tone.
- Sound like a supportive friend — be concise, friendly, and conversational.
"""

pygame.mixer.init()

async def record_audio(seconds=6):
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
    print(f"🎤 Recording {seconds}s... Speak with real emotion now!")
    
    frames = [stream.read(1024, exception_on_overflow=False) for _ in range(int(16000 / 1024 * seconds))]
    
    stream.stop_stream()
    stream.close()
    p.terminate()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wf = wave.open(tmp.name, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b''.join(frames))
        wf.close()
        return tmp.name

def play_response(text):
    print(f"Aria: {text}")
    tts = gTTS(text=text, lang='en', slow=False)
    
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        mp3_path = tmp.name
        tts.save(mp3_path)
    
    try:
        pygame.mixer.music.load(mp3_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    finally:
        pygame.mixer.music.stop()
        time.sleep(0.2)  # small delay to release handle
        try:
            os.unlink(mp3_path)
        except:
            pass

async def main():
    print("=== Stable Hybrid Voice Assistant (Fixed Playback + 503 Retry) ===")
    print("Ctrl+C to quit\n")

    while True:
        audio_file = None
        try:
            audio_file = await record_audio(6)

            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=SYSTEM_INSTRUCTION),
                        types.Part.from_bytes(
                            data=open(audio_file, "rb").read(),
                            mime_type="audio/wav"
                        )
                    ]
                )
            ]

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.75,
                    max_output_tokens=280
                )
            )

            text_response = response.text.strip() if response.text else "Sorry, I didn't understand. Can you repeat?"
            play_response(text_response)

        except Exception as e:
            error_str = str(e).lower()
            if "503" in error_str or "unavailable" in error_str:
                print("503 - Google servers overloaded. Waiting 10 seconds...")
                await asyncio.sleep(10)
            else:
                print(f"Error: {e}")
                await asyncio.sleep(2)
        finally:
            if audio_file and os.path.exists(audio_file):
                try:
                    os.unlink(audio_file)
                except:
                    pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Stopped by user.")
    except Exception as e:
        print(f"Crash: {e}")