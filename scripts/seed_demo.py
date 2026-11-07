"""Seed the PayPal sandbox with realistic demo clients and payment history.

For every invoice the script creates it in PayPal, sends it, and (for paid ones)
records a payment on a past date, so the collections agent has real history to
score. Dates are relative to today, so the demo always looks current.

Run from the project root:
    python -m scripts.seed_demo
"""

import argparse
import sys
from datetime import date, timedelta

from backend import database, paypal_client, services
from backend.paypal_client import PayPalError

DEMO_DOMAIN = "demo-clients.example.com"
CURRENCY = "USD"
TERM = "NET_15"
TERM_DAYS = 15

TODAY = date.today()

# Each invoice: (item name, amount, due date offset in days from today,
#                payment offset in days from the due date, or None if unpaid).
CLIENTS = [
    {
        "name": "Aarav Mehta",
        "email": f"aarav.mehta@{DEMO_DOMAIN}",
        "invoices": [
            ("Brand identity pack", 400, -60, -2),
            ("Website copy", 250, -35, -3),
            ("Landing page design", 600, 2, None),
        ],
    },
    {
        "name": "Maya Iyer",
        "email": f"maya.iyer@{DEMO_DOMAIN}",
        "invoices": [
            ("Logo redesign", 300, -90, 14),
            ("Social media kit", 220, -65, 10),
            ("Pitch deck", 500, -40, 13),
            ("Brochure design", 350, -8, None),
            ("Packaging mockup", 450, -16, None),
        ],
    },
    {
        "name": "Rohan Das",
        "email": f"rohan.das@{DEMO_DOMAIN}",
        "invoices": [
            ("Product photos", 180, -50, 0),
            ("Video edit", 320, -30, 6),
            ("Newsletter template", 140, -2, None),
        ],
    },
    {
        "name": "Priya Nair",
        "email": f"priya.nair@{DEMO_DOMAIN}",
        "invoices": [
            ("Illustration set", 275, 10, None),
        ],
    },
]


def day(offset):
    return TODAY + timedelta(days=offset)


def api(method, path, body=None):
    return paypal_client._request(method, path, body)


def create_and_send(name, email, item_name, amount, due_offset):
    """Create an invoice dated so that it falls due on the wanted day, then send it."""
    due = day(due_offset)
    invoice_date = due - timedelta(days=TERM_DAYS)

    number = api("POST", "/v2/invoicing/generate-next-invoice-number")["invoice_number"]
    given, surname = paypal_client._split_name(name)

    body = {
        "detail": {
            "invoice_number": number,
            "invoice_date": invoice_date.isoformat(),
            "currency_code": CURRENCY,
            "payment_term": {"term_type": TERM},
        },
        "invoicer": {"business_name": paypal_client.BUSINESS_NAME},
        "primary_recipients": [
            {
                "billing_info": {
                    "name": {"given_name": given, "surname": surname},
                    "email_address": email,
                }
            }
        ],
        "items": [
            {
                "name": item_name,
                "quantity": "1",
                "unit_amount": {
                    "currency_code": CURRENCY,
                    "value": f"{amount:.2f}",
                },
            }
        ],
    }

    created = api("POST", "/v2/invoicing/invoices", body)
    invoice_id = created["href"].split("/")[-1]
    api(
        "POST",
        f"/v2/invoicing/invoices/{invoice_id}/send",
        {"send_to_invoicer": False, "send_to_recipient": True},
    )
    return invoice_id, number


def record_payment(invoice_id, amount, paid_on):
    """Record a full payment on a past date. Tries two date formats."""
    base = {
        "method": "BANK_TRANSFER",
        "amount": {"currency_code": CURRENCY, "value": f"{amount:.2f}"},
        "note": "Demo payment",
    }
    formats = [paid_on.isoformat(), f"{paid_on.isoformat()}T00:00:00Z"]
    last_error = None
    for payment_date in formats:
        try:
            api(
                "POST",
                f"/v2/invoicing/invoices/{invoice_id}/payments",
                {**base, "payment_date": payment_date},
            )
            return
        except PayPalError as exc:
            if exc.status_code not in (400, 422):
                raise
            last_error = exc
    raise last_error


def cancel_old_open_invoices():
    """Cancel the earlier test invoices so they do not clutter the demo."""
    for row in database.list_invoices():
        email = row.get("client_email") or ""
        if email.endswith(DEMO_DOMAIN):
            continue
        if row["status"] not in services.REMINDABLE_STATUSES:
            continue
        try:
            api(
                "POST",
                f"/v2/invoicing/invoices/{row['invoice_id']}/cancel",
                {
                    "subject": "Invoice cancelled",
                    "note": "Cancelled while preparing demo data.",
                    "send_to_invoicer": False,
                    "send_to_recipient": False,
                    "additional_recipients": [],
                },
            )
            services.refresh_invoice(row["invoice_id"])
            print(f"Cancelled old test invoice #{row['invoice_number']}")
        except PayPalError as exc:
            print(
                f"Warning: could not cancel #{row['invoice_number']} "
                f"(PayPal status {exc.status_code}): {exc.payload}"
            )


def main():
    parser = argparse.ArgumentParser(description="Seed demo clients and invoices.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Seed again even if demo invoices already exist (creates duplicates).",
    )
    parser.add_argument(
        "--keep-old",
        action="store_true",
        help="Do not cancel the older test invoices.",
    )
    args = parser.parse_args()

    database.init_db()
    services.sync_all(actor="system")

    existing = [
        r
        for r in database.list_invoices()
        if (r.get("client_email") or "").endswith(DEMO_DOMAIN)
    ]
    if existing and not args.force:
        print(
            f"Demo invoices already exist ({len(existing)} found). "
            "Use --force only if you want duplicates."
        )
        sys.exit(1)

    if not args.keep_old:
        cancel_old_open_invoices()

    created_ids = []
    failed = False

    for client in CLIENTS:
        if failed:
            break
        print(f"\n{client['name']}")
        for item_name, amount, due_offset, paid_offset in client["invoices"]:
            try:
                invoice_id, number = create_and_send(
                    client["name"], client["email"], item_name, amount, due_offset
                )
                created_ids.append(invoice_id)
                line = f"  #{number} {item_name}: ${amount}, due {day(due_offset)}"

                if paid_offset is not None:
                    paid_on = day(due_offset + paid_offset)
                    record_payment(invoice_id, amount, paid_on)
                    line += f", paid {paid_on}"
                print(line)
            except PayPalError as exc:
                print(f"  FAILED on '{item_name}': PayPal status {exc.status_code}")
                print(f"  Details: {exc.payload}")
                failed = True
                break

    print("\nRefreshing local database...")
    for invoice_id in created_ids:
        services.refresh_invoice(invoice_id)

    print("\nSummary")
    for invoice_id in created_ids:
        row = database.get_invoice(invoice_id)
        print(
            f"  #{row['invoice_number']} {row['client_name']}: {row['status']}, "
            f"total {row['total']}, due {row['due_date']}, "
            f"paid date {row.get('paid_date') or '-'}"
        )

    if failed:
        print(
            "\nStopped early because PayPal rejected a request. "
            "Copy the output above and share it."
        )
        sys.exit(1)

    print("\nDone. Refresh the dashboard.")


if __name__ == "__main__":
    main()