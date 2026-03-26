import asyncio
import os
import sys
from collections import deque
from dotenv import load_dotenv

import pyaudio
from google import genai
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY not found in .env!")
    sys.exit(1)

# Correct model for standard Gemini API key (developer path)
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"   # Most current preview as of March 2026

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 512

SYSTEM_INSTRUCTION = """
You are Aria, a warm, emotionally intelligent FEMALE voice assistant.
- Your voice must be bright, youthful, higher-pitched, smooth, clear, and highly expressive — NEVER deep, male, gravelly, raspy, or low-pitched.
- Always speak with natural feminine prosody, warmth, and emotional tone matching the user.
- Detect the user's emotion (excited, frustrated, sad, happy, tired, angry, etc.) and respond empathetically with matching energy.
- Be concise, conversational, and natural. Allow interruptions.
"""

client = genai.Client(api_key=API_KEY)

class AudioManager:
    def __init__(self):
        self.pya = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        self.audio_queue = deque(maxlen=200)

    async def start_streams(self):
        self.input_stream = await asyncio.to_thread(
            self.pya.open, format=FORMAT, channels=CHANNELS, rate=RATE,
            input=True, frames_per_buffer=CHUNK
        )
        self.output_stream = await asyncio.to_thread(
            self.pya.open, format=FORMAT, channels=CHANNELS, rate=RATE,
            output=True, frames_per_buffer=CHUNK
        )
        print("✅ Audio streams opened (CHUNK=512)")

    def close(self):
        if self.input_stream: self.input_stream.stop_stream(); self.input_stream.close()
        if self.output_stream: self.output_stream.stop_stream(); self.output_stream.close()
        self.pya.terminate()
        print("🛑 Audio closed.")

async def send_audio(session, audio_manager):
    print("🎤 Mic LIVE — speak clearly with emotion now!")
    try:
        while True:
            data = await asyncio.to_thread(
                audio_manager.input_stream.read, CHUNK, exception_on_overflow=False
            )
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
            )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Send error: {e}")

async def receive_audio(session, audio_manager):
    try:
        async for response in session.receive():
            if hasattr(response, 'data') and response.data:
                audio_manager.audio_queue.append(response.data)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Receive error: {e}")

async def play_audio_loop(audio_manager):
    try:
        while True:
            if audio_manager.audio_queue:
                chunk = audio_manager.audio_queue.popleft()
                await asyncio.to_thread(audio_manager.output_stream.write, chunk)
            else:
                await asyncio.sleep(0.001)
    except asyncio.CancelledError:
        pass

async def main():
    VOICE_NAME = "Aoede"   # Try these in order: Aoede, Kore, Leda, Zephyr, Despina

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME)
            )
        ),
        system_instruction=SYSTEM_INSTRUCTION
    )

    audio_manager = AudioManager()
    await audio_manager.start_streams()

    print(f"🔄 Connecting to {MODEL} with voice '{VOICE_NAME}'...")

    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("✅ Connected! Speak emotional sentences now.")
            await asyncio.gather(
                send_audio(session, audio_manager),
                receive_audio(session, audio_manager),
                play_audio_loop(audio_manager),
                return_exceptions=True
            )
    except Exception as e:
        print(f"❌ Session crashed: {e}")
    finally:
        audio_manager.close()
        print("Session ended.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Stopped by user.")
    except Exception as e:
        print(f"Unexpected crash: {e}")