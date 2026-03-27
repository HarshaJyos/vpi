# core_voice.py - RELIABLE VERSION (gTTS + aplay - No Piper issues)
import asyncio
import os
import tempfile
import time
import subprocess
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from gtts import gTTS

load_dotenv()

# Global variables
client = None
conversation_history = []
is_listening = False
voice_task = None

# ============== SETTINGS ==============
SILENCE_THRESHOLD = 0.005
SILENCE_DURATION = 1.6
SAMPLE_RATE = 44100
# =====================================

def init_client():
    global client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY missing in .env!")
        return False
    try:
        client = genai.Client(api_key=api_key)
        print("✅ Gemini client initialized")
        return True
    except Exception as e:
        print(f"❌ Gemini init failed: {e}")
        return False

SYSTEM_INSTRUCTION = """
You are Aria, a warm, caring, emotionally intelligent female voice assistant.
Respond naturally in Telugu if the user speaks in Telugu, otherwise in English.
Keep responses short, natural and friendly (1-3 sentences maximum).
"""

async def play_response(text):
    """Reliable playback using gTTS + aplay (best for your 3.5mm jack)"""
    print(f"[TTS] Aria: {text}")
    
    mp3_file = tempfile.mktemp(suffix=".mp3")
    wav_file = tempfile.mktemp(suffix=".wav")
    
    try:
        # 1. Generate with gTTS (supports Telugu well)
        lang = 'te' if any(ord(c) > 127 for c in text) else 'en'
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(mp3_file)
        print("[TTS] gTTS generated audio")

        # 2. Convert MP3 to WAV (clean for aplay)
        subprocess.run([
            "ffmpeg", "-i", mp3_file, 
            "-ar", "22050", "-ac", "1", "-y", wav_file
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # 3. Play with aplay - most reliable method
        print("[TTS] Playing through 3.5mm jack...")
        subprocess.run([
            "aplay",
            "-D", "plughw:2,0",      # Your 3.5mm jack
            "-f", "S16_LE",
            "-c", "1",
            "-r", "22050",
            wav_file
        ], check=True, timeout=30)

        print("[TTS] Playback finished successfully")

    except subprocess.CalledProcessError as e:
        print(f"[TTS] aplay failed: {e}")
        # Emergency fallback with pygame
        try:
            import pygame
            pygame.mixer.music.load(mp3_file)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            print("[TTS] Fallback pygame playback done")
        except Exception as fallback_e:
            print(f"[TTS] All playback methods failed: {fallback_e}")
    except Exception as e:
        print(f"[TTS] Error: {e}")
    finally:
        time.sleep(0.4)
        for f in [mp3_file, wav_file]:
            try:
                os.unlink(f)
            except:
                pass


class DynamicRecorder:
    def __init__(self):
        self.audio_buffer = []
        self.silence_counter = 0
        self.is_speaking = False

    def callback(self, indata, frames, time_info, status):
        if status:
            print(f"[Audio] {status}")
        audio_chunk = np.frombuffer(indata, dtype=np.float32)
        energy = np.sqrt(np.mean(audio_chunk ** 2))

        if energy > SILENCE_THRESHOLD:
            self.audio_buffer.extend(audio_chunk.tolist())
            if not self.is_speaking:
                print("🔊 Speech started")
            self.is_speaking = True
            self.silence_counter = 0
        else:
            if self.is_speaking:
                self.silence_counter += 0.1
                self.audio_buffer.extend(audio_chunk.tolist())
                if self.silence_counter >= SILENCE_DURATION:
                    print("🔇 Silence detected - ending recording")
                    self.is_speaking = False
                    raise sd.CallbackStop()

    async def record_until_silence(self):
        print("\n🎤 Listening... Speak now")
        self.audio_buffer = []
        self.silence_counter = 0
        self.is_speaking = False

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32',
                                blocksize=0, callback=self.callback):
                while (self.is_speaking or len(self.audio_buffer) == 0) and is_listening:
                    await asyncio.sleep(0.1)
        except sd.CallbackStop:
            pass
        except Exception as e:
            print(f"[RECORD] Stream error: {e}")

        duration = len(self.audio_buffer) / SAMPLE_RATE
        print(f"[RECORD] Finished - Duration: {duration:.2f}s")

        if duration < 0.6:
            print("⚠️ Too short - ignored")
            return None

        audio_array = np.array(self.audio_buffer, dtype=np.float32)
        audio_int16 = (audio_array * 32767).astype(np.int16)

        audio_file = tempfile.mktemp(suffix=".wav")
        from scipy.io.wavfile import write
        write(audio_file, SAMPLE_RATE, audio_int16)

        print(f"✅ Recorded {duration:.1f}s → Sending to Gemini")
        return audio_file


async def continuous_voice_loop():
    global conversation_history
    print("=== Aria Dynamic Voice Assistant STARTED (Reliable) ===")
    print(f"Sample Rate: {SAMPLE_RATE}Hz")
    print("="*60)

    while is_listening:
        audio_file = None
        try:
            audio_file = await DynamicRecorder().record_until_silence()
            if not audio_file or not is_listening:
                continue

            with open(audio_file, "rb") as f:
                audio_bytes = f.read()

            conversation_history.append(types.Content(
                role="user",
                parts=[types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")]
            ))
            if len(conversation_history) > 12:
                conversation_history = conversation_history[-12:]

            if not client:
                continue

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=conversation_history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.75,
                    max_output_tokens=220
                )
            )

            text_response = response.text.strip() or "Sorry, I didn't catch that."
            print(f"[GEMINI] Response: {text_response[:100]}...")

            conversation_history.append(types.Content(
                role="model",
                parts=[types.Part.from_text(text=text_response)]
            ))

            await play_response(text_response)

        except Exception as e:
            print(f"[LOOP] Error: {e}")
        finally:
            if audio_file and os.path.exists(audio_file):
                try:
                    os.unlink(audio_file)
                except:
                    pass

    print("=== Aria Dynamic Voice Assistant STOPPED ===")