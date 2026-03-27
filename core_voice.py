# core_voice.py - DEBUG VERSION
import asyncio
import os
import tempfile
import time
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from gtts import gTTS
import pygame

load_dotenv()

# Global shared variables
client = None
conversation_history = []
is_listening = False
voice_task = None

pygame.mixer.init()
pygame.mixer.music.set_volume(0.85)

# ============== TUNABLE SETTINGS ==============
SILENCE_THRESHOLD = 0.004      # Lowered - try 0.002 ~ 0.006
SILENCE_DURATION = 1.8         # seconds of silence to end utterance
CHUNK_DURATION = 0.3           # smaller chunks = more responsive
SAMPLE_RATE = 16000
CHANNELS = 1
# ============================================

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
Keep responses short, natural and friendly (1-3 sentences maximum).
"""

def play_response(text):
    print(f"[TTS] Aria: {text}")
    tts = gTTS(text=text, lang='en', slow=False)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        mp3_path = tmp.name
        tts.save(mp3_path)
    
    try:
        pygame.mixer.music.load(mp3_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        print("[TTS] Playback finished")
    except Exception as e:
        print(f"[TTS] Playback error: {e}")
    finally:
        time.sleep(0.3)
        try:
            os.unlink(mp3_path)
        except:
            pass

class DynamicRecorder:
    def __init__(self):
        self.audio_buffer = []
        self.silence_counter = 0
        self.is_speaking = False
        self.max_energy_seen = 0.0

    def callback(self, indata, frames, time_info, status):
        if status:
            print(f"[Audio] Status: {status}")

        audio_chunk = np.frombuffer(indata, dtype=np.float32)
        energy = np.sqrt(np.mean(audio_chunk ** 2))

        self.max_energy_seen = max(self.max_energy_seen, energy)

        # Debug log every second or so
        if int(time.time()) % 1 == 0 and len(self.audio_buffer) % 50 == 0:
            print(f"[Audio Debug] Energy: {energy:.5f} | Max so far: {self.max_energy_seen:.5f} | Speaking: {self.is_speaking}")

        if energy > SILENCE_THRESHOLD:
            self.audio_buffer.extend(audio_chunk.tolist())
            if not self.is_speaking:
                print("🔊 SPEECH STARTED detected!")
            self.is_speaking = True
            self.silence_counter = 0
        else:
            if self.is_speaking:
                self.silence_counter += CHUNK_DURATION
                self.audio_buffer.extend(audio_chunk.tolist())  # keep tail

                if self.silence_counter >= SILENCE_DURATION:
                    print(f"🔇 Silence detected for {self.silence_counter:.1f}s → Ending recording")
                    self.is_speaking = False
                    raise sd.CallbackStop()
            else:
                # Very quiet - still keep a tiny buffer for context
                if len(self.audio_buffer) < 10000:
                    self.audio_buffer.extend(audio_chunk.tolist())

    async def record_until_silence(self):
        print("\n🎤 [RECORD] Starting dynamic recording... Speak now!")
        self.audio_buffer = []
        self.silence_counter = 0
        self.is_speaking = False
        self.max_energy_seen = 0.0

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, 
                                dtype='float32', 
                                blocksize=int(SAMPLE_RATE * CHUNK_DURATION),
                                callback=self.callback):
                print("[RECORD] InputStream opened successfully")
                while (self.is_speaking or len(self.audio_buffer) == 0) and is_listening:
                    await asyncio.sleep(0.05)
        except sd.CallbackStop:
            print("[RECORD] CallbackStop - Recording ended naturally")
        except Exception as e:
            print(f"[RECORD] Stream error: {e}")

        duration = len(self.audio_buffer) / SAMPLE_RATE
        print(f"[RECORD] Finished. Duration: {duration:.2f}s | Max Energy: {self.max_energy_seen:.5f}")

        if duration < 0.8 or len(self.audio_buffer) < 8000:
            print("⚠️  [RECORD] Too short or silent - ignored")
            return None

        # Save as WAV
        audio_array = np.array(self.audio_buffer, dtype=np.float32)
        audio_array = np.clip(audio_array, -1.0, 1.0)
        audio_int16 = (audio_array * 32767).astype(np.int16)

        audio_file = tempfile.mktemp(suffix=".wav")
        from scipy.io.wavfile import write
        write(audio_file, SAMPLE_RATE, audio_int16)

        print(f"✅ [RECORD] Saved {duration:.1f} seconds of audio → Sending to Gemini")
        return audio_file


async def continuous_voice_loop():
    global conversation_history
    print("=== Aria Dynamic Voice Assistant STARTED (Debug Mode) ===")
    print(f"   Threshold: {SILENCE_THRESHOLD} | Silence: {SILENCE_DURATION}s")
    print("="*60)

    while is_listening:
        # ... rest of your function remains same
        audio_file = None
        try:
            audio_file = await DynamicRecorder().record_until_silence()
            if not audio_file or not is_listening:
                continue

            with open(audio_file, "rb") as f:
                audio_bytes = f.read()

            print(f"[GEMINI] Sending {len(audio_bytes)/1024:.1f} KB audio to Gemini...")
            conversation_history.append(types.Content(
                role="user",
                parts=[types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")]
            ))

            if len(conversation_history) > 12:
                conversation_history = conversation_history[-12:]

            if not client:
                print("[GEMINI] Client not ready")
                continue

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=conversation_history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7,
                    max_output_tokens=200
                )
            )

            text_response = response.text.strip() if response.text else "Sorry, I didn't catch that."
            print(f"[GEMINI] Received response: {text_response[:80]}...")

            conversation_history.append(types.Content(
                role="model",
                parts=[types.Part.from_text(text=text_response)]
            ))

            play_response(text_response)

        except Exception as e:
            print(f"[LOOP] Error in main loop: {e}")
        finally:
            if audio_file and os.path.exists(audio_file):
                try:
                    os.unlink(audio_file)
                except:
                    pass

    print("=== Aria Dynamic Voice Assistant STOPPED ===")