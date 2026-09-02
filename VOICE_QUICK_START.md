# 🎤 Voice Assistant - QUICK START (5 Minutes)

## ⚡ Super Fast Setup

### 1. Get Gemini API Key (2 min)
1. Go to: https://aistudio.google.com/
2. Click **"Get API Key"** → **"Create API Key"**
3. Copy the key

### 2. Add Key to `.env` (1 min)
Open `backend/.env` and add:
```env
GEMINI_API_KEY=paste_your_key_here
```

### 3. Install & Run (2 min)
**Option A - Double-click:**
```
Double-click: START_VOICE_DEMO.bat
```

**Option B - Manual:**
```powershell
cd backend
pip install google-genai
python -m uvicorn app.main:app --reload
```

### 4. Test (30 sec)
Open Chrome: **http://localhost:8000/voice-assistant.html**

Click 🎤 and say:
- **English:** "What is my soil moisture?"
- **Hindi:** "मिट्टी की नमी कितनी है?"
- **Marathi:** "EC किती आहे?"

---

## ✅ That's It!

You now have:
- ✅ Voice recognition (mic → text)
- ✅ Gemini AI with farm context
- ✅ Hindi/Marathi/English support
- ✅ Text-to-speech responses

---

## 📚 Full Documentation

See: **VOICE_ASSISTANT_SETUP.md** for detailed 2-hour guide

---

## 🐛 Problems?

| Issue | Solution |
|-------|----------|
| "GEMINI_API_KEY not configured" | Check `.env` file, restart server |
| Mic not working | Use Chrome, allow permission |
| Module not found | Run: `pip install google-genai` |
| Wrong language | Speak clearly in your chosen language |

---

## 🎯 Demo Script (30 seconds)

1. Open page in Chrome
2. Click microphone
3. Say: "fertilizer kyun band hai?" (Hindi)
4. Show: Answer in Hindi + Farm data context
5. Browser speaks answer

**Done!** 🎉
