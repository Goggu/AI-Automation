# Instagram DM Automation Agent

AI-powered Instagram DM agent for a retail clothing brand.  
Customers can query stock via **text, image, or voice**. When they're ready to buy,
the agent sends a yes/no prompt and redirects confirmed orders to WhatsApp.

---

## How it works

```
Instagram DM
     │
     ├─ Quick reply "Yes — Checkout"
     │       └─▶ Send WhatsApp link with pre-filled order text
     │
     ├─ Image attachment
     │       └─▶ Download image
     │               └─▶ Claude Vision describes the product
     │                       └─▶ Fetch live inventory (Google Sheets)
     │                               └─▶ Claude agent replies
     │
     ├─ Audio / voice message
     │       └─▶ Download audio
     │               └─▶ Gemini transcribes speech → text
     │                       └─▶ Fetch live inventory (Google Sheets)
     │                               └─▶ Claude agent replies
     │
     └─ Text message
             └─▶ Fetch live inventory (Google Sheets)
                     └─▶ Claude agent replies
                             │
                             ├─ Contains [BUY_NOW: SKU_Branch]?
                             │       └─▶ Strip tag, send Yes / No quick-reply
                             └─ Plain response
                                     └─▶ Send text DM
```

---

## Project structure

```
instagram_agent/
├── main.py               Flask webhook server (entry point)
├── config.py             Environment variable loader — fails fast if anything missing
├── message_handler.py    Orchestrates routing: text / image / audio / quick-reply
├── agent.py              Claude AI agent + conversation memory + Gemini audio
├── instagram_api.py      Meta Graph API — send messages, download media
├── inventory.py          Google Sheets read via gspread + service account
├── requirements.txt      Python dependencies
├── .env.example          Template — copy to .env and fill in
└── credentials.json      ← YOU supply this (Google service-account key)
```

---

## Prerequisites

| What | Where to get it |
|---|---|
| Meta app with approved permissions | [Meta Developer Console](https://developers.facebook.com) |
| Instagram Business / Creator account linked to a Facebook Page | Meta Business Suite |
| Anthropic API key | [console.anthropic.com](https://console.anthropic.com) |
| Google Cloud service account + Sheets API enabled | [Google Cloud Console](https://console.cloud.google.com) |
| Google Gemini API key *(voice messages only)* | [Google AI Studio](https://aistudio.google.com) |

### Required Meta permissions
- `pages_show_list`
- `pages_manage_metadata`
- `instagram_manage_messages`
- `instagram_basic`

---

## Setup

### 1. Clone and install

```bash
git clone <your-repo>
cd instagram_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Open .env and fill in every required value (see comments inside)
```

### 3. Google service account

1. Go to [Google Cloud Console](https://console.cloud.google.com) → IAM & Admin → Service Accounts → **Create**.
2. Grant the role **Viewer**.
3. Click the account → Keys → **Add Key → JSON** → download.
4. Save the file as `credentials.json` or `service_account.json` in the project root. A sample format service_account.json file has been given. Replace it with yours. 
5. Open your Google Sheet → **Share** it with the service-account email  
   (looks like `name@project.iam.gserviceaccount.com`).

### 4. Google Sheet schema

Your stock sheet must have these column headers in row 1:

| SKU | Product Name | Branch | Category | Size | Color | Price | Stock Quantity |
|---|---|---|---|---|---|---|---|
| SHIRT001 | Classic White Tee | Main | Tops | M | White | 29.99 | 15 |

The `SKU` and `Branch` columns are used to construct the WhatsApp order reference (`ORDER-IG-SHIRT001_Main`).

### 5. Register the Meta webhook

1. Meta Developer Console → your app → **Webhooks** → Instagram.
2. Set **Callback URL**: `https://your-domain.com/webhook`
3. Set **Verify Token**: the same value as `VERIFY_TOKEN` in your `.env`.
4. Click **Verify and Save**.
5. Subscribe to the **`messages`** field.

---

## Running locally

```bash
# Terminal 1 — start the agent
source .venv/bin/activate
python main.py

# Terminal 2 — expose it to Meta via ngrok
ngrok http 5000
```

Use the ngrok HTTPS URL as the webhook callback URL during development.

---

## Running in production

```bash
gunicorn main:app --workers 2 --bind 0.0.0.0:8000
```

Use a reverse proxy (nginx / Caddy) in front for TLS termination.

### Cloud deployment (Railway / Render)

1. Push the repo.
2. Set all environment variables in the platform's dashboard.
3. For `credentials.json`, paste the entire JSON content into `GOOGLE_CREDENTIALS_JSON` instead.  
   The app reads this env var automatically when the file isn't present.
4. Set the start command to:
   ```
   gunicorn main:app --workers 2 --bind 0.0.0.0:$PORT
   ```

---

## Conversation memory

By default, conversation history is stored **in process memory** (a Python dict).  
This means history is lost on restart, and won't work across multiple workers.

For production, replace the `_history` dict in `agent.py` with Redis:

```python
import redis, json
r = redis.from_url(os.environ["REDIS_URL"])

def _get_history(sender_id):
    raw = r.get(f"history:{sender_id}")
    return json.loads(raw) if raw else []

def _save_history(sender_id, history):
    r.set(f"history:{sender_id}", json.dumps(history), ex=86400)  # 24h TTL
```

---

## Environment variable reference

| Variable | Required | Description |
|---|---|---|
| `VERIFY_TOKEN` | ✅ | Webhook verify token (you choose) |
| `PAGE_ACCESS_TOKEN` | ✅ | Meta page access token |
| `INSTAGRAM_ACCOUNT_ID` | ✅ | Your page's IG-scoped ID |
| `ANTHROPIC_API_KEY` | ✅ | Claude API key |
| `GOOGLE_SHEET_ID` | ✅ | Spreadsheet ID from the URL |
| `WHATSAPP_NUMBER` | ✅ | WhatsApp number e.g. `+917306420219` |
| `GOOGLE_CREDENTIALS_FILE` | — | Path to service-account JSON (default: `credentials.json`) |
| `GOOGLE_CREDENTIALS_JSON` | — | Raw JSON string (alternative to file — for cloud) |
| `GOOGLE_API_KEY` | — | Gemini key for audio transcription |
| `SHEET_NAME` | — | Sheet tab name (default: `Sheet1`) |
| `CLAUDE_MODEL` | — | Claude model (default: `claude-sonnet-4-20250514`) |
| `GEMINI_AUDIO_MODEL` | — | Gemini model for audio (default: `models/gemini-1.5-flash`) |
| `MEMORY_WINDOW_TURNS` | — | Conversation turns to keep per user (default: `10`) |
| `WHATSAPP_ORDER_PREFIX` | — | Order text prefix (default: `ORDER-IG`) |
| `PORT` | — | Server port (default: `5000`) |
| `DEBUG` | — | Enable Flask debug mode (default: `false`) |

---

## Troubleshooting

**Webhook verification fails**  
→ Check that `VERIFY_TOKEN` in `.env` exactly matches what you entered in the Meta console.

**`Missing required env var` on startup**  
→ Make sure `.env` exists and all required variables are set (not just commented out).

**Google Sheets returns empty inventory**  
→ Confirm the service-account email has been shared on the sheet. Check `GOOGLE_SHEET_ID` and `SHEET_NAME`.

**Audio messages not handled**  
→ Set `GOOGLE_API_KEY`. Without it, the agent replies with a polite fallback message.

**Messages not received at all**  
→ Confirm the `messages` webhook field is subscribed in the Meta console. Re-verify the webhook URL if the domain changed.

**`[BUY_NOW: …]` appears in the customer's DM**  
→ The agent ignored the system prompt. Try increasing `max_tokens` in `agent.py` or check that the inventory JSON isn't truncating the prompt.
