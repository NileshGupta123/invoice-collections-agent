"""SQLite storage for invoices and the agent activity log."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", os.path.join("data", "app.db"))

INVOICE_FIELDS = [
    "invoice_id",
    "invoice_number",
    "status",
    "client_name",
    "client_email",
    "currency",
    "total",
    "due_amount",
    "paid_amount",
    "invoice_date",
    "due_date",
    "paid_date",
    "note",
    "payer_view_url",
]

# Columns that keep their old value when PayPal's response does not include them.
KEEP_IF_MISSING = ("payer_view_url", "paid_date")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_conn():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_id TEXT PRIMARY KEY,
                invoice_number TEXT,
                status TEXT,
                client_name TEXT,
                client_email TEXT,
                currency TEXT,
                total TEXT,
                due_amount TEXT,
                paid_amount TEXT,
                invoice_date TEXT,
                due_date TEXT,
                paid_date TEXT,
                note TEXT,
                payer_view_url TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                actor TEXT,
                action TEXT,
                invoice_id TEXT,
                details TEXT
            )
            """
        )

        # Migration: older databases were created without paid_date.
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(invoices)").fetchall()
        }
        if "paid_date" not in columns:
            conn.execute("ALTER TABLE invoices ADD COLUMN paid_date TEXT")


def upsert_invoice(summary):
    """Insert or update an invoice from a paypal_client summary dict."""
    params = {field: summary.get(field) for field in INVOICE_FIELDS}
    params["now"] = _now()

    columns = ", ".join(INVOICE_FIELDS)
    placeholders = ", ".join(f":{field}" for field in INVOICE_FIELDS)
    plain_updates = ", ".join(
        f"{field}=excluded.{field}"
        for field in INVOICE_FIELDS
        if field != "invoice_id" and field not in KEEP_IF_MISSING
    )
    keep_updates = ", ".join(
        f"{field}=COALESCE(excluded.{field}, invoices.{field})"
        for field in KEEP_IF_MISSING
    )

    sql = f"""
        INSERT INTO invoices ({columns}, created_at, updated_at)
        VALUES ({placeholders}, :now, :now)
        ON CONFLICT(invoice_id) DO UPDATE SET
            {plain_updates},
            {keep_updates},
            updated_at=excluded.updated_at
    """
    with get_conn() as conn:
        conn.execute(sql, params)


def get_invoice(invoice_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,)
        ).fetchone()
    return dict(row) if row else None


def list_invoices():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM invoices ORDER BY created_at DESC, invoice_id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def log_activity(actor, action, invoice_id=None, details=None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO activity_log (timestamp, actor, action, invoice_id, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (_now(), actor, action, invoice_id, json.dumps(details or {})),
        )


def list_activity(limit=50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["details"] = json.loads(item["details"] or "{}")
        except ValueError:
            item["details"] = {}
        result.append(item)
    return result


def reminder_stats(invoice_id):
    """How many reminders were sent for an invoice, and when the last one went out."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n, MAX(timestamp) AS last_at
            FROM activity_log
            WHERE action = 'send_reminder' AND invoice_id = ?
            """,
            (invoice_id,),
        ).fetchone()
    return {"count": row["n"], "last_at": row["last_at"]}