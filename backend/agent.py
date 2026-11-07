"""Groq tool-calling agent for invoicing and collections.

The agent can draft invoices, send reminders and run adaptive collections, but it
can NOT send an invoice: that stays a human approval step in the Approval Inbox.
"""

import json
import os
from datetime import date

from dotenv import load_dotenv
from groq import Groq, GroqError

from backend import collections_engine, database, services
from backend.paypal_client import PayPalError

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
MAX_TOOL_ROUNDS = 6
MAX_HISTORY = 12

FINAL_STATUSES = {
    "PAID",
    "MARKED_AS_PAID",
    "CANCELLED",
    "REFUNDED",
    "MARKED_AS_REFUNDED",
}

PAYMENT_TERMS = [
    "DUE_ON_RECEIPT",
    "NET_10",
    "NET_15",
    "NET_30",
    "NET_45",
    "NET_60",
    "NET_90",
]


class AgentError(Exception):
    def __init__(self, message, status_code=502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def build_system_prompt():
    today = date.today().isoformat()
    return f"""You are an invoicing and collections assistant for a freelancer or small business. Today's date is {today}.

You work with PayPal invoices through tools. Rules:
1. You can DRAFT invoices but you can NOT send them. A drafted invoice appears in the Approval Inbox of this app, where the user reviews it and clicks "Approve and Send". After drafting, tell the user the draft is waiting in the Approval Inbox. If the user asks you to send an invoice, explain that you cannot send invoices yourself and that they need to approve it in the Approval Inbox. Never say an invoice was sent unless its status is SENT.
2. Never call create_draft_invoice unless the user has given you the client's real email address. If the email is missing, ask for it first and do NOT call any tool. Never invent or guess an email. Default currency is USD and default payment term is NET_10 unless the user says otherwise.
3. Before sending a single reminder, check the invoice status. Only send reminders for invoices that are SENT, UNPAID, PARTIALLY_PAID or PAYMENT_PENDING. Never remind a PAID or DRAFT invoice.
4. Write the reminder subject and note yourself. If the invoice is not yet overdue (days_overdue is zero or negative), be warm and friendly. If it is overdue, be polite but firm and mention the due date and the amount. Keep notes under 60 words and sign off without inventing a personal name.
5. Invoices can be referred to by invoice number (like 0002) or by invoice_id. Use list_invoices if you are unsure which invoice the user means.
6. For requests about chasing, following up on, or reviewing all unpaid or overdue invoices, use run_collections instead of sending reminders one by one. Call it with execute=false to preview what it would do, and only set execute=true when the user clearly asks to send or run it now. After the call, explain each decision in plain language: the action, the tone, the client's risk level and why. Never claim reminders were sent unless the result shows sent=true.
7. For questions about how reliable a client is or which clients are risky, use get_client_risk and explain the reasons it returns.
8. Be concise. After using tools, summarise what you did and the current status in plain language. If a tool returns an error, explain it simply and do not retry the same call repeatedly."""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_invoices",
            "description": "List all invoices with their latest status, amounts, due dates and days overdue.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_invoice_status",
            "description": "Get the latest status of one invoice from PayPal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice": {
                        "type": "string",
                        "description": "Invoice number like 0002 or an invoice_id like INV2-XXXX-XXXX-XXXX-XXXX.",
                    }
                },
                "required": ["invoice"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_draft_invoice",
            "description": "Create a DRAFT invoice. It is not sent to the client until a human approves it. Only call this when you have the client's real email address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string"},
                    "client_email": {"type": "string"},
                    "items": {
                        "type": "array",
                        "description": "Line items on the invoice.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "quantity": {"type": "number"},
                                "unit_amount": {"type": "number"},
                            },
                            "required": ["name", "quantity", "unit_amount"],
                        },
                    },
                    "currency": {"type": "string", "description": "3-letter code, default USD."},
                    "note": {"type": "string", "description": "Optional note shown on the invoice."},
                    "payment_term": {"type": "string", "enum": PAYMENT_TERMS},
                },
                "required": ["client_name", "client_email", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_reminder",
            "description": "Send a payment reminder email for one unpaid, already-sent invoice.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice": {
                        "type": "string",
                        "description": "Invoice number like 0002 or an invoice_id.",
                    },
                    "subject": {"type": "string", "description": "Reminder email subject."},
                    "note": {"type": "string", "description": "Reminder message to the client."},
                },
                "required": ["invoice", "subject", "note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_collections",
            "description": (
                "Review all unpaid invoices and decide for each one whether to wait, "
                "skip, send a reminder or escalate to a human, using each client's "
                "payment history and risk level. With execute=false it only previews "
                "the decisions and sends nothing. Set execute=true ONLY when the user "
                "explicitly asks to send or run the reminders now."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "execute": {
                        "type": "boolean",
                        "description": "false = preview only (default). true = actually send the reminders.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_client_risk",
            "description": "Get each client's payment-risk score (0-100), risk level and the reasons behind it, based on their payment history.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _days_overdue(row):
    due = row.get("due_date")
    if not due or row.get("status") in FINAL_STATUSES:
        return None
    try:
        return (date.today() - date.fromisoformat(due)).days
    except ValueError:
        return None


def _compact(row):
    keys = [
        "invoice_id",
        "invoice_number",
        "status",
        "client_name",
        "client_email",
        "currency",
        "total",
        "due_amount",
        "paid_amount",
        "due_date",
    ]
    data = {key: row.get(key) for key in keys}
    data["days_overdue"] = _days_overdue(row)
    return data


def _resolve_invoice_id(ref):
    ref = str(ref).strip()
    if ref.upper().startswith("INV2-"):
        return ref.upper()
    for row in database.list_invoices():
        if str(row.get("invoice_number")) == ref.lstrip("#"):
            return row["invoice_id"]
    raise ValueError(f"No invoice found for '{ref}'")


def tool_list_invoices(args):
    rows = database.list_invoices()
    if not rows:
        services.sync_all(actor="agent")
        rows = database.list_invoices()

    result = []
    for row in rows[:20]:
        if row["status"] not in FINAL_STATUSES:
            try:
                row = services.refresh_invoice(row["invoice_id"])
            except PayPalError:
                pass
        result.append(_compact(row))
    return {"count": len(result), "invoices": result}


def tool_get_invoice_status(args):
    invoice_id = _resolve_invoice_id(args["invoice"])
    return _compact(services.refresh_invoice(invoice_id))


def tool_create_draft_invoice(args):
    email = str(args.get("client_email", "")).strip()
    if "@" not in email:
        raise ValueError("client_email must be a valid email address")

    items = args.get("items") or []
    cleaned = []
    for item in items:
        cleaned.append(
            {
                "name": str(item["name"]),
                "description": str(item.get("description", "")),
                "quantity": float(item.get("quantity", 1)),
                "unit_amount": float(item["unit_amount"]),
            }
        )

    row = services.create_draft_invoice(
        client_name=str(args["client_name"]),
        client_email=email,
        items=cleaned,
        currency=str(args.get("currency") or "USD").upper(),
        note=args.get("note"),
        payment_term=args.get("payment_term") or "NET_10",
        actor="agent",
    )
    result = _compact(row)
    result["next_step"] = (
        "Draft only. It is waiting in the Approval Inbox, where a human must "
        "click Approve and Send."
    )
    return result


def tool_send_reminder(args):
    invoice_id = _resolve_invoice_id(args["invoice"])
    result = services.send_reminder(
        invoice_id,
        subject=args.get("subject"),
        note=args.get("note"),
        actor="agent",
    )
    return {
        "reminder_sent": result["reminder_sent"],
        "invoice": _compact(result["invoice"]),
    }


def tool_run_collections(args):
    execute = args.get("execute") is True
    result = collections_engine.run(execute=execute, actor="agent")

    decisions = []
    for d in result["decisions"]:
        decisions.append(
            {
                "invoice_number": d["invoice_number"],
                "client_name": d["client_name"],
                "due_date": d["due_date"],
                "days_overdue": d["days_overdue"],
                "action": d["action"],
                "tone": d["tone"],
                "reason": d["reason"],
                "risk_level": d["risk_level"],
                "risk_score": d["risk_score"],
                "reminders_sent": d["reminders_sent"],
                "subject": d["message"]["subject"] if d["message"] else None,
                "sent": d["sent"],
                "error": d["error"],
            }
        )
    return {
        "executed": result["executed"],
        "as_of": result["as_of"],
        "summary": result["summary"],
        "decisions": decisions,
    }


def tool_get_client_risk(args):
    report = collections_engine.client_risk_report()
    clients = []
    for c in report["clients"]:
        clients.append(
            {
                "client_name": c["client_name"],
                "client_email": c["client_email"],
                "risk_score": c["score"],
                "risk_level": c["level"],
                "reasons": c["reasons"],
                "paid_invoices": c["paid_count"],
                "open_amount": c["open_amount"],
            }
        )
    return {"as_of": report["as_of"], "clients": clients}


TOOL_FUNCTIONS = {
    "list_invoices": tool_list_invoices,
    "get_invoice_status": tool_get_invoice_status,
    "create_draft_invoice": tool_create_draft_invoice,
    "send_reminder": tool_send_reminder,
    "run_collections": tool_run_collections,
    "get_client_risk": tool_get_client_risk,
}


def run_tool(name, args):
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return {"error": f"Unknown tool '{name}'"}
    try:
        return func(args)
    except services.ServiceError as exc:
        return {"error": exc.message}
    except PayPalError as exc:
        return {
            "error": "PayPal rejected the request",
            "paypal_status": exc.status_code,
            "details": exc.payload,
        }
    except (ValueError, KeyError, TypeError) as exc:
        return {"error": f"Invalid arguments: {exc}"}


def _get_client():
    if not GROQ_API_KEY:
        raise AgentError("GROQ_API_KEY is missing in the .env file", 503)
    return Groq(api_key=GROQ_API_KEY)


def chat(message, history=None):
    """Run one user message through the agent loop.

    Returns {"reply": str, "actions": [{"tool", "arguments", "result"}, ...]}.
    """
    client = _get_client()

    messages = [{"role": "system", "content": build_system_prompt()}]
    for turn in (history or [])[-MAX_HISTORY:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    actions = []

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
                max_tokens=1024,
            )
        except GroqError as exc:
            raise AgentError(f"Groq request failed: {exc}")

        reply = response.choices[0].message

        if not reply.tool_calls:
            return {"reply": reply.content or "", "actions": actions}

        messages.append(
            {
                "role": "assistant",
                "content": reply.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments or "{}",
                        },
                    }
                    for call in reply.tool_calls
                ],
            }
        )

        for call in reply.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
                result = run_tool(name, args)
            except ValueError:
                args = {}
                result = {"error": "Tool arguments were not valid JSON"}

            actions.append({"tool": name, "arguments": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": name,
                    "content": json.dumps(result, default=str),
                }
            )

    return {
        "reply": "I stopped because the task needed too many steps. Please try a simpler request.",
        "actions": actions,
    }