#!/usr/bin/env python3
"""Sync Zerodha (Indian PF) balance from Google Sheets to Monarch Money."""

import json
import os
import re
import sys
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── Config ────────────────────────────────────────────────────────────────────
SHEET_ID = "10AjE53pQv-NKO-YoQsVjsOzNRRXjdUPkmleTzDBYoBk"
SHEET_TAB = "PF Summary"
LABEL_TO_FIND = "Indian PF"
MONARCH_ACCOUNT_ID = "210134774683437453"


# ── Step 1: Read balance from Google Sheets ───────────────────────────────────
def get_indian_pf_balance() -> float:
    raw_key = os.environ["GSHEET_SERVICE_ACCOUNT_JSON"]
    key_info = json.loads(raw_key)

    creds = service_account.Credentials.from_service_account_info(
        key_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=creds)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SHEET_ID, range=f"'{SHEET_TAB}'")
        .execute()
    )
    rows = result.get("values", [])
    for row in rows:
        for i, cell in enumerate(row):
            if cell.strip() == LABEL_TO_FIND and i + 1 < len(row):
                raw = row[i + 1].strip()
                clean = re.sub(r"[^\d.]", "", raw)
                return float(clean)
    raise ValueError(f"Could not find row labeled '{LABEL_TO_FIND}' in sheet")


# ── Step 2: Update Monarch Money ──────────────────────────────────────────────
def update_monarch(balance: float) -> None:
    import urllib.request

    token = os.environ["MONARCH_TOKEN"]

    query = """
    mutation Common_UpdateAccount($input: UpdateAccountMutationInput!) {
        updateAccount(input: $input) {
            account {
                id
                displayName
                displayBalance
            }
            errors {
                message
            }
        }
    }
    """
    payload = json.dumps({
        "query": query,
        "variables": {
            "input": {
                "id": MONARCH_ACCOUNT_ID,
                "displayBalance": balance,
            }
        },
    }).encode()

    req = urllib.request.Request(
        "https://api.monarch.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Client-Platform": "web",
            "User-Agent": "MonarchMoneyAPI (https://github.com/bradleyseanf/monarchmoneycommunity)",
        },
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    errors = result.get("data", {}).get("updateAccount", {}).get("errors", [])
    if errors:
        print(f"ERROR: {errors}", file=sys.stderr)
        sys.exit(1)

    updated = result.get("data", {}).get("updateAccount", {}).get("account", {})
    print(f"Updated: {updated.get('displayName')} → ${updated.get('displayBalance'):,.2f}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Fetching Indian PF balance from Google Sheets...")
    balance = get_indian_pf_balance()
    print(f"  Found: ${balance:,.2f}")

    print("Updating Monarch Money...")
    update_monarch(balance)
    print("Done.")
