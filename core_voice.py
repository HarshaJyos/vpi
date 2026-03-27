# core_voice.py - IMPROVED SMOOTH VOICE VERSION
import asyncio
import os
import tempfile
import time
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from google import genai
from google.genai import types
import edge_tts
import pygame
import pyttsx3
import piper

load_dotenv()

# Load Piper once at module level (add near the top after imports)
piper_voice = None

# Global shared variables
client = None
conversation_history = []
is_listening = False
voice_task = None

pygame.mixer.init()
pygame.mixer.music.set_volume(0.92)   # Slightly higher for clarity

# Initialize pyttsx3 once at the top (after pygame.init())
engine = pyttsx3.init()
engine.setProperty('rate', 160)      # Speed (140-180 is good)
engine.setProperty('volume', 0.95)

# ============== TUNABLE SETTINGS ==============
SILENCE_THRESHOLD = 0.004      # Adjust based on your mic (0.002 to 0.006)
SILENCE_DURATION = 1.8
CHUNK_DURATION = 0.3
SAMPLE_RATE = 16000
CHANNELS = 1
# ============================================
def init_piper():
    global piper_voice
    try:
        model_path = os.path.expanduser("~/piper-voices/en_US-lessac-medium.onnx")
        config_path = os.path.expanduser("~/piper-voices/en_US-lessac-medium.onnx.json")
        
        piper_voice = piper.PiperVoice.load(model_path, config_path)
        print("✅ Piper TTS initialized with natural voice (lessac-medium)")
        return True
    except Exception as e:
        print(f"❌ Piper init failed: {e}")
        return False
    
    
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

async def play_response(text):
    """Natural human-like voice using Piper TTS"""
    print(f"[TTS] Aria: {text}")
    
    global piper_voice
    if piper_voice is None:
        if not init_piper():
            # Fallback to gTTS if Piper fails
            await fallback_gtts(text)
            return

    audio_file = tempfile.mktemp(suffix=".wav")
    
    try:
        # Generate audio with Piper
        with open(audio_file, "wb") as f:
            piper_voice.synthesize(text, f)
        
        print("[TTS] Audio generated with Piper")
        
        # Play with pygame
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
            
        print("[TTS] Playback finished")
        
    except Exception as e:
        print(f"[TTS] Piper error: {e}")
        await fallback_gtts(text)
    finally:
        time.sleep(0.4)
        try:
            os.unlink(audio_file)
        except:
            pass
        
def fallback_gtts(text):
    """Original gTTS fallback"""
    from gtts import gTTS
    tts = gTTS(text=text, lang='te' if any(ord(c) > 127 for c in text) else 'en', slow=False)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        mp3_path = tmp.name
        tts.save(mp3_path)
    
    try:
        pygame.mixer.music.load(mp3_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except Exception as e:
        print(f"Fallback playback error: {e}")
    finally:
        time.sleep(0.4)
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

        if len(self.audio_buffer) % 80 == 0:   # Reduce spam
            print(f"[Audio] Energy: {energy:.5f} | Max: {self.max_energy_seen:.5f} | Speaking: {self.is_speaking}")

        if energy > SILENCE_THRESHOLD:
            self.audio_buffer.extend(audio_chunk.tolist())
            if not self.is_speaking:
                print("🔊 SPEECH STARTED")
            self.is_speaking = True
            self.silence_counter = 0
        else:
            if self.is_speaking:
                self.silence_counter += CHUNK_DURATION
                self.audio_buffer.extend(audio_chunk.tolist())

                if self.silence_counter >= SILENCE_DURATION:
                    print(f"🔇 Silence detected → Ending recording")
                    self.is_speaking = False
                    raise sd.CallbackStop()
            else:
                if len(self.audio_buffer) < 12000:
                    self.audio_buffer.extend(audio_chunk.tolist())

    async def record_until_silence(self):
        print("\n🎤 Listening... Speak naturally")
        self.audio_buffer = []
        self.silence_counter = 0
        self.is_speaking = False
        self.max_energy_seen = 0.0

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, 
                                dtype='float32', blocksize=int(SAMPLE_RATE * CHUNK_DURATION),
                                callback=self.callback):
                while (self.is_speaking or len(self.audio_buffer) == 0) and is_listening:
                    await asyncio.sleep(0.05)
        except sd.CallbackStop:
            pass
        except Exception as e:
            print(f"[RECORD] Stream error: {e}")

        duration = len(self.audio_buffer) / SAMPLE_RATE
        print(f"[RECORD] Finished - Duration: {duration:.2f}s | Max Energy: {self.max_energy_seen:.5f}")

        if duration < 0.7:
            print("⚠️ Too short - ignored")
            return None

        # Save WAV
        audio_array = np.array(self.audio_buffer, dtype=np.float32)
        audio_array = np.clip(audio_array, -1.0, 1.0)
        audio_int16 = (audio_array * 32767).astype(np.int16)

        audio_file = tempfile.mktemp(suffix=".wav")
        from scipy.io.wavfile import write
        write(audio_file, SAMPLE_RATE, audio_int16)

        print(f"✅ Recorded {duration:.1f}s audio → Sending to Gemini")
        return audio_file


async def continuous_voice_loop():
    global conversation_history
    print("=== Aria Dynamic Voice Assistant STARTED ===")
    print(f"Threshold: {SILENCE_THRESHOLD} | Silence: {SILENCE_DURATION}s")
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

            text_response = response.text.strip() if response.text else "Sorry, I didn't catch that."
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