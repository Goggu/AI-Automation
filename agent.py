"""
agent.py — AI-powered customer service agent using Google Gemini.
"""
import base64
import logging
from collections import defaultdict, deque

import google.generativeai as genai

import config

logger = logging.getLogger(__name__)

genai.configure(api_key=config.GOOGLE_API_KEY)

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a friendly, helpful, and concise customer service assistant for a retail clothing brand on Instagram.

Your job is to answer customer questions about product availability by checking our live inventory database.

STRICT RULES YOU MUST FOLLOW:
1. NEVER invent or guess inventory. Base your answers ONLY on the provided inventory data.
2. If a customer asks for a product, color, or size not in the data, apologise and say we do not carry it.
3. If a product exists but "Stock Quantity" is 0, tell the customer it is currently out of stock.
4. If an item is in stock, confirm availability and mention the price if it feels natural.
5. Keep responses short, conversational, and formatted beautifully for an Instagram DM (1-2 relevant emojis max). No robotic or overly formal language.

PURCHASE INTENT:
If the customer explicitly confirms they want to buy an item, you MUST append this exact tag at the very end of your response (invisible to the customer - the system strips it):
    [BUY_NOW: SKU_Branch]
Replace SKU and Branch with the exact values from the database (e.g. SHIRT001_Main).
"""

# ── Gemini model ──────────────────────────────────────────────────────────────

_model = genai.GenerativeModel(
    model_name=config.GOOGLE_MODEL,
    system_instruction=_SYSTEM
)

# ── In-memory conversation history ───────────────────────────────────────────

_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=config.MEMORY_WINDOW_TURNS * 2))


# ── Public helpers ────────────────────────────────────────────────────────────

def run_agent(
    sender_id: str,
    user_text: str,
    inventory_json: str,
    image_bytes: bytes | None = None,
    image_mime: str | None = None,
) -> str:
    hist = _history[sender_id]
    hist.append({"role": "user", "parts": [f"Inventory:\n{inventory_json}\n\nCustomer: {user_text}"]})

    response = _model.generate_content(list(hist))
    reply = response.text.strip()

    hist.append({"role": "model", "parts": [reply]})

    logger.info("Agent reply for %s: %s", sender_id, reply[:120])
    return reply


def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/mpeg") -> str:
    if not config.GOOGLE_API_KEY:
        return "[Audio message received but transcription is not configured]"
    try:
        audio_part = {"mime_type": mime_type, "data": audio_bytes}
        result = _model.generate_content(["Please transcribe this audio message exactly as spoken.", audio_part])
        transcription = result.text.strip()
        logger.info("Audio transcription: %s", transcription[:120])
        return transcription
    except Exception as exc:
        logger.error("Audio transcription failed: %s", exc)
        return "[Could not transcribe audio message]"


def analyze_image_for_query(image_bytes: bytes, mime_type: str) -> str:
    image_part = {"mime_type": mime_type, "data": image_bytes}
    response = _model.generate_content([
        "A customer sent this image on Instagram. Describe in one sentence what clothing product or style they are likely asking about so we can check our stock for them.",
        image_part
    ])
    description = response.text.strip()
    logger.info("Image described as: %s", description)
    return description


def clear_memory(sender_id: str) -> None:
    _history.pop(sender_id, None)