"""
Run at 8:00 AM IST daily before market open.
Usage: python scripts/refresh_token.py
"""
import os
import sys
import webbrowser
from pathlib import Path
from dotenv import load_dotenv, set_key

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

BROKER = os.getenv("BROKER", "zerodha").lower()
ENV_FILE = ROOT / ".env"


def refresh_zerodha():
    from kiteconnect import KiteConnect
    api_key = os.getenv("KITE_API_KEY")
    api_secret = os.getenv("KITE_API_SECRET")

    kite = KiteConnect(api_key=api_key)
    login_url = kite.login_url()
    print(f"\nOpen this URL in your browser:\n{login_url}\n")
    webbrowser.open(login_url)

    request_token = input("Paste the request_token from the redirect URL: ").strip()
    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data["access_token"]

    set_key(str(ENV_FILE), "KITE_ACCESS_TOKEN", access_token)
    print(f"Access token saved to .env")
    return access_token


def refresh_upstox():
    import urllib.parse
    api_key = os.getenv("UPSTOX_API_KEY")
    redirect_uri = "http://localhost"
    auth_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code&client_id={api_key}&redirect_uri={urllib.parse.quote(redirect_uri)}"
    )
    print(f"\nOpen this URL in your browser:\n{auth_url}\n")
    webbrowser.open(auth_url)

    code = input("Paste the authorization code from the redirect URL: ").strip()

    import requests
    api_secret = os.getenv("UPSTOX_API_SECRET")
    resp = requests.post("https://api.upstox.com/v2/login/authorization/token", data={
        "code": code,
        "client_id": api_key,
        "client_secret": api_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    access_token = resp.json()["access_token"]
    set_key(str(ENV_FILE), "UPSTOX_ACCESS_TOKEN", access_token)
    print("Access token saved to .env")
    return access_token


if __name__ == "__main__":
    print(f"Refreshing token for broker: {BROKER}")
    if BROKER == "zerodha":
        token = refresh_zerodha()
    elif BROKER == "upstox":
        token = refresh_upstox()
    else:
        print(f"Unknown broker: {BROKER}")
        sys.exit(1)
    print(f"Done. Token: {token[:8]}...")
