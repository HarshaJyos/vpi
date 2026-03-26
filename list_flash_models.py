import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

print("Flash Models:")
for m in client.models.list():
    if "flash" in m.name.lower():
        print(f"- {m.name}")
