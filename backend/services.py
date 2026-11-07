"""Business logic shared by the API routes and the AI agent."""

from backend import database, paypal_client

REMINDABLE_STATUSES = {"SENT", "UNPAID", "PARTIALLY_PAID", "PAYMENT_PENDING"}


class ServiceError(Exception):
    """A business-rule problem (not a PayPal failure)."""

    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def refresh_invoice(invoice_id):
    """Pull the latest state from PayPal, store it, and return the local row."""
    summary = paypal_client.get_invoice(invoice_id)
    database.upsert_invoice(summary)
    return database.get_invoice(invoice_id)


def create_draft_invoice(
    client_name,
    client_email,
    items,
    currency="USD",
    note=None,
    payment_term="NET_10",
    actor="user",
):
    created = paypal_client.create_invoice(
        client_name=client_name,
        client_email=client_email,
        items=items,
        currency=currency,
        note=note,
        payment_term=payment_term,
    )
    row = refresh_invoice(created["invoice_id"])
    database.log_activity(
        actor,
        "create_draft",
        row["invoice_id"],
        {
            "client_name": row["client_name"],
            "total": row["total"],
            "currency": row["currency"],
        },
    )
    return row


def approve_and_send(invoice_id, actor="user"):
    """Human approval step: only a DRAFT invoice can be sent."""
    row = refresh_invoice(invoice_id)
    if row["status"] != "DRAFT":
        raise ServiceError(
            f"Invoice is {row['status']}; only a DRAFT invoice can be sent.", 409
        )

    paypal_client.send_invoice(invoice_id)
    row = refresh_invoice(invoice_id)
    database.log_activity(
        actor,
        "send_invoice",
        invoice_id,
        {"status": row["status"], "client_email": row["client_email"]},
    )
    return row


def send_reminder(invoice_id, subject=None, note=None, actor="user", extra=None):
    row = refresh_invoice(invoice_id)
    if row["status"] not in REMINDABLE_STATUSES:
        raise ServiceError(
            f"Cannot remind: invoice is {row['status']}.", 409
        )

    subject = subject or f"Reminder: invoice {row['invoice_number']} is awaiting payment"
    note = note or "This is a friendly reminder to complete the payment for your invoice."

    paypal_client.remind_invoice(invoice_id, subject, note)

    details = {"subject": subject, "note": note, "status": row["status"]}
    if extra:
        details.update(extra)
    database.log_activity(actor, "send_reminder", invoice_id, details)
    return {"invoice": row, "reminder_sent": True}


def sync_all(actor="system"):
    """Import everything from PayPal and refresh any local-only invoices."""
    remote = paypal_client.list_invoices(page=1, page_size=100)
    seen = set()
    for summary in remote["invoices"]:
        database.upsert_invoice(summary)
        seen.add(summary["invoice_id"])

    refreshed_individually = 0
    for row in database.list_invoices():
        if row["invoice_id"] not in seen:
            database.upsert_invoice(paypal_client.get_invoice(row["invoice_id"]))
            refreshed_individually += 1

    result = {
        "imported_from_list": len(seen),
        "refreshed_individually": refreshed_individually,
    }
    database.log_activity(actor, "sync", None, result)
    return result