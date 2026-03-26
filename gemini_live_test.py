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

MODEL = "gemini-2.5-flash-native-audio-preview-09-2025"

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 512   # Back to 512 — better for real-time feel

SYSTEM_INSTRUCTION = """
You are a warm, emotionally intelligent female voice assistant with a clear, bright, and expressive voice.
- Your voice is feminine, higher-pitched, smooth, and full of emotion — never deep or male-sounding.
- Detect the user's emotion from tone and match it with warm, natural prosody.
- Speak naturally, conversationally, with good energy and feeling.
- Keep responses concise and helpful. Allow interruptions.
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
    print("🎤 Mic is LIVE and sending continuously. Speak clearly with emotion now!")
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
            # Silently ignore text/thought parts
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
    VOICE_NAME = "Aoede"   # Change to "Aoede", "Umbriel", "Zephyr" if you want

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
            print("✅ Connected successfully!")
            print("Speak now — say something emotional like 'I'm so excited!' or 'This is really frustrating.'")
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