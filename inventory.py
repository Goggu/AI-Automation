"""
inventory.py — Google Sheets stock-database integration.

Sheet schema assumed (must match your mock sheet):
    SKU | Product Name | Branch | Category | Size | Color | Price | Stock Quantity

The sheet ID is the long string in the Google Sheets URL:
    https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit
"""
import json
import logging
from functools import lru_cache

import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


@lru_cache(maxsize=1)
def _get_client() -> gspread.Client:
    """Authenticate and return a cached gspread client."""
    if config.GOOGLE_CREDENTIALS_JSON:
        # Credentials supplied as a raw JSON string (handy for cloud deploys)
        info = json.loads(config.GOOGLE_CREDENTIALS_JSON)
        creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
    else:
        creds = Credentials.from_service_account_file(config.GOOGLE_CREDENTIALS_FILE, scopes=_SCOPES)
    return gspread.authorize(creds)


def fetch_inventory() -> list[dict]:
    """
    Return the full inventory as a list of row-dicts.
    Result is NOT cached so every call reflects the latest sheet data.

    Example row:
        {
            "SKU": "SHIRT001",
            "Product Name": "Classic White Tee",
            "Branch": "Main",
            "Category": "Tops",
            "Size": "M",
            "Color": "White",
            "Price": "29.99",
            "Stock Quantity": "15"
        }
    """
    try:
        client = _get_client()
        sheet  = client.open_by_key(config.GOOGLE_SHEET_ID).worksheet(config.SHEET_NAME)
        rows   = sheet.get_all_records()          # list[dict] keyed by header row
        logger.info("Fetched %d inventory rows from Google Sheets", len(rows))
        return rows
    except Exception as exc:
        logger.error("Failed to fetch inventory: %s", exc)
        return []


def inventory_as_json_string() -> str:
    """Return inventory JSON ready to embed in an LLM prompt."""
    return json.dumps(fetch_inventory(), ensure_ascii=False, indent=2)
