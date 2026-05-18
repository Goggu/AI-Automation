"""
Configuration — all values come from environment variables / .env file.
"""
import os
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val

# ── Meta / Instagram ──────────────────────────────────────────────────────────
VERIFY_TOKEN          = _require("VERIFY_TOKEN")          # Your chosen webhook verify token
PAGE_ACCESS_TOKEN     = _require("PAGE_ACCESS_TOKEN")     # Instagram Page access token
INSTAGRAM_ACCOUNT_ID  = _require("INSTAGRAM_ACCOUNT_ID")  # IG-scoped page ID (to filter self-messages)
GRAPH_API_VERSION     = os.environ.get("GRAPH_API_VERSION", "v25.0")
GRAPH_API_BASE        = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# ── AI model (Anthropic Claude) ─────────────────────────────────────────────────────

#ANTHROPIC_API_KEY     = _require("ANTHROPIC_API_KEY")
#CLAUDE_MODEL          = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# ── AI model (Google Gemini) ───────────────────────────────────────

GOOGLE_API_KEY        = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_MODEL          = os.environ.get("GOOGLE_MODEL", "models/gemini-flash-latest:generateContent")
GEMINI_AUDIO_MODEL    = os.environ.get("GEMINI_AUDIO_MODEL", "models/gemini-2.5-flash")

# ── Google Sheets (inventory) ─────────────────────────────────────────────────
GOOGLE_SHEET_ID       = _require("GOOGLE_SHEET_ID")          # Spreadsheet ID from the URL
SHEET_NAME            = os.environ.get("SHEET_NAME", "Sheet1")

# Path to service-account JSON file, OR set GOOGLE_CREDENTIALS_JSON with the raw JSON string
GOOGLE_CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")  # raw JSON (for cloud deploy)

# ── WhatsApp redirect ─────────────────────────────────────────────────────────
WHATSAPP_NUMBER       = _require("WHATSAPP_NUMBER")  # e.g.  +917306420219
WHATSAPP_ORDER_PREFIX = os.environ.get("WHATSAPP_ORDER_PREFIX", "ORDER-IG")

# ── Conversation memory ───────────────────────────────────────────────────────
MEMORY_WINDOW_TURNS   = int(os.environ.get("MEMORY_WINDOW_TURNS", "10"))

# ── App ───────────────────────────────────────────────────────────────────────
PORT                  = int(os.environ.get("PORT", "5000"))
DEBUG                 = os.environ.get("DEBUG", "false").lower() == "true"
