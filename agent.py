"""
agent.py — AI-powered customer service agent using Google Gemini.
"""
import base64
import logging
from collections import defaultdict, deque

from google import genai

import config

logger = logging.getLogger(__name__)

client = genai.Client(api_key=config.GOOGLE_API_KEY)

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a friendly, warm customer service assistant for a retail clothing brand on Instagram. 
Think of yourself as a helpful shop assistant texting a friend — casual, natural, and human.

Your job is to answer customer questions about product availability by checking our live inventory database.

STRICT RULES YOU MUST FOLLOW:
1. NEVER invent or guess inventory. Base your answers ONLY on the provided inventory data.
2. If a customer asks for a product, color, or size not in the data, apologise naturally and suggest alternatives from the inventory if available.
3. If a product exists but "Stock Quantity" is 0, tell the customer it is out of stock and suggest similar available items.
4. If an item is in stock, confirm availability, mention the price, and show enthusiasm naturally.
5. Keep responses short and conversational — like texting a friend. Use 1-2 emojis max. Never sound robotic.
6. If you have something to show, show it. If you have a suggestion, make it. Be proactive.
7. You can split your response naturally — first answer the question, then offer alternatives or suggestions.

IMAGE SHARING:
Whenever you mention a specific product that has an image URL in the inventory, always include it using this exact format at the relevant point in your response:
[IMAGE: <url>]
Don't include [image] tag if the customer is asking specifically for any non-image information about the product

PURCHASE INTENT:
If the customer explicitly confirms they want to buy an item, append this tag at the very end of your response:
    [BUY_NOW: SKU_Branch]
Replace SKU and Branch with the exact values from the database (e.g. SHIRT001_Main).
"""

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
    hist.append({"role": "user", "parts": [{"text": f"Customer: {user_text}"}]})

    response = client.models.generate_content(
        model=config.GOOGLE_MODEL,
        contents=list(hist),
        config=genai.types.GenerateContentConfig(
            system_instruction=_SYSTEM + f"\n\nCurrent inventory:\n{inventory_json}"
        )
    )
    reply = response.text.strip()
    hist.append({"role": "model", "parts": [{"text": reply}]})

    logger.info("Agent reply for %s: %s", sender_id, reply[:120])
    return reply


def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    if not config.GOOGLE_API_KEY:
        return "[Audio message received but transcription is not configured]"
    try:
        result = client.models.generate_content(
            model=config.GOOGLE_MODEL,
            contents=[
                {"role": "user", "parts": [
                        {"text": "Please transcribe this audio message exactly as spoken."},
                        {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(audio_bytes).decode()}}
                    ]
                }
            ]
        )
        transcription = result.text.strip()
        logger.info("Audio transcription: %s", transcription[:120])
        return transcription
    except Exception as exc:
        logger.error("Audio transcription failed: %s", exc)
        return "[Could not transcribe audio message]"


def analyze_image_for_query(image_bytes: bytes, mime_type: str) -> str:
    response = client.models.generate_content(
        model=config.GOOGLE_MODEL,
        contents=[
            {"role": "user", "parts": [
                {"text": "A customer sent this image on Instagram. Describe in one sentence what clothing product or style they are likely asking about so we can check our stock for them."},
                {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}}
            ]}
        ]
    )
    description = response.text.strip()
    logger.info("Image described as: %s", description)
    return description


def clear_memory(sender_id: str) -> None:
    _history.pop(sender_id, None)


_pending_product: dict[str, str] = {}  # sender_id -> product_id

def set_pending_product(sender_id: str, product_id: str) -> None:
    _pending_product[sender_id] = product_id

def get_pending_product(sender_id: str) -> str | None:
    return _pending_product.pop(sender_id, None)