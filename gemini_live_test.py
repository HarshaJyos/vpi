
import asyncio
import os
import tempfile
import time
from dotenv import load_dotenv
import subprocess
from google import genai
from google.genai import types
from gtts import gTTS
import pygame

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY missing in .env!")
    exit(1)

client = genai.Client(api_key=API_KEY)

SYSTEM_INSTRUCTION = """
You are Aria, a warm, caring, emotionally intelligent female voice assistant.
Detect the user's emotion from voice tone and respond with matching empathy and warmth.
Keep responses short, natural and friendly (1-3 sentences maximum).
"""

pygame.mixer.init()
pygame.mixer.music.set_volume(0.85)   # Slightly lower volume to reduce distortion

async def record_audio():
    print("🎤 Recording with arecord (USB Mic card 3)... Speak now!")
    audio_file = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run([
            "arecord", "-D", "plughw:3,0",
            "-f", "S16_LE", "-c", "1", "-r", "44100",
            "-d", "8", "-q", audio_file
        ], check=True, timeout=10)
        print("   [Recording finished]")
        return audio_file
    except Exception as e:
        print(f"   Recording error: {e}")
        return None

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
    except Exception as e:
        print(f"Playback error: {e}")
    finally:
        time.sleep(0.4)   # Extra delay to release file
        try:
            os.unlink(mp3_path)
        except:
            pass

async def main():
    print("=== Aria Voice Assistant - Clean & Stable Version ===")
    print("USB Mic (card 3) → Gemini → 3.5mm Jack")
    print("Ctrl+C to stop\n")

    history = []

    while True:
        audio_file = None
        try:
            audio_file = await record_audio()
            if not audio_file:
                await asyncio.sleep(1)
                continue

            with open(audio_file, "rb") as f:
                audio_bytes = f.read()

            history.append(types.Content(
                role="user",
                parts=[types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")]
            ))

            if len(history) > 10:
                history = history[-10:]

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7,
                    max_output_tokens=180
                )
            )

            text_response = response.text.strip() if response.text else "Sorry, I didn't catch that."
            
            history.append(types.Content(
                role="model",
                parts=[types.Part.from_text(text=text_response)]
            ))

            play_response(text_response)

        except Exception as e:
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
