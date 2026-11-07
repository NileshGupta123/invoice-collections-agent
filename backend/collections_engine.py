"""Adaptive collections: client risk scoring, reminder decisions and message writing.

Decisions are rule-based, so they are deterministic and explainable. The AI model
only writes the reminder text, and a template is used if the model is unavailable.
"""

import json
import os
from datetime import date, datetime

from dotenv import load_dotenv
from groq import Groq, GroqError

from backend import database, services
from backend.paypal_client import PayPalError

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

OPEN_STATUSES = services.REMINDABLE_STATUSES
PAID_STATUSES = {"PAID", "MARKED_AS_PAID"}

# Start the heads-up reminder this many days before the due date.
LEAD_DAYS = {"LOW": 2, "MEDIUM": 3, "HIGH": 5}
# Minimum days between two overdue reminders on the same invoice.
GAP_DAYS = {"LOW": 7, "MEDIUM": 5, "HIGH": 3}
# After this many reminders, stop and hand the invoice to a human.
MAX_REMINDERS = int(os.getenv("MAX_REMINDERS", "4"))

TONE_GUIDE = {
    "friendly": (
        "Warm and light. A gentle heads-up or nudge, no pressure. If the invoice is "
        "already overdue, just say it may have slipped through."
    ),
    "firm": (
        "Polite but direct. State clearly that the invoice is overdue, give the amount "
        "and the due date, and ask for payment this week."
    ),
    "final": (
        "Serious and professional. Say this is the final reminder before the invoice is "
        "followed up personally. Do not mention fees, interest or legal action."
    ),
}


# ---------- helpers ----------


def _to_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_as_of(value):
    """Return the date decisions are made for (today unless simulated)."""
    if not value:
        return date.today()
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError("as_of must be a date like 2026-10-20")


def _client_key(row):
    return (row.get("client_email") or "").strip().lower()


def _refresh_state(include_open=True):
    """Fill missing paid dates (and optionally re-check open invoices) from PayPal."""
    for row in database.list_invoices():
        missing_paid_date = row["status"] in PAID_STATUSES and not row.get("paid_date")
        is_open = include_open and row["status"] in OPEN_STATUSES
        if missing_paid_date or is_open:
            try:
                services.refresh_invoice(row["invoice_id"])
            except PayPalError:
                continue


# ---------- risk scoring ----------


def build_history(rows, email, as_of):
    days_late = []
    overdue_open = 0
    open_amount = 0.0
    name = None

    for row in rows:
        if _client_key(row) != email:
            continue
        name = name or row.get("client_name")
        due = _to_date(row.get("due_date"))

        if row["status"] in PAID_STATUSES:
            paid = _to_date(row.get("paid_date"))
            if due and paid:
                days_late.append((paid - due).days)
        elif row["status"] in OPEN_STATUSES:
            open_amount += float(row.get("due_amount") or 0)
            if due and due < as_of:
                overdue_open += 1

    paid_count = len(days_late)
    return {
        "client_name": name,
        "client_email": email,
        "paid_count": paid_count,
        "late_count": sum(1 for d in days_late if d > 0),
        "avg_days_late": (sum(days_late) / paid_count) if paid_count else 0.0,
        "overdue_open": overdue_open,
        "open_amount": round(open_amount, 2),
    }


def score_client(history):
    reasons = []
    paid_count = history["paid_count"]

    if paid_count == 0:
        score = 35
        reasons.append("No payment history yet, so the score starts at a cautious 35.")
    else:
        score = 10
        avg = history["avg_days_late"]
        if avg > 0:
            score += min(40, round(avg * 2))
            reasons.append(f"Pays {avg:.1f} days late on average.")
        else:
            reasons.append(
                f"Pays on time or early ({abs(avg):.1f} days early on average)."
            )
        if history["late_count"]:
            ratio = history["late_count"] / paid_count
            score += round(30 * ratio)
            reasons.append(
                f"{history['late_count']} of {paid_count} paid invoices were late."
            )

    if history["overdue_open"]:
        score += min(30, 15 * history["overdue_open"])
        reasons.append(
            f"{history['overdue_open']} open invoice(s) already past due."
        )

    score = max(0, min(100, score))
    level = "LOW" if score < 25 else "MEDIUM" if score < 55 else "HIGH"
    return {"score": score, "level": level, "reasons": reasons}


def risk_for(rows, email, as_of):
    history = build_history(rows, email, as_of)
    return {**history, **score_client(history)}


def client_risk_report(as_of=None):
    as_of_date = parse_as_of(as_of)
    _refresh_state(include_open=False)
    rows = database.list_invoices()

    emails = []
    for row in rows:
        key = _client_key(row)
        if key and key not in emails:
            emails.append(key)

    report = [risk_for(rows, email, as_of_date) for email in emails]
    report.sort(key=lambda item: item["score"], reverse=True)
    return {"as_of": as_of_date.isoformat(), "clients": report}


# ---------- decisions ----------


def decide(row, risk, as_of, stats):
    """Return {"action", "tone", "reason", "days_overdue"} for one open invoice."""
    level = risk["level"]
    due = _to_date(row.get("due_date"))
    if due is None:
        return {
            "action": "SKIP",
            "tone": None,
            "reason": "Invoice has no due date.",
            "days_overdue": None,
        }

    days_overdue = (as_of - due).days
    count = stats["count"]
    lead = LEAD_DAYS[level]

    def result(action, tone, reason):
        return {
            "action": action,
            "tone": tone,
            "reason": reason,
            "days_overdue": days_overdue,
        }

    if days_overdue < -lead:
        return result(
            "WAIT",
            None,
            f"Due in {-days_overdue} days. For a {level.lower()}-risk client the "
            f"first heads-up goes out {lead} days before the due date.",
        )

    if days_overdue <= 0:
        if count > 0:
            return result(
                "SKIP",
                None,
                "A reminder was already sent. The agent will follow up after the due date.",
            )
        when = "today" if days_overdue == 0 else f"in {-days_overdue} days"
        return result("REMIND", "friendly", f"Due {when} and no reminder sent yet: friendly heads-up.")

    # Overdue from here on.
    if count >= MAX_REMINDERS:
        return result(
            "ESCALATE",
            None,
            f"{count} reminders sent and still unpaid. This needs a human follow-up, "
            "like a call or a direct message.",
        )

    last_at = _to_date(stats.get("last_at"))
    if last_at is not None:
        since_last = (as_of - last_at).days
        gap = GAP_DAYS[level]
        if since_last < gap:
            return result(
                "SKIP",
                None,
                f"Last reminder was {max(since_last, 0)} day(s) ago. For a "
                f"{level.lower()}-risk client the agent waits {gap} days between reminders.",
            )

    if days_overdue >= 14:
        tone = "final"
    elif days_overdue >= 7 or level == "HIGH":
        tone = "firm"
    elif level == "MEDIUM" and days_overdue >= 3:
        tone = "firm"
    else:
        tone = "friendly"

    return result(
        "REMIND",
        tone,
        f"{days_overdue} day(s) overdue and the client is {level.lower()} risk: "
        f"{tone} reminder.",
    )


# ---------- message writing ----------


def _first_name(row):
    full = (row.get("client_name") or "").strip()
    return full.split()[0] if full else "there"


def _template(tone, row, days_overdue):
    name = _first_name(row)
    number = row["invoice_number"]
    amount = f"{row['due_amount']} {row['currency']}"
    due = row["due_date"]

    if tone == "final":
        subject = f"Final reminder: invoice {number} is overdue"
        note = (
            f"Hello {name},\n\nThis is a final reminder that invoice {number} for "
            f"{amount}, due on {due}, is still unpaid. Please arrange payment as soon "
            "as possible, or reply if there is a problem.\n\nThank you."
        )
    elif tone == "firm":
        subject = f"Overdue: invoice {number} needs payment"
        note = (
            f"Hello {name},\n\nInvoice {number} for {amount} was due on {due} and is "
            "now overdue. Please complete the payment this week, or let me know if "
            "anything is blocking it.\n\nThank you."
        )
    elif days_overdue <= 0:
        subject = f"Friendly reminder: invoice {number} is due soon"
        note = (
            f"Hello {name},\n\nJust a heads-up that invoice {number} for {amount} is "
            f"due on {due}. Let me know if you need anything from my side.\n\nThank you."
        )
    else:
        subject = f"Friendly reminder: invoice {number}"
        note = (
            f"Hello {name},\n\nInvoice {number} for {amount} was due on {due} and may "
            "have slipped through. Please have a look when you can.\n\nThank you."
        )
    return {"subject": subject, "note": note}


def _extract_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model reply")
    return json.loads(text[start : end + 1])


def _ai_message(tone, row, days_overdue, reminders_sent):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY missing")

    facts = {
        "client_first_name": _first_name(row),
        "invoice_number": row["invoice_number"],
        "amount_due": row["due_amount"],
        "currency": row["currency"],
        "due_date": row["due_date"],
        "days_overdue": days_overdue,
        "reminders_already_sent": reminders_sent,
        "tone": tone,
    }
    system = (
        "You write short payment reminder emails on behalf of a freelancer or small "
        "business. Reply with ONLY a JSON object with the keys \"subject\" and "
        "\"note\", and nothing else. Rules: use only the facts provided; never invent "
        "fees, interest, deadlines, legal action or names; never mention risk scores or "
        "internal rules; plain text with no markdown; the note is under 70 words, "
        "starts with 'Hello <first name>,' and ends with 'Thank you.'. A negative "
        "days_overdue means the invoice is not due yet. Tone guide: "
        + TONE_GUIDE[tone]
    )

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(facts)},
        ],
        temperature=0.3,
        max_tokens=1024,
    )
    data = _extract_json(response.choices[0].message.content or "")
    subject = str(data["subject"]).strip()[:120]
    note = str(data["note"]).strip()[:800]
    if not subject or not note:
        raise ValueError("empty subject or note")
    return {"subject": subject, "note": note}


def compose_message(row, decision, reminders_sent):
    tone = decision["tone"]
    days_overdue = decision["days_overdue"]
    try:
        message = _ai_message(tone, row, days_overdue, reminders_sent)
        message["source"] = "ai"
    except (GroqError, ValueError, KeyError, TypeError):
        message = _template(tone, row, days_overdue)
        message["source"] = "template"
    return message


# ---------- the run ----------


def run(execute=False, as_of=None, actor="agent"):
    """Review every open invoice and decide what to do.

    execute=False is a preview: nothing is sent and nothing is logged.
    execute=True sends the reminders the agent decided on.
    """
    as_of_date = parse_as_of(as_of)
    _refresh_state(include_open=True)
    rows = database.list_invoices()

    risk_cache = {}
    decisions = []

    for row in rows:
        if row["status"] not in OPEN_STATUSES:
            continue

        email = _client_key(row)
        if email not in risk_cache:
            risk_cache[email] = risk_for(rows, email, as_of_date)
        risk = risk_cache[email]

        stats = database.reminder_stats(row["invoice_id"])
        decision = decide(row, risk, as_of_date, stats)

        item = {
            "invoice_id": row["invoice_id"],
            "invoice_number": row["invoice_number"],
            "client_name": row["client_name"],
            "client_email": row["client_email"],
            "total": row["total"],
            "due_amount": row["due_amount"],
            "currency": row["currency"],
            "due_date": row["due_date"],
            "days_overdue": decision["days_overdue"],
            "action": decision["action"],
            "tone": decision["tone"],
            "reason": decision["reason"],
            "risk_score": risk["score"],
            "risk_level": risk["level"],
            "reminders_sent": stats["count"],
            "message": None,
            "sent": False,
            "error": None,
        }

        if decision["action"] == "REMIND":
            item["message"] = compose_message(row, decision, stats["count"])
            if execute:
                try:
                    services.send_reminder(
                        row["invoice_id"],
                        subject=item["message"]["subject"],
                        note=item["message"]["note"],
                        actor=actor,
                        extra={
                            "tone": decision["tone"],
                            "risk_level": risk["level"],
                            "risk_score": risk["score"],
                            "message_source": item["message"]["source"],
                            "as_of": as_of_date.isoformat(),
                        },
                    )
                    item["sent"] = True
                except services.ServiceError as exc:
                    item["error"] = exc.message
                except PayPalError as exc:
                    item["error"] = f"PayPal error {exc.status_code}"

        elif decision["action"] == "ESCALATE" and execute:
            database.log_activity(
                actor,
                "collections_escalate",
                row["invoice_id"],
                {
                    "reason": decision["reason"],
                    "risk_level": risk["level"],
                    "as_of": as_of_date.isoformat(),
                },
            )

        decisions.append(item)

    decisions.sort(
        key=lambda d: d["days_overdue"] if d["days_overdue"] is not None else -9999,
        reverse=True,
    )

    summary = {
        "reviewed": len(decisions),
        "remind": sum(1 for d in decisions if d["action"] == "REMIND"),
        "wait": sum(1 for d in decisions if d["action"] == "WAIT"),
        "skip": sum(1 for d in decisions if d["action"] == "SKIP"),
        "escalate": sum(1 for d in decisions if d["action"] == "ESCALATE"),
        "sent": sum(1 for d in decisions if d["sent"]),
        "errors": sum(1 for d in decisions if d["error"]),
    }

    if execute:
        database.log_activity(
            actor,
            "collections_run",
            None,
            {**summary, "as_of": as_of_date.isoformat()},
        )

    clients = sorted(risk_cache.values(), key=lambda c: c["score"], reverse=True)
    return {
        "as_of": as_of_date.isoformat(),
        "executed": bool(execute),
        "summary": summary,
        "decisions": decisions,
        "clients": clients,
    }