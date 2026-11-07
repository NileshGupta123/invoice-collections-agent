import os
import sys
import json

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
BASE_URL = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")

DEFAULT_INVOICE_ID = "INV2-WSV7-RBPB-P7RG-X285"


def get_access_token():
    response = requests.post(
        f"{BASE_URL}/v1/oauth2/token",
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={"Accept": "application/json"},
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def main():
    invoice_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INVOICE_ID

    token = get_access_token()
    response = requests.get(
        f"{BASE_URL}/v2/invoicing/invoices/{invoice_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    print("HTTP status:", response.status_code)
    if response.status_code != 200:
        print(response.text)
        sys.exit(1)

    data = response.json()
    print("Invoice ID:", data.get("id"))
    print("STATUS:", data.get("status"))
    print("Viewed by recipient:", data.get("detail", {}).get("viewed_by_recipient"))
    print("Total:", data.get("amount", {}).get("value"), data.get("amount", {}).get("currency_code"))
    print("Due amount:", json.dumps(data.get("due_amount")))

    payments = data.get("payments", {})
    if payments:
        print("Payments:", json.dumps(payments, indent=2))


if __name__ == "__main__":
    main()