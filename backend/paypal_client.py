"""PayPal sandbox Invoicing client used by the agent as its tools."""

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
BASE_URL = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Nilesh Freelance Studio")

ALLOWED_TERMS = {
    "DUE_ON_RECEIPT",
    "NET_10",
    "NET_15",
    "NET_30",
    "NET_45",
    "NET_60",
    "NET_90",
}

_token_cache = {"token": None, "expires_at": 0.0}


class PayPalError(Exception):
    """Raised when PayPal returns a non-success response."""

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"PayPal API error {status_code}: {payload}")


def get_access_token():
    """Return a cached access token, refreshing it shortly before expiry."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    response = requests.post(
        f"{BASE_URL}/v1/oauth2/token",
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={"Accept": "application/json"},
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    if response.status_code != 200:
        raise PayPalError(response.status_code, response.text)

    data = response.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
    return _token_cache["token"]


def _request(method, path, body=None, params=None, extra_headers=None):
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    response = requests.request(
        method,
        f"{BASE_URL}{path}",
        headers=headers,
        json=body,
        params=params,
        timeout=30,
    )
    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        raise PayPalError(response.status_code, payload)

    if not response.text:
        return {}
    return response.json()


def _split_name(full_name):
    parts = full_name.strip().split(None, 1)
    given = parts[0] if parts else "Customer"
    surname = parts[1] if len(parts) > 1 else "."
    return given, surname


def summarize_invoice(data):
    """Reduce PayPal's big invoice payload to the fields the agent needs."""
    detail = data.get("detail", {})
    recipients = data.get("primary_recipients") or [{}]
    billing = recipients[0].get("billing_info", {})
    amount = data.get("amount", {})
    due = data.get("due_amount", {})
    payments = data.get("payments", {}) or {}
    paid = payments.get("paid_amount", {})

    paid_date = None
    dates = [
        t.get("payment_date")
        for t in (payments.get("transactions") or [])
        if t.get("payment_date")
    ]
    if dates:
        paid_date = max(dates)[:10]

    return {
        "invoice_id": data.get("id"),
        "invoice_number": detail.get("invoice_number"),
        "status": data.get("status"),
        "client_name": billing.get("name", {}).get("full_name"),
        "client_email": billing.get("email_address"),
        "currency": amount.get("currency_code"),
        "total": amount.get("value"),
        "due_amount": due.get("value"),
        "paid_amount": paid.get("value", "0.00"),
        "invoice_date": detail.get("invoice_date"),
        "due_date": detail.get("payment_term", {}).get("due_date"),
        "paid_date": paid_date,
        "note": detail.get("note"),
        "payer_view_url": detail.get("metadata", {}).get("recipient_view_url"),
    }


def create_invoice(
    client_name,
    client_email,
    items,
    currency="USD",
    note=None,
    payment_term="NET_10",
):
    """Create a draft invoice.

    items: list of dicts like
        {"name": "Logo design", "description": "...", "quantity": 1, "unit_amount": 250.0}
    Returns {"invoice_id": ..., "invoice_number": ...}.
    """
    if payment_term not in ALLOWED_TERMS:
        raise ValueError(f"payment_term must be one of {sorted(ALLOWED_TERMS)}")
    if not items:
        raise ValueError("items cannot be empty")

    number_data = _request("POST", "/v2/invoicing/generate-next-invoice-number")
    invoice_number = number_data["invoice_number"]

    given, surname = _split_name(client_name)
    paypal_items = []
    for item in items:
        paypal_items.append(
            {
                "name": item["name"],
                "description": item.get("description", ""),
                "quantity": str(item.get("quantity", 1)),
                "unit_amount": {
                    "currency_code": currency,
                    "value": f"{float(item['unit_amount']):.2f}",
                },
            }
        )

    detail = {
        "invoice_number": invoice_number,
        "currency_code": currency,
        "payment_term": {"term_type": payment_term},
    }
    if note:
        detail["note"] = note

    body = {
        "detail": detail,
        "invoicer": {"business_name": BUSINESS_NAME},
        "primary_recipients": [
            {
                "billing_info": {
                    "name": {"given_name": given, "surname": surname},
                    "email_address": client_email,
                }
            }
        ],
        "items": paypal_items,
    }

    created = _request("POST", "/v2/invoicing/invoices", body)
    invoice_id = created["href"].split("/")[-1]
    return {"invoice_id": invoice_id, "invoice_number": invoice_number}


def send_invoice(invoice_id):
    """Send a draft invoice to the recipient. Returns the payer view link."""
    data = _request(
        "POST",
        f"/v2/invoicing/invoices/{invoice_id}/send",
        {"send_to_invoicer": False, "send_to_recipient": True},
    )
    return {"invoice_id": invoice_id, "payer_view_url": data.get("href")}


def get_invoice(invoice_id):
    """Fetch one invoice and return a compact summary."""
    data = _request("GET", f"/v2/invoicing/invoices/{invoice_id}")
    return summarize_invoice(data)


def remind_invoice(invoice_id, subject, note):
    """Send a payment reminder for an unpaid invoice."""
    _request(
        "POST",
        f"/v2/invoicing/invoices/{invoice_id}/remind",
        {"subject": subject, "note": note, "send_to_invoicer": False},
    )
    return {"invoice_id": invoice_id, "reminder_sent": True}


def list_invoices(page=1, page_size=20):
    """List invoices (newest first) as compact summaries."""
    data = _request(
        "GET",
        "/v2/invoicing/invoices",
        params={"page": page, "page_size": page_size, "total_required": "true"},
    )
    return {
        "total_items": data.get("total_items"),
        "invoices": [summarize_invoice(i) for i in data.get("items", [])],
    }


if __name__ == "__main__":
    import json
    import sys

    default_id = "INV2-WSV7-RBPB-P7RG-X285"
    target = sys.argv[1] if len(sys.argv) > 1 else default_id

    print("--- get_invoice ---")
    print(json.dumps(get_invoice(target), indent=2))

    print("\n--- list_invoices ---")
    print(json.dumps(list_invoices(), indent=2))