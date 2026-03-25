#!/usr/bin/env python3
"""Parse sync_output.txt and write a clean email_body.txt for the success email."""

import re
import sys


def parse(text: str) -> dict:
    data = {
        "run_url": None,
        "zerodha_balance": None,
        "accounts": [],   # list of (label, amount, unit)  unit: "$" or "shares"
        "us_added": [],   # list of (ticker, qty_str)
        "us_removed": [], # list of ticker
        "us_updated": 0,
        "warnings": [],
    }

    for line in text.splitlines():
        # Run URL written by the init step
        if line.startswith("Run: http"):
            data["run_url"] = line[5:].strip()

        # Zerodha: "Updated: Zerodha → $234,794.88"
        m = re.match(r"Updated: .+ → \$([0-9,]+\.\d+)", line.strip())
        if m:
            data["zerodha_balance"] = m.group(1)

        # Account balance: "  8843 → C2: $9,945.67"
        m = re.match(r"\s+(\S+) → [A-Z]\d+: \$([0-9,]+\.\d+)", line)
        if m:
            label = m.group(1)
            display = f"...{label}" if re.match(r"^\d{4}$", label) else label
            data["accounts"].append((display, f"${m.group(2)}", ""))

        # SGOV: "  SGOV total → F5: 1,122.1153 shares"
        m = re.match(r"\s+SGOV total → [A-Z]\d+: ([0-9,]+\.\d+) shares", line)
        if m:
            data["accounts"].append(("SGOV", m.group(1), " shares"))

        # US added (detail line): "  NVDA   : 92.3431 shares (Theme/Conviction: fill manually)"
        m = re.match(r"\s+(\w+)\s*: ([0-9,]+\.\d+) shares \(Theme", line)
        if m:
            data["us_added"].append((m.group(1), m.group(2)))

        # US removed list: "Removing N closed positions: ['XYZ', ...]"
        m = re.match(r"Removing \d+ closed positions: \[(.+)\]", line)
        if m:
            data["us_removed"] = [t.strip().strip("'") for t in m.group(1).split(",")]

        # US summary: "Done. Updated 30, removed 0, added 0."
        m = re.match(r"Done\. Updated (\d+), removed \d+, added \d+\.", line)
        if m:
            data["us_updated"] = int(m.group(1))

        # Warnings / errors
        if re.search(r"WARNING:|ERROR", line, re.IGNORECASE):
            data["warnings"].append(line.strip())

    return data


def format_email(data: dict) -> str:
    lines = []

    if data["run_url"]:
        lines += [f"Run: {data['run_url']}", ""]

    # Warnings first
    if data["warnings"]:
        lines += ["WARNINGS", ""]
        for w in data["warnings"]:
            lines.append(f"  {w}")
        lines.append("")

    # Zerodha
    if data["zerodha_balance"]:
        lines += [
            "ZERODHA (Indian PF)",
            f"  ${data['zerodha_balance']}",
            "",
        ]

    # Account balances
    if data["accounts"]:
        lines.append("ACCOUNTS")
        label_w = max(len(label) for label, _, _ in data["accounts"])
        for label, amount, unit in data["accounts"]:
            lines.append(f"  {label:<{label_w}}  {amount}{unit}")
        lines.append("")

    # US Portfolio
    lines.append("US PORTFOLIO")
    has_changes = data["us_removed"] or data["us_added"]

    if data["us_removed"]:
        lines.append(f"  Closed:  {', '.join(data['us_removed'])}")

    if data["us_added"]:
        lines.append(f"  New:     {', '.join(t for t, _ in data['us_added'])}")
        for ticker, qty in data["us_added"]:
            lines.append(f"           {ticker}: {qty} shares  (fill Theme/Conviction)")

    if not has_changes:
        n = data["us_updated"]
        lines.append(f"  {n} position{'s' if n != 1 else ''} updated — no changes to holdings")
    elif data["us_updated"]:
        n = data["us_updated"]
        lines.append(f"  {n} existing position{'s' if n != 1 else ''} updated")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    with open("sync_output.txt") as f:
        text = f.read()

    data = parse(text)
    body = format_email(data)

    with open("email_body.txt", "w") as f:
        f.write(body)

    print(body, end="")
