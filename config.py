import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Meeting settings
AUTO_JOIN = True
MEETING_PLATFORM = "google_meet"  # google_meet / zoom / teams

# Aria settings
ARIA_NAME = "Aria"
ARIA_WAKE_WORD = "hey"
VOICE_ENABLED = True
AVATAR_ENABLED = True  # Enabled for Phase 3!
STT_MODEL_SIZE = os.getenv("STT_MODEL_SIZE", "medium")

# Response gating
# strict: old behavior (requires "hey <name>")
# smart: responds to direct addressing even without wake word
RESPONSE_MODE = os.getenv("RESPONSE_MODE", "smart").lower()
ALLOW_WAKE_FALLBACK = os.getenv("ALLOW_WAKE_FALLBACK", "true").lower() == "true"

# Memory
MEMORY_DIR = "D:/AI/Project_Aria/meetings"
EMBEDDINGS_MODEL = "nomic-embed-text"
OLLAMA_BASE = "http://127.0.0.1:11434"
