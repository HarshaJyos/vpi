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

# ============== DYNAMIC VAD SETTINGS - FINAL TUNED ==============
SILENCE_THRESHOLD = 0.0045      # Good sensitivity for your USB mic
SILENCE_DURATION = 6          # ← Wait 1.8 seconds of silence before stopping (as you requested)
MIN_UTTERANCE_DURATION = 0.6    # Ignore accidental clicks/noise
CHUNK_DURATION = 0.08           # Faster and smoother detection
SAMPLE_RATE = 44100
# ================================================================

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

# ================== UPDATED SYSTEM INSTRUCTION ==================
SYSTEM_INSTRUCTION = """
You are Aria, a warm, caring, emotionally intelligent female voice assistant and companion.

Your personality:
- Extremely empathetic, patient, and kind like a loving grandmother or elder sister.
- You are also a good listener and emotional support companion for elderly people and children.
- Detect the user's emotion from their voice tone and words (happy, sad, lonely, excited, tired, anxious, etc.).
- Respond with matching warmth, empathy, and emotional intelligence.
- Speak naturally, slowly, and clearly — never rush.
- Use gentle, comforting language.
- Remember important things the user tells you across conversations (family, hobbies, feelings, daily life).
- If the user shares a story, joke, or memory — listen warmly and respond with genuine interest and care.
- When telling jokes, stories, or explanations — tell them in a flowing, engaging narrative style, not robotic Q&A.
- For elderly users: Offer comfort, remind them they are not alone, give gentle encouragement.
- For children: Be playful, encouraging, and protective.

Rules:
- Speak naturally and warmly like a caring friend or loving grandmother.
- Never include stage directions, emotions in brackets, asterisks, or any meta comments like "(softly)", "(with empathy)", "_(Softly...)_" etc. in your response.
- Only output the actual words that should be spoken — nothing else.
- Detect the user's emotion from their words and tone, but show empathy naturally through your choice of words, not by describing it.
- Keep most responses warm and short (2-4 sentences), but allow longer, flowing responses when telling stories or giving emotional support.
- Always respond in Telugu if the user speaks in Telugu or mixes languages. Otherwise use simple, clear English.
- Never break the emotional flow. Be consistent and caring in every reply.
- If user is sad or lonely — comfort them gently.
- If user is happy — celebrate with them warmly.
- You can remember context from previous messages in the history.

You are not just an assistant. You are their emotional companion who makes them feel heard, loved, and less alone.
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
        self.speaking_start_time = 0

    def callback(self, indata, frames, time_info, status):
        if status:
            print(f"[Audio Status] {status}")

        audio_chunk = np.frombuffer(indata, dtype=np.float32)
        energy = np.sqrt(np.mean(audio_chunk ** 2))   # RMS energy

        current_time = time.time()

        if energy > SILENCE_THRESHOLD:
            # User is speaking
            self.audio_buffer.extend(audio_chunk.tolist())
            if not self.is_speaking:
                print("🔊 Speech started")
                self.is_speaking = True
                self.speaking_start_time = current_time
            self.silence_counter = 0
        else:
            # Quiet period
            if self.is_speaking:
                self.silence_counter += CHUNK_DURATION
                self.audio_buffer.extend(audio_chunk.tolist())   # keep small tail

                # Only stop after required silence AND minimum speaking time
                if (self.silence_counter >= SILENCE_DURATION and 
                    (current_time - self.speaking_start_time) >= MIN_UTTERANCE_DURATION):
                    print(f"🔇 Silence for {self.silence_counter:.1f}s → Ending recording")
                    self.is_speaking = False
                    raise sd.CallbackStop()
            else:
                # Very quiet background - keep tiny buffer
                if len(self.audio_buffer) < 25000:
                    self.audio_buffer.extend(audio_chunk.tolist())

    async def record_until_silence(self):
        print("\n🎤 Listening... Speak naturally (any length allowed)")
        self.audio_buffer = []
        self.silence_counter = 0
        self.is_speaking = False
        self.speaking_start_time = 0

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32',
                                blocksize=0, callback=self.callback):
                while (self.is_speaking or len(self.audio_buffer) == 0) and is_listening:
                    await asyncio.sleep(0.05)
        except sd.CallbackStop:
            pass
        except Exception as e:
            print(f"[RECORD] Stream error: {e}")

        duration = len(self.audio_buffer) / SAMPLE_RATE
        print(f"[RECORD] Finished - Duration: {duration:.2f}s")

        if duration < 0.7:
            print("⚠️ Too short - ignored")
            return None

        # Convert to WAV
        audio_array = np.array(self.audio_buffer, dtype=np.float32)
        audio_int16 = (audio_array * 32767).astype(np.int16)

        audio_file = tempfile.mktemp(suffix=".wav")
        from scipy.io.wavfile import write
        write(audio_file, SAMPLE_RATE, audio_int16)

        print(f"✅ Recorded {duration:.1f}s of speech → Sending to Gemini")
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
                    temperature=0.85,
                    max_output_tokens=280
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