# portfolio-sync

Daily automation that keeps a personal Google Sheet portfolio tracker in sync with live brokerage data. Runs on GitHub Actions, Mon–Fri at 5 AM EST. Sends an HTML email summary on every run (success or failure).

## What it does

Four scripts run in sequence each weekday:

### 1. `kite_auth.py` — Zerodha headless login

Logs in to Zerodha using user ID + password + TOTP (via `pyotp`), extracts the `enctoken` session cookie, and writes it to `$GITHUB_OUTPUT` for subsequent steps.

### 2. `sync_indian_portfolio.py` — Zerodha holdings → Indian Portfolio sheet

- Fetches all settled DEMAT holdings from Zerodha (via enctoken auth)
- **Updates** Column C (Quantity) for all tickers already in the *Indian Portfolio* tab
- **Removes** rows for tickers no longer held in Zerodha (closed positions)
- **Inserts** new rows for tickers in Zerodha not yet in the sheet — Theme is left blank for manual entry

### 3. `sync.py` — Zerodha + Monarch balances → PF Summary sheet

- Reads the **Indian PF** USD balance from the *PF Summary* tab and updates the manual Zerodha account in **Monarch Money**
- Reads all US brokerage account balances from Monarch and writes them back to the *PF Summary* tab (bank accounts, CDs, etc.)
- Tracks the total SGOV share count across all brokerage accounts
- Reads the **PF Breakdown** table from the sheet and emits a parseable summary line for the email

### 4. `sync_us_portfolio.py` — Monarch holdings → US Portfolio sheet

Monarch Money is the source of truth (it integrates with all brokerage accounts). This script:

- **Updates** Column D (Quantity) for all tickers already in the *US Portfolio* tab
- **Removes** rows for tickers no longer held in any brokerage account (closed positions)
- **Inserts** new rows for tickers that appear in Monarch but not yet in the sheet — Theme and Conviction Rating are left blank for manual entry

The Holdings column (E) auto-recalculates via `GOOGLEFINANCE` formulas once quantities are updated.

### Email notification (`format_email.py`)

After all sync scripts finish, `format_email.py` parses the combined log (`sync_output.txt`) and generates an HTML email showing:
- Portfolio totals (Indian PF / US PF / Total, with allocation %)
- Indian PF changes: quantity diffs, new positions, closed positions
- US PF changes: new positions, closed positions
- Warning banner if any WARNING/ERROR lines were emitted

A success email is sent after every run. A failure email (with the raw log) is sent if any step exits non-zero.

## Architecture

```
Zerodha (enctoken)    Google Sheets (Indian PF balance)    Monarch Money (brokerage-linked)
        │                           │                                   │
        ▼                           ▼                                   ▼
sync_indian_portfolio.py        sync.py                  sync_us_portfolio.py
        │                    ┌──────┴──────┐              ┌─────────────┴─────────────┐
        ▼                    ▼             ▼              ▼             ▼             ▼
 Update Indian         Update Zerodha  Write account  Update qty  Remove closed  Add new
 Portfolio tab         in Monarch      balances+SGOV  for tickers  positions    positions
                                            │                                   │
                                            └───────────────┬───────────────────┘
                                                            ▼
                                              Google Sheets (Personal tracker)
                                                            │
                                                            ▼
                                                   format_email.py
                                                            │
                                                            ▼
                                                  HTML email (Gmail SMTP)
```

## Sheet structure

| Tab | Managed by | Description |
|-----|-----------|-------------|
| PF Summary | `sync.py` | Net worth overview — bank, CDs, bonds, Indian + US PF totals |
| US Portfolio | `sync_us_portfolio.py` | US equity positions with Theme, Quantity, Holdings, Conviction |
| US PF P&L | Manual | Realized gains by year; performance vs SPY/QQQ |
| Indian Portfolio | `sync_indian_portfolio.py` | Indian equity holdings — Zerodha quantities synced daily |
| Indian PF P&L | Manual | Realized gains by Indian FY |
| Subscriptions | Manual | Recurring subscription tracker |

### Cells read by `sync.py` (PF Summary tab)

| What | How located | Used for |
|------|------------|----------|
| Indian PF balance | Row where col A/B = `GSHEET_LABEL` (default `Indian PF`), value in next column | Push to Monarch as Zerodha balance |
| Account balance rows | Col A = `sheet_category`, Col B = `sheet_institution` from `ACCOUNTS_JSON` | Pull from Monarch and write to Col C |
| SGOV quantity cell | Cell immediately to the right of `SGOV_LABEL` (default `Total:`) | Write total SGOV share count |
| PF Breakdown table | Rows below `PF_BREAKDOWN_LABEL` header (default `PF Breakdown`); label \| amount \| pct | Email summary — Indian PF / US PF / Total with allocation % |

### Cells read by `sync_indian_portfolio.py` (Indian Portfolio tab)

| What | Range | Used for |
|------|-------|----------|
| All ticker rows | `B:C` (ticker + quantity), starting row 2 | Diff against Zerodha holdings |

### Cells written by `sync_indian_portfolio.py` (Indian Portfolio tab)

| What | Column | Notes |
|------|--------|-------|
| Quantity | C | Updated for all existing positions |
| New rows | A–C | Inserted at end; Theme (col A) left blank |
| Closed rows | — | Entire row deleted |

### Cells written by `sync.py` (PF Summary tab)

| What | Column | Notes |
|------|--------|-------|
| Account balances | C | One row per `ACCOUNTS_JSON` entry, matched by category + institution |
| SGOV quantity | Right of `SGOV_LABEL` | Share count, not dollar value |

### Cells read/written by `sync_us_portfolio.py` (US Portfolio tab)

| What | Column | Notes |
|------|--------|-------|
| Read tickers | B | Used to diff against Monarch holdings |
| Quantity | D | Updated for all existing positions |
| New rows | A–F | Theme (A), Ticker (B), % of total (C formula), Qty (D), Holdings/GOOGLEFINANCE (E formula), Conviction (F) |
| Closed rows | — | Entire row deleted |

## Setup

### Google Cloud service account

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → enable **Google Sheets API**
3. **APIs & Services → Credentials → Create Credentials → Service Account**
4. Download the JSON key
5. Share your Google Sheet with the service account email (**Editor** access — needed for writes)

### Monarch Money token

Authenticate locally using the `monarchmoneycommunity` library:

```bash
pip install monarchmoneycommunity
```

```python
import asyncio, pickle
from monarchmoney import MonarchMoney, RequireMFAException

async def main():
    mm = MonarchMoney(session_file="monarch_session.pickle")
    try:
        await mm.login("your@email.com", "yourpassword", save_session=True)
    except RequireMFAException:
        mfa = input("2FA code: ")
        await mm.multi_factor_authenticate("your@email.com", "yourpassword", mfa)
        mm.save_session("monarch_session.pickle")

asyncio.run(main())
```

Extract the token:
```bash
python3 -c "
import pickle
with open('monarch_session.pickle', 'rb') as f:
    s = pickle.load(f)
print(s['token'])
"
```

### GitHub Secrets

| Secret | Description |
|--------|-------------|
| `ZERODHA_USER_ID` | Zerodha login user ID |
| `ZERODHA_PASSWORD` | Zerodha login password |
| `ZERODHA_TOTP_KEY` | Base32 TOTP secret from Zerodha 2FA setup — found in the QR code during 2FA enrollment |
| `MONARCH_TOKEN` | Monarch Money API token — expires every few months (see [Token expiry](#token-expiry)) |
| `GSHEET_SERVICE_ACCOUNT_JSON` | Full contents of the service account JSON key |
| `NOTIFY_EMAIL` | Gmail address used to send and receive sync notifications |
| `NOTIFY_EMAIL_APP_PASSWORD` | Gmail App Password — create at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) |

### GitHub Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GSHEET_SHEET_ID` | — | Google Sheet ID from the URL (`/spreadsheets/d/<ID>/edit`) |
| `GSHEET_TAB` | `PF Summary` | Tab name for `sync.py` |
| `GSHEET_LABEL` | `Indian PF` | Row label used to locate the Indian PF balance cell |
| `MONARCH_ACCOUNT_NAME` | `Zerodha` | Monarch display name of the manual Zerodha account |
| `ACCOUNTS_JSON` | *(see below)* | Maps Monarch accounts to PF Summary rows |
| `SGOV_LABEL` | `Total:` | Label to locate the SGOV quantity cell in PF Summary |
| `PF_BREAKDOWN_LABEL` | `PF Breakdown` | Header label that marks the portfolio breakdown table in PF Summary |
| `INDIAN_PORTFOLIO_TAB` | `Indian Portfolio` | Tab name for `sync_indian_portfolio.py` |
| `US_PORTFOLIO_TAB` | `US Portfolio` | Tab name for `sync_us_portfolio.py` |

`ACCOUNTS_JSON` maps each brokerage account to a row in the PF Summary tab:
```json
[
  {"mask": "1234", "sheet_category": "Bank", "sheet_institution": "Chase"},
  {"mask": "5678", "sheet_category": "CDs",  "sheet_institution": "Marcus"},
  {"monarch_name": "PayPal", "sheet_category": "Bank", "sheet_institution": "PayPal"}
]
```
Use `mask` (last 4 digits) for institution-synced accounts, `monarch_name` for manual accounts. For duplicate `sheet_category` + `sheet_institution` pairs (e.g. two Chase accounts), entries are matched in the order they appear in the sheet.

## Running locally

```bash
pip install google-auth google-auth-httplib2 google-api-python-client pyotp requests

# 1. Get Zerodha enctoken
ZERODHA_USER_ID=... ZERODHA_PASSWORD=... ZERODHA_TOTP_KEY=... python kite_auth.py
# Copy the printed enctoken, then:

# 2. Sync Indian portfolio
KITE_ACCESS_TOKEN=<enctoken> \
GSHEET_SHEET_ID=... \
GSHEET_SERVICE_ACCOUNT_JSON="$(cat gsheet-key.json)" \
python sync_indian_portfolio.py

# 3. Sync PF Summary
MONARCH_TOKEN=... \
GSHEET_SHEET_ID=... \
GSHEET_SERVICE_ACCOUNT_JSON="$(cat gsheet-key.json)" \
python sync.py

# 4. Sync US portfolio
MONARCH_TOKEN=... \
GSHEET_SHEET_ID=... \
GSHEET_SERVICE_ACCOUNT_JSON="$(cat gsheet-key.json)" \
python sync_us_portfolio.py
```

Copy `.env.example` to `.env` and fill in your values for a more convenient local setup.

## Running tests

```bash
python -m pytest tests/
```

Tests cover `kite_auth.py` (login flow), `sync.py` (pure logic functions), and `format_email.py` (parsing and HTML generation). Google Sheets and Monarch API calls are mocked.

## Maintenance

### Token expiry

Monarch tokens last several months. When one expires the workflow fails and you'll receive a failure email. To refresh:

1. Re-run the login script above to get a new `monarch_session.pickle`
2. Extract the token and update the `MONARCH_TOKEN` GitHub Secret

### New positions (US Portfolio)

When `sync_us_portfolio.py` inserts a new row, **Theme** and **Conviction Rating** are left blank — fill these in manually after the next run. Column B (ticker) will show a Google Sheets suggestion to "Add Finance chip" — clicking it is optional and purely cosmetic; the `GOOGLEFINANCE` formula in column E uses the ticker directly.

### Closed positions (US Portfolio)

Rows are deleted automatically when a ticker is no longer found in any Monarch brokerage account. If a position disappears temporarily due to a brokerage sync delay, it will be re-inserted on the next run (with blank Theme/Conviction — keep an eye on this).
