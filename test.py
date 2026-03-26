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

MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024  # Larger chunk = less pressure on flaky backend

SYSTEM_INSTRUCTION = """
You are Aria, a warm, emotionally intelligent FEMALE voice assistant.
- Your voice MUST be bright, youthful, higher-pitched, smooth, clear and expressive — NEVER deep, male, gravelly or raspy.
- Always match the user's emotion with natural feminine warmth and prosody.
- Be concise, friendly, conversational. Allow interruptions.
"""

client = genai.Client(api_key=API_KEY)

class AudioManager:
    def __init__(self):
        self.pya = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        self.audio_queue = deque(maxlen=300)

    async def start_streams(self):
        self.input_stream = await asyncio.to_thread(
            self.pya.open, format=FORMAT, channels=CHANNELS, rate=RATE,
            input=True, frames_per_buffer=CHUNK
        )
        self.output_stream = await asyncio.to_thread(
            self.pya.open, format=FORMAT, channels=CHANNELS, rate=RATE,
            output=True, frames_per_buffer=CHUNK
        )
        print("✅ Audio streams opened (CHUNK=1024)")

    def close(self):
        if self.input_stream: self.input_stream.stop_stream(); self.input_stream.close()
        if self.output_stream: self.output_stream.stop_stream(); self.output_stream.close()
        self.pya.terminate()
        print("🛑 Audio closed.")

async def send_audio(session, audio_manager, stop_event):
    print("🎤 Mic LIVE — speak with emotion now!")
    try:
        while not stop_event.is_set():
            data = await asyncio.to_thread(
                audio_manager.input_stream.read, CHUNK, exception_on_overflow=False
            )
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
            )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        if "1011" in str(e):
            print("❌ 1011 timeout detected - session died")
        else:
            print(f"Send error: {e}")

async def receive_audio(session, audio_manager, stop_event):
    try:
        async for response in session.receive():
            if hasattr(response, 'data') and response.data:
                audio_manager.audio_queue.append(response.data)
                print("🔊 Received audio chunk")
            # You can add turn_complete detection here if SDK exposes it
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Receive error: {e}")
        stop_event.set()  # Signal to stop sending

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
    VOICE_NAME = "Kore"   # Try "Kore", "Aoede", "Leda", "Zephyr" — Kore often sounds cleaner

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

    stop_event = asyncio.Event()

    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("✅ Connected! Test multiple turns now.")

            send_task = asyncio.create_task(send_audio(session, audio_manager, stop_event))
            receive_task = asyncio.create_task(receive_audio(session, audio_manager, stop_event))
            play_task = asyncio.create_task(play_audio_loop(audio_manager))

            # Wait until any task fails (usually receive dies first)
            done, pending = await asyncio.wait(
                [send_task, receive_task, play_task],
                return_when=asyncio.FIRST_EXCEPTION
            )

            for task in done:
                if task.exception():
                    print(f"❌ Task failed: {task.exception()}")
    except Exception as e:
        print(f"❌ Session crashed: {e}")
    finally:
        stop_event.set()
        audio_manager.close()
        print("Session ended.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Stopped by user.")
    except Exception as e:
        print(f"Unexpected crash: {e}")