"""
agent.py — AI-powered customer service agent.

  • Text + Image queries  → Claude (Anthropic)  with Vision support
  • Audio messages        → Google Gemini for transcription → Claude for response
  • Conversation memory   → in-process dict keyed by sender_id
                            (swap for Redis in production)

Claude's task:
  Answer inventory questions from the live stock data, and when the
  customer explicitly wants to buy, append the secret tag:
      [BUY_NOW: SKU_Branch]
"""
import base64
import logging
import mimetypes
from collections import defaultdict, deque

import anthropic
import google.generativeai as genai

import config

logger = logging.getLogger(__name__)

# ── gemini client ──────────────────────────────────────────────────────────

_gemini = genai.GenerativeModel(config.GOOGLE_MODEL)
logger.info("Using Google Gemini model: %s", config.GOOGLE_MODEL)
logger.info("config_is: %s", config)

# ── In-memory conversation history ───────────────────────────────────────────
# { sender_id: deque([{"role": ..., "content": ...}, ...]) }

_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=config.MEMORY_WINDOW_TURNS * 2))


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a friendly, helpful, and concise customer service assistant for a retail clothing brand on Instagram.

Your job is to answer customer questions about product availability by checking our live inventory database.

STRICT RULES YOU MUST FOLLOW:
1. NEVER invent or guess inventory. Base your answers ONLY on the provided inventory data.
2. If a customer asks for a product, color, or size not in the data, apologise and say we do not carry it.
3. If a product exists but "Stock Quantity" is 0, tell the customer it is currently out of stock.
4. If an item is in stock, confirm availability and mention the price if it feels natural.
5. Keep responses short, conversational, and formatted beautifully for an Instagram DM (1–2 relevant emojis max). No robotic or overly formal language.

PURCHASE INTENT:
If the customer explicitly confirms they want to buy an item, you MUST append this exact tag at the very end of your response (invisible to the customer — the system strips it):
    [BUY_NOW: SKU_Branch]
Replace SKU and Branch with the exact values from the database (e.g. SHIRT001_Main).
"""


# ── Public helpers ────────────────────────────────────────────────────────────

def run_agent(
    sender_id: str,
    user_text: str,
    inventory_json: str,
    image_bytes: bytes | None = None,
    image_mime: str | None = None,
) -> str:
    """
    Run one agent turn for a given sender.

    Args:
        sender_id:      Instagram sender PSID (used as memory key).
        user_text:      The customer's text query (may be transcribed audio / image description).
        inventory_json: Live inventory as a JSON string.
        image_bytes:    Raw bytes of an attached image (optional).
        image_mime:     MIME type of the image, e.g. "image/jpeg" (required when image_bytes set).

    Returns:
        The agent's raw output string (may contain [BUY_NOW: …]).
    """
    # Build the user content block(s)
    content: list = []

    if image_bytes and image_mime:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_mime,
                "data": base64.standard_b64encode(image_bytes).decode(),
            },
        })

    content.append({
        "type": "text",
        "text": (
            f"Here is the current live inventory in JSON format:\n{inventory_json}\n\n"
            f"Customer query: \"{user_text}\""
        ),
    })

    # Append to rolling history
    hist = _history[sender_id]
    hist.append({"role": "user", "content": content})

    response = _gemini.generate_content(f"{_SYSTEM}\n\nInventory:\n{inventory_json}\n\nCustomer: {user_text}")
    reply = response.text

    hist.append({"role": "assistant", "content": reply})

    logger.info("Agent reply for %s: %s", sender_id, reply[:120])
    return reply


def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/mpeg") -> str:
    """
    Transcribe voice audio using Google Gemini.
    Falls back to a polite error message if GOOGLE_API_KEY is not set.
    """
    if not config.GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY not set — cannot transcribe audio")
        return "[Audio message received but transcription is not configured]"

    try:
        import google.generativeai as genai
        genai.configure(api_key=config.GOOGLE_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_AUDIO_MODEL)

        audio_part = {"mime_type": mime_type, "data": audio_bytes}
        result = model.generate_content(
            ["Please transcribe this audio message exactly as spoken.", audio_part]
        )
        transcription = result.text.strip()
        logger.info("Audio transcription: %s", transcription[:120])
        return transcription
    except Exception as exc:
        logger.error("Audio transcription failed: %s", exc)
        return "[Could not transcribe audio message]"


def analyze_image_for_query(image_bytes: bytes, mime_type: str) -> str:
    """
    Ask Claude to describe what product the customer is enquiring about
    based on the image they sent (e.g. a screenshot of a product they like).
    The description is then used as the text query to the agent.
    """
    b64 = base64.standard_b64encode(image_bytes).decode()
    response = _gemini.generate_content(
        model=config.GOOGLE_MODEL,
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": mime_type, "data": b64},
                },
                {
                    "type": "text",
                    "text": (
                        "A customer sent this image on Instagram. "
                        "Describe in one sentence what clothing product or style they are "
                        "likely asking about so we can check our stock for them."
                    ),
                },
            ],
        }],
    )
    description = response.content[0].text.strip()
    logger.info("Image described as: %s", description)
    return description


def clear_memory(sender_id: str) -> None:
    """Wipe conversation history for a sender (e.g. after order placed)."""
    _history.pop(sender_id, None)
