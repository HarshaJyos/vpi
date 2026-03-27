# 🚀 Aria Voice Assistant - Production Ready ✅

## 🎯 One-Command Start

```bash
cd ~/aria-voice-assistant
chmod +x run.sh
./run.sh
```

**Auto-does**:
- Creates `venv` & installs deps
- Copies `.env.example → .env`
- Starts dashboard: **http://127.0.0.1:8000**

## 📱 Dashboard (localhost:8000)
1. Paste Gemini API key (aistudio.google.com/app/apikeys)
2. **🎤 Start Continuous** → USB mic → Aria speaks (3.5mm)
3. **CLI Sync**: `python gemini_live_test.py --dashboard`

## 🎙️ Core Pipeline
```
USB Mic (hw:3,0) 16kHz → Gemini 2.5 Flash → gTTS → pygame (3.5mm)
                  ↑
             Dashboard Toggle/Pause + History
```

## 🛠️ Hardware
```bash
# List mics
arecord -l
# Test USB mic 3
arecord -D plughw:3,0 -d 3 test.wav && play test.wav
```

## 📋 Features
| ✓ Live Gemini 2.5 | ✓ 20-msg Memory | ✓ Continuous Toggle |
|-------------------|-----------------|-------------------|
| ✓ Dashboard UI | ✓ CLI Dual-mode | ✓ State Sync | 
| ✓ Hot Reload | ✓ .env Auto | ✓ 16kHz Audio |

## 🔧 Files (Cleaned)
```
✅ app.py (dashboard)
✅ gemini_live_test.py (CLI)
✅ requirements.txt (pinned)
✅ run.sh (auto-setup)
✅ .env.example
✅ README.md
❌ Removed: app_new.py, gemini_live_test_new.py
```

## 🧪 Verify Working
```bash
./run.sh  # Dashboard starts
# New terminal:
source venv/bin/activate
python gemini_live_test.py --dashboard  # CLI sync
```

## 📖 Wakeword (Docs)
- [Porcupine Setup](PORCUPINE_SETUP.md) - Optional offline
- [Wakeword Guide](README_WAKWORD.md) - Google Speech fallback

## 🎉 Status: Fixed & Production Ready
**All formats corrected, deps clean, duplicates removed, auto-setup complete.**

**Run `./run.sh` to verify!**
