"""
instagram_api.py — thin wrapper around the Meta Graph API Messaging endpoint.

Permissions used:
    instagram_manage_messages  — send DMs / quick replies
    pages_show_list            — enumerate pages
    pages_manage_metadata      — subscribe webhooks
    instagram_basic            — read profile & media
"""
import logging
import re
import requests

import config

logger = logging.getLogger(__name__)

_MESSAGES_URL = f"{config.GRAPH_API_BASE}/{config.INSTAGRAM_ACCOUNT_ID}/messages"
_HEADERS = {"Content-Type": "application/json"}
_PARAMS  = {"access_token": config.PAGE_ACCESS_TOKEN}


# ── Low-level sender ──────────────────────────────────────────────────────────

def _send(payload: dict) -> dict:
    resp = requests.post(_MESSAGES_URL, headers=_HEADERS, params=_PARAMS, json=payload, timeout=15)
    if not resp.ok:
        logger.error("Graph API error %s: %s", resp.status_code, resp.text)
        resp.raise_for_status()
    return resp.json()


# ── Public helpers ────────────────────────────────────────────────────────────

def send_text(recipient_id: str, text: str) -> dict:
    """Send a plain text DM."""
    return _send({
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE",
        "message": {"text": text},
    })


def send_quick_replies(recipient_id: str, text: str, quick_replies: list[dict]) -> dict:
    """
    Send a message with quick-reply buttons.

    quick_replies format:
        [{"content_type": "text", "title": "Yes - Checkout", "payload": "BUY_YES_SKU001"}]
    """
    return _send({
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE",
        "message": {
            "text": text,
            "quick_replies": quick_replies,
        },
    })


def send_whatsapp_redirect(recipient_id: str, product_id: str) -> dict:
    """
    Send the WhatsApp checkout link after the customer taps 'Yes'.
    Pre-fills ORDER-IG-{product_id} in the WhatsApp message field.
    """
    wa_link = (
        f"https://wa.me/{config.WHATSAPP_NUMBER}"
        f"?text={config.WHATSAPP_ORDER_PREFIX}-{product_id}"
    )
    text = (
        "Awesome! Let's secure that for you. "
        f"Tap this link to open our WhatsApp checkout: {wa_link} 🛍️"
    )
    return send_text(recipient_id, text)


# ── Media helpers ─────────────────────────────────────────────────────────────

def download_media(url: str) -> bytes:
    """
    Download an Instagram media attachment (image / audio).
    The access_token is appended so that private CDN URLs are accessible.
    """
    resp = requests.get(url, params={"access_token": config.PAGE_ACCESS_TOKEN}, timeout=30)
    resp.raise_for_status()
    return resp.content


# ── Response parsers ──────────────────────────────────────────────────────────

_BUY_NOW_RE = re.compile(r"\[BUY_NOW:\s*(.+?)\]", re.IGNORECASE)


def extract_buy_now(agent_output: str) -> str | None:
    """
    Return the product token from [BUY_NOW: SKU_Branch] or None if absent.
    e.g.  "[BUY_NOW: SHIRT001_Main]"  →  "SHIRT001_Main"
    """
    m = _BUY_NOW_RE.search(agent_output)
    return m.group(1).strip() if m else None


def strip_buy_now(agent_output: str) -> str:
    """Remove the hidden [BUY_NOW: …] tag from the customer-visible text."""
    return _BUY_NOW_RE.sub("", agent_output).strip()
