import json
import gspread
from google.oauth2.service_account import Credentials
import traceback

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Step 1 — print service account details
with open("service_account.json") as f:
    info = json.load(f)

print(f"Project ID:    {info['project_id']}")
print(f"Client email:  {info['client_email']}")

# Step 2 — try to open the sheet
SHEET_ID = "1C3SfzCCA7GhqqJkFST8MBNT1LA5VzQaHi_O-RbZlnsg"

creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
client = gspread.authorize(creds)

try:
    sheet = client.open_by_key(SHEET_ID)
    print(f"SUCCESS — Sheet title: {sheet.title}")
except Exception as e:
    print(f"Exception type: {type(e).__name__}")
    print(f"Exception args: {e.args}")
    traceback.print_exc()