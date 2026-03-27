#!/bin/bash
# Aria Voice Assistant - Production Start Script (with venv auto-setup)

set -e

VENV_DIR=venv
VENV_ACTIVATE="$VENV_DIR/bin/activate"

echo '🚀 Aria Voice Assistant - Auto Setup & Start'

# Venv setup
if [ ! -d "$VENV_DIR" ]; then
  echo '🐍 Creating virtual environment...'
  python3 -m venv "$VENV_DIR"
fi

if [ ! -f "$VENV_DIR/bin/pip" ]; then
  echo '❌ Venv creation failed. Check python3-venv package.'
  exit 1
fi

# Activate venv and install deps
echo '📥 Installing dependencies in venv...'
source "$VENV_ACTIVATE"
pip install --upgrade pip
pip install -r requirements.txt

# Copy env example if needed
if [ ! -f .env ]; then
  echo 'ℹ️  Copy .env.example to .env and add your GEMINI_API_KEY'
  cp .env.example .env || true
fi

echo ''
echo '🚀 Starting Aria Dashboard...'
echo '📱 Open: http://127.0.0.1:8000 (set API key there)'

# Start uvicorn in venv (background)
uvicorn app:app --host 127.0.0.1 --port 8000 --reload &

DASH_PID=$!

# Wait startup
sleep 5

echo '✅ Dashboard running!'
echo ''
echo '🎤 Test CLI (new terminal):'
echo '  cd ~/aria-voice-assistant'
echo '  source venv/bin/activate'
echo '  python gemini_live_test.py --dashboard'
echo ''
echo 'Press Ctrl+C to stop...'
wait $DASH_PID
