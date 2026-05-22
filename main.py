"""
main.py — Instagram DM Automation Agent
Flask webhook server for Meta/Instagram Messaging API.

Endpoints:
    GET  /webhook   Meta webhook verification (hub.challenge)
    POST /webhook   Incoming Instagram DM events
    GET  /health    Health-check for load-balancer / uptime monitors
"""
import logging
import os

from flask import Flask, jsonify, request

import config
from message_handler import handle_message

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)

# ── Webhook verification (GET) ────────────────────────────────────────────────

@app.get("/webhook")
def verify_webhook():
    """
    Meta sends a GET request to verify the webhook endpoint.
    We echo back hub.challenge only if the verify token matches.
    """
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == config.VERIFY_TOKEN:
        logger.info("Webhook verified ✅")
        return challenge, 200

    logger.warning("Webhook verification failed — bad token or mode")
    return "Forbidden", 403


# ── Incoming events (POST) ────────────────────────────────────────────────────

@app.post("/webhook")
def webhook():

    """
    Meta posts all Instagram DM events here.

    Payload shape:
        {
            "object": "instagram",
            "entry": [
                {
                    "id": "<page_id>",
                    "time": 1234567890,
                    "messaging": [
                        {
                            "sender":    {"id": "<psid>"},
                            "recipient": {"id": "<page_id>"},
                            "timestamp": 1234567890,
                            "message": { ... }   // or "postback": { ... }
                        }
                    ]
                }
            ]
        }
    """

    data = request.get_json(silent=True)
    print(f"data: {data}")  ### Log the incoming payload for debugging

    if not data:
        logger.warning("Received non-JSON webhook body")
        return "Bad Request", 400

    if data.get("object") != "instagram":
        return "Not handled", 404

    for entry in data.get("entry", []):
        for messaging_event in entry.get("messaging", []):
            sender_id = messaging_event.get("sender", {}).get("id")

            # Filter out echo messages from the page itself

            logger.info("SENDER: %s | PAGE: %s | MATCH: %s", sender_id, config.INSTAGRAM_ACCOUNT_ID, sender_id == config.INSTAGRAM_ACCOUNT_ID) ###

            if sender_id == config.INSTAGRAM_ACCOUNT_ID:
                logger.debug("Skipping self-message from page account")
                continue

            handle_message(messaging_event)

    # Always respond with 200 quickly — Meta will retry on non-200
    return "EVENT_RECEIVED", 200

# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "instagram-agent"}), 200

# ── Dev server ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting Instagram Agent on port %d (debug=%s)", config.PORT, config.DEBUG)
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
