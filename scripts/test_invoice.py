import os
import sys
import json
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
BASE_URL = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
BUYER_EMAIL = os.getenv("PAYPAL_BUYER_EMAIL")


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


def api(method, path, token, body=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    response = requests.request(
        method,
        f"{BASE_URL}{path}",
        headers=headers,
        json=body,
        timeout=30,
    )
    return response


def show(step, response):
    print(f"\n--- {step} ---")
    print("HTTP status:", response.status_code)
    if response.text:
        try:
            print(json.dumps(response.json(), indent=2))
        except ValueError:
            print(response.text)


def main():
    if not CLIENT_ID or not CLIENT_SECRET or not BUYER_EMAIL:
        print("ERROR: .env mein PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET aur PAYPAL_BUYER_EMAIL teeno chahiye")
        sys.exit(1)

    token = get_access_token()
    print("Auth OK")

    # 1. Next invoice number
    r = api("POST", "/v2/invoicing/generate-next-invoice-number", token)
    show("1. Generate invoice number", r)
    if r.status_code != 200:
        sys.exit(1)
    invoice_number = r.json()["invoice_number"]

    # 2. Create draft invoice
    invoice_body = {
        "detail": {
            "invoice_number": invoice_number,
            "invoice_date": date.today().isoformat(),
            "currency_code": "USD",
            "note": "Test invoice from AI hackathon project",
            "payment_term": {"term_type": "NET_10"},
        },
        "invoicer": {
            "business_name": "Nilesh Freelance Studio",
        },
        "primary_recipients": [
            {
                "billing_info": {
                    "name": {"given_name": "Test", "surname": "Buyer"},
                    "email_address": BUYER_EMAIL,
                }
            }
        ],
        "items": [
            {
                "name": "Website design",
                "description": "Landing page design",
                "quantity": "1",
                "unit_amount": {"currency_code": "USD", "value": "100.00"},
            }
        ],
    }
    r = api("POST", "/v2/invoicing/invoices", token, invoice_body)
    show("2. Create draft invoice", r)
    if r.status_code != 201:
        sys.exit(1)
    invoice_id = r.json()["href"].split("/")[-1]
    print("INVOICE ID:", invoice_id)

    # 3. Send invoice
    send_body = {
        "send_to_invoicer": False,
        "send_to_recipient": True,
    }
    r = api("POST", f"/v2/invoicing/invoices/{invoice_id}/send", token, send_body)
    show("3. Send invoice", r)
    if r.status_code not in (200, 202):
        sys.exit(1)

    # 4. Check status
    r = api("GET", f"/v2/invoicing/invoices/{invoice_id}", token)
    show("4. Get invoice status", r)
    if r.status_code == 200:
        data = r.json()
        print("\nSTATUS:", data.get("status"))
        print("AMOUNT DUE:", data.get("due_amount"))

    # 5. Send reminder
    remind_body = {
        "subject": "Reminder: payment due",
        "note": "Friendly reminder to complete the payment for your invoice.",
        "send_to_invoicer": False,
    }
    r = api("POST", f"/v2/invoicing/invoices/{invoice_id}/remind", token, remind_body)
    show("5. Send reminder", r)

    print("\nDone. Ab Personal (buyer) account se https://www.sandbox.paypal.com par login karke invoice dekho.")


if __name__ == "__main__":
    main()