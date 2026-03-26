import asyncio
import os
from dotenv import load_dotenv
from google import genai
import pyaudio

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"  # or latest native audio model

async def main():
    config = {
        "response_modalities": ["AUDIO"],  # native audio out
        "speech_config": {"voice": "Puck"}  # or other voices
    }

    print("Connecting to Gemini Live... Say something after it connects.")

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        # You need proper audio streaming loop here - refer to official command-line example
        # For full bidirectional: use separate tasks for send_audio() and receive_audio()
        print("Session active. Test conversation now.")

if __name__ == "__main__":
    asyncio.run(main())