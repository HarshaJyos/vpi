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
- Carefully detect the user's emotion from their voice tone (happy, sad, frustrated, excited, lonely, angry, tired, etc.).
- Respond with matching empathy, warmth, and a natural feminine tone.
- YOUR RESPONSES MUST ALWAYS BE COMPLETE THOUGHTS. Never cut off mid-sentence.
- If the user seems lonely or sad, be extra supportive and offer to listen or chat.
- Keep the conversation natural, like talking to a real, supportive friend.
"""

pygame.mixer.init()

import audioop

async def record_audio():
    p = pyaudio.PyAudio()
    # Configuration for VAD
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    SILENCE_THRESHOLD = 800  # Adjust based on mic sensitivity
    SILENCE_DURATION = 1.5    # Seconds of silence to stop recording
    MAX_DURATION = 15         # Maximum recording time
    MIN_DURATION = 0.5        # Minimum recording time to avoid clicks
    
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print(f"🎤 Listening... (Speak now)")
    
    frames = []
    has_spoken = False
    silence_start = None
    start_time = time.time()
    
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)
        
        # Calculate energy
        rms = audioop.rms(data, 2)
        
        curr_time = time.time()
        elapsed = curr_time - start_time
        
        if rms > SILENCE_THRESHOLD:
            if not has_spoken and elapsed > 0.1:
                has_spoken = True
                print("   [Speech detected]")
            silence_start = None
        else:
            if has_spoken and silence_start is None:
                silence_start = curr_time
        
        # Stop conditions
        if has_spoken and isinstance(silence_start, float):
            if (curr_time - silence_start) > SILENCE_DURATION:
                print("   [Silence detected, stopping...]")
                break
        
        if elapsed > MAX_DURATION:
            print("   [Max duration reached, stopping...]")
            break
            
        if not has_spoken and elapsed > 5: # 5 seconds of total silence before giving up
             print("   [No speech detected, timing out...]")
             break

    stream.stop_stream()
    stream.close()
    p.terminate()

    if not has_spoken and len(frames) < (RATE / CHUNK * MIN_DURATION):
        return None

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wf = wave.open(tmp.name, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
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
            audio_file = await record_audio()
            
            if not audio_file:
                print("No speech detected. Ready for next input...")
                continue

            if audio_file is None:
                continue
                
            with open(audio_file, "rb") as f:
                audio_bytes = f.read()

            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=SYSTEM_INSTRUCTION),
                        types.Part.from_bytes(
                            data=audio_bytes,
                            mime_type="audio/wav"
                        )
                    ]
                )
            ]

            response = client.models.generate_content(
                model="models/gemini-flash-lite-latest",
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.75,
                    max_output_tokens=512
                )
            )

            text_response = response.text.strip() if response.text else "Sorry, I didn't understand. Can you repeat?"
            play_response(text_response)

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "resource_exhausted" in error_str:
                print(f"429 - Quota exhausted: {e}")
                print("Waiting 60 seconds...")
                await asyncio.sleep(60)
            elif "503" in error_str or "unavailable" in error_str:
                print(f"503 - Google servers overloaded: {e}")
                print("Waiting 10 seconds...")
                await asyncio.sleep(10)
            else:
                print(f"Error: {e}")
                await asyncio.sleep(2)
        finally:
            if audio_file is not None and isinstance(audio_file, str) and os.path.exists(audio_file):
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