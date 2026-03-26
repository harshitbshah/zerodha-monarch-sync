#!/usr/bin/env python3
"""Authenticate with Zerodha and return an enctoken for API calls.

Writes the enctoken to GITHUB_OUTPUT for downstream workflow steps.

Login flow (3 steps — no KiteConnect OAuth consent page required):
  1. GET kite.zerodha.com/user/login   → init session, get kf_session cookie
  2. POST /api/login                   → Zerodha credentials → get request_id
  3. POST /api/twofa                   → TOTP → server sets enctoken cookie
"""

import os

import pyotp
import requests


def login() -> str:
    user_id  = os.environ["ZERODHA_USER_ID"]
    password = os.environ["ZERODHA_PASSWORD"]
    totp_key = os.environ["ZERODHA_TOTP_KEY"]

    s = requests.Session()

    # Step 1: init — establishes kf_session cookie required by subsequent calls
    s.get("https://kite.zerodha.com/user/login", timeout=15)

    # Step 2: submit credentials
    r = s.post(
        "https://kite.zerodha.com/api/login",
        data={"user_id": user_id, "password": password},
        timeout=15,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"Login failed: {payload.get('message')}")
    request_id = payload["data"]["request_id"]

    # Step 3: submit TOTP — server sets enctoken cookie on success
    r = s.post(
        "https://kite.zerodha.com/api/twofa",
        data={
            "user_id":     user_id,
            "request_id":  request_id,
            "twofa_value": pyotp.TOTP(totp_key).now(),
            "twofa_type":  "totp",
        },
        timeout=15,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"Twofa failed: {payload.get('message')}")

    enctoken = s.cookies.get("enctoken")
    if not enctoken:
        raise RuntimeError("No enctoken cookie after twofa — login may have failed silently")

    return enctoken


if __name__ == "__main__":
    token = login()
    print("Zerodha enctoken generated successfully.")

    gh_output = os.environ.get("GITHUB_OUTPUT", "")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write(f"access_token={token}\n")
    else:
        print(f"ZERODHA_ENCTOKEN={token}")
