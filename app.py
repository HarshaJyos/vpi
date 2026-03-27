# app.py - CLEAN & FIXED
import asyncio
import threading
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import core_voice

load_dotenv()

app = Flask(__name__)
app.secret_key = "aria-rpi-admin-2026"

# Global event loop for background task
background_loop = None
voice_task = None

# Initialize core
core_voice.init_client()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/toggle-listen', methods=['POST'])
def toggle_listen():
    global voice_task, background_loop

    if not core_voice.client:
        return jsonify({"success": False, "error": "Gemini client not ready"})

    core_voice.is_listening = not core_voice.is_listening

    if core_voice.is_listening:
        # Create background loop if not exists
        if background_loop is None:
            background_loop = asyncio.new_event_loop()
            threading.Thread(target=background_loop.run_forever, daemon=True).start()

        # Start the voice loop
        voice_task = asyncio.run_coroutine_threadsafe(
            core_voice.continuous_voice_loop(), background_loop
        )
        status_msg = "Aria is awake - Dynamic listening started"
        print("✅ Voice loop STARTED successfully")
    else:
        core_voice.is_listening = False
        status_msg = "Aria is sleeping"
        print("⏹️  Voice loop STOPPED")

    return jsonify({
        "success": True,
        "listening": core_voice.is_listening,
        "message": status_msg
    })

@app.route('/api/set-key', methods=['POST'])
def set_key():
    data = request.json
    key = data.get('key', '').strip()
    if not key:
        return jsonify({"success": False, "error": "Key required"})
    
    with open('.env', 'a') as f:
        f.write(f"\nGEMINI_API_KEY={key}\n")
    
    success = core_voice.init_client()
    return jsonify({"success": success})

@app.route('/api/test', methods=['POST'])
def test_api():
    if not core_voice.client:
        return jsonify({"success": False, "error": "Client not ready"})
    try:
        resp = core_voice.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": "Say hello warmly"}]}]
        )
        return jsonify({"success": True, "text": resp.text})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/clear', methods=['POST'])
def clear_history():
    core_voice.conversation_history.clear()
    return jsonify({"success": True})

if __name__ == '__main__':
    print("\n" + "="*80)
    print("🎤 ARIA RASPBERRY PI - Dynamic Voice Assistant (Fixed)")
    print("Microphone : plughw:3,0 (USB)")
    print("Web Admin  : http://0.0.0.0:5000")
    print("="*80 + "\n")

    app.run(host='0.0.0.0', port=5000, debug=False)