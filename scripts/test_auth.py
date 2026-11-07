import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
BASE_URL = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")


def get_access_token():
    response = requests.post(
        f"{BASE_URL}/v1/oauth2/token",
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={"Accept": "application/json"},
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: .env file mein PAYPAL_CLIENT_ID ya PAYPAL_CLIENT_SECRET missing hai")
    else:
        try:
            data = get_access_token()
            print("SUCCESS: PayPal sandbox auth ho gaya")
            print("Token type:", data.get("token_type"))
            print("Expires in (seconds):", data.get("expires_in"))
            print("App ID:", data.get("app_id"))
        except requests.HTTPError as e:
            print("FAILED:", e.response.status_code, e.response.text)