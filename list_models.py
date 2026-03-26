import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

print("Listing all models...")
try:
    models = client.models.list()
    for m in models:
        # Print the whole model object to see attributes
        print(f"Model ID: {m.name}")
except Exception as e:
    print(f"Error listing models: {e}")
