"""
message_handler.py — orchestrates the full DM processing pipeline.

Flow diagram:
  Instagram DM event
       │
       ├─ quick_reply (payload contains "BUY_YES")
       │       └─ send WhatsApp redirect link  ✅
       │
       ├─ image attachment
       │       └─ download image
       │               └─ describe image with Claude Vision
       │                       └─ query inventory
       │                               └─ run agent  →  Switch1
       │
       ├─ audio attachment
       │       └─ download audio
       │               └─ transcribe with Gemini
       │                       └─ query inventory
       │                               └─ run agent  →  Switch1
       │
       └─ text message
               └─ query inventory
                       └─ run agent  →  Switch1

  Switch1:
       agent output contains [BUY_NOW: …]
           → strip tag, send quick-reply (Yes / No)
       else
           → send plain text reply
"""
import logging
import mimetypes

import agent
import instagram_api as ig
import inventory

logger = logging.getLogger(__name__)


# ── Entry point ───────────────────────────────────────────────────────────────

def handle_message(event: dict) -> None:
    """
    Process one messaging event from the Meta webhook payload.

    Args:
        event: Single messaging object, e.g.
               {"sender": {"id": "..."}, "message": {...}, ...}
    """
    sender_id = event.get("sender", {}).get("id", "")
    message   = event.get("message", {})

    if not sender_id or not message:
        return

    try:
        # ── Route ─────────────────────────────────────────────────────────────
        if _is_buy_yes_reply(message):
            _handle_buy_yes(sender_id, message)

        elif _has_attachment(message, "audio"):
            _handle_audio(sender_id, message)

        elif _has_attachment(message, "image"):
            _handle_image(sender_id, message)

        elif message.get("text"):
            _handle_text(sender_id, message["text"])
            print(f"Handled text message from {sender_id}") ###

        else:
            logger.info("Unhandled message type from %s: %s", sender_id, message)

    except Exception as exc:
        logger.exception("Error processing message from %s: %s", sender_id, exc)
        try:
            ig.send_text(sender_id, "Sorry, something went wrong on our end. Please try again shortly 🙏")
        except Exception:
            pass


# ── Route handlers ────────────────────────────────────────────────────────────

def _handle_buy_yes(sender_id: str, message: dict) -> None:
    """Customer tapped 'Yes - Checkout'. Send WhatsApp redirect link."""
    payload    = message.get("quick_reply", {}).get("payload", "")
    product_id = payload.replace("BUY_YES_", "", 1)
    logger.info("Purchase confirmed by %s — product: %s", sender_id, product_id)
    ig.send_whatsapp_redirect(sender_id, product_id)
    agent.clear_memory(sender_id)   # fresh start after purchase


def _handle_text(sender_id: str, text: str) -> None:
    """Plain text query → fetch inventory → run agent → reply."""
    inv_json    = inventory.inventory_as_json_string()
    agent_reply = agent.run_agent(sender_id, text, inv_json)
    _dispatch_agent_reply(sender_id, agent_reply)


def _handle_image(sender_id: str, message: dict) -> None:
    """
    Image query:
      1. Download the image from Instagram CDN.
      2. Ask Claude to describe what the customer is looking for.
      3. Run agent with both the image bytes AND the description as user_text.
    """
    url       = _first_attachment_url(message)
    img_bytes = ig.download_media(url)
    mime      = _guess_mime(url, "image/jpeg")

    # Describe the image to form a text query, then pass image to agent too
    description = agent.analyze_image_for_query(img_bytes, mime)
    logger.info("Image query from %s → %s", sender_id, description)

    inv_json    = inventory.inventory_as_json_string()
    agent_reply = agent.run_agent(sender_id, description, inv_json,
                                  image_bytes=img_bytes, image_mime=mime)
    _dispatch_agent_reply(sender_id, agent_reply)


def _handle_audio(sender_id: str, message: dict) -> None:
    """
    Audio query:
      1. Download the audio clip from Instagram CDN.
      2. Transcribe with Google Gemini.
      3. Run agent with the transcription as text.
    """
    url         = _first_attachment_url(message)
    audio_bytes = ig.download_media(url)
    mime        = _guess_mime(url, "audio/mpeg")

    transcription = agent.transcribe_audio(audio_bytes, mime)
    logger.info("Audio query from %s → %s", sender_id, transcription)

    inv_json    = inventory.inventory_as_json_string()
    agent_reply = agent.run_agent(sender_id, transcription, inv_json)
    _dispatch_agent_reply(sender_id, agent_reply)


# ── Switch1: dispatch agent reply ─────────────────────────────────────────────

def _dispatch_agent_reply(sender_id: str, agent_reply: str) -> None:
    """
    If the reply contains [BUY_NOW: SKU_Branch] → send yes/no quick-reply.
    Otherwise → send plain text.
    """
    product_id = ig.extract_buy_now(agent_reply)

    if product_id:
        visible_text = ig.strip_buy_now(agent_reply)
        ig.send_quick_replies(
            recipient_id=sender_id,
            text=f"{visible_text}\n\nAre you ready to check out?",
            quick_replies=[
                {
                    "content_type": "text",
                    "title": "Yes — Checkout ✅",
                    "payload": f"BUY_YES_{product_id}",
                },
                {
                    "content_type": "text",
                    "title": "No thanks",
                    "payload": "BUY_NO",
                },
            ],
        )
        logger.info("Sent checkout quick-reply to %s for product %s", sender_id, product_id)
    else:
        ig.send_text(sender_id, agent_reply)
        logger.info("Sent text reply to %s", sender_id)


# ── Utility helpers ───────────────────────────────────────────────────────────

def _is_buy_yes_reply(message: dict) -> bool:
    payload = message.get("quick_reply", {}).get("payload", "")
    return "BUY_YES" in payload


def _has_attachment(message: dict, att_type: str) -> bool:
    attachments = message.get("attachments", [])
    return bool(attachments) and attachments[0].get("type") == att_type


def _first_attachment_url(message: dict) -> str:
    return message["attachments"][0]["payload"]["url"]


def _guess_mime(url: str, fallback: str) -> str:
    mime, _ = mimetypes.guess_type(url.split("?")[0])
    return mime or fallback
