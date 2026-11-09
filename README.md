# Invoice and Collections Agent

An AI agent that drafts PayPal invoices, scores how risky each client is to chase, and decides when and how firmly to send payment reminders. The agent can draft and remind, but **it can never send an invoice**: a human has to click Approve and Send.

Built for the **PayPal AI Hackathon** ("Build what's next with PayPal and AI"). Everything runs against the **PayPal sandbox**. No real money moves.

- **Hosted demo:** https://invoice-agent-web.onrender.com
- **API docs:** https://invoice-agent-api-ni51.onrender.com/docs
- **Demo video:** ADD_YOUTUBE_LINK_HERE
- **License:** MIT

> The hosted demo runs on Render's free tier. After 15 minutes without traffic the backend sleeps, so the first request can take 30 to 60 seconds. If the page looks empty, wait a minute and refresh.

## The problem

Freelancers and small businesses lose time and cash chasing late payments. Deciding who to remind, when, and in what tone takes judgement, and it is easy to be too soft, too pushy or to forget entirely.

## What it does

| Feature | What happens |
|---|---|
| **Agent chat** | Ask in plain language ("Invoice Maya 400 dollars for a landing page"). The agent drafts the invoice through PayPal. |
| **Approval Inbox** | Drafts wait here. Only a human can click **Approve and Send**. The agent has no tool to send invoices. |
| **Client risk score** | Each client gets a 0 to 100 score from their payment history: days late on past invoices, how often they were late, and how many invoices are overdue now. |
| **Adaptive collections** | For every unpaid invoice the agent decides: `WAIT`, `REMIND`, `SKIP` or `ESCALATE`, and picks a `friendly`, `firm` or `final` tone. Every decision comes with a plain-language reason. |
| **Reminder writing** | The AI model writes the reminder subject and message for the chosen tone. A template is used if the model is unavailable. |
| **Preview and Run** | Preview shows what the agent would do and sends nothing. Run now sends the reminders. |
| **Date simulator** | Decide as if it were a later date, so the escalating tone can be shown without waiting days. |
| **Activity log** | Every action, who did it (agent, user or system), tone and subject. |

## How the agent makes decisions

Money decisions are **rule-based and explainable**. The AI model only writes the message text.

**Risk score (0 to 100)**

- No payment history: starts at a cautious 35.
- With history: starts at 10, plus up to 40 points for the average days late (2 points per day), plus up to 30 points for the share of invoices that were late.
- Each open invoice already past due adds 15 points (capped at 30).
- Levels: `LOW` below 25, `MEDIUM` below 55, `HIGH` otherwise.

**Reminder rules for each unpaid invoice**

| Situation | Decision |
|---|---|
| Due date is far away (more than 2 / 3 / 5 days for LOW / MEDIUM / HIGH risk) | `WAIT` |
| Due soon or today, no reminder sent yet | `REMIND`, friendly heads-up |
| Overdue, but the last reminder was too recent (gap of 7 / 5 / 3 days for LOW / MEDIUM / HIGH) | `SKIP` (no spam) |
| Overdue, 14 or more days | `REMIND`, `final` tone |
| Overdue, 7 or more days, or HIGH risk | `REMIND`, `firm` tone |
| Overdue, MEDIUM risk, 3 or more days | `REMIND`, `firm` tone |
| Otherwise overdue | `REMIND`, `friendly` tone |
| Already reminded 4 times and still unpaid | `ESCALATE` (needs a human: call or direct message) |

## Guardrails

- The agent has **no send-invoice tool**. Sending only happens through the Approve and Send button, which calls a separate endpoint.
- Only a `DRAFT` invoice can be sent. Sending an already sent invoice returns `409 Conflict`.
- Reminders are only allowed for unpaid, already sent invoices.
- The agent is told never to invent a client email. A tool-side check rejects drafts without a valid email.
- Reminder messages are written from known facts only (amount, due date, days overdue). The prompt forbids fees, interest and legal threats.
- `ESCALATE` makes the agent stop and hand over to a human instead of reminding forever.
- Every action is written to the activity log with its actor.

## Architecture

```
React dashboard (Vite + Tailwind)
        |
        v
FastAPI backend  ----  Groq (openai/gpt-oss-20b): tool-calling agent + message writing
        |
        +---- collections_engine.py: risk scoring and decisions (rule-based)
        +---- SQLite: invoices, activity log
        |
        v
PayPal Invoicing API (sandbox)
```

## Tools used

- **PayPal Invoicing API (sandbox):** generate invoice number, create, send, get, list, remind, cancel, record payment. Also OAuth 2.0 client credentials.
- **Groq API** with the `openai/gpt-oss-20b` model: tool-calling agent and reminder text.
- **FastAPI, SQLite, React, Vite, Tailwind CSS.**
- **Render:** hosts the API (web service) and the dashboard (static site) from `render.yaml`.

## Project structure

```
backend/
  agent.py               Groq tool-calling agent (6 tools, no send tool)
  collections_engine.py  risk score, decisions, message writing, run
  database.py            SQLite storage
  main.py                FastAPI routes
  paypal_client.py       PayPal Invoicing API client
  services.py            shared business rules (approval, reminders, sync)
frontend/                React dashboard
scripts/
  seed_demo.py           creates demo clients and payment history in the sandbox
  test_auth.py, test_invoice.py, check_invoice.py, check_scopes.py   PayPal sandbox checks
render.yaml              Render blueprint (API and dashboard)
```

## Run it locally

### 1. Requirements

- Python 3.12 and Node.js 20 or newer
- A PayPal developer account with a **sandbox** app
- A free Groq API key (console.groq.com)

### 2. PayPal sandbox setup

1. Open developer.paypal.com, switch to **Sandbox**, then **Apps and Credentials**, and create a **Merchant** app.
2. In the app's **Features**, tick **Invoicing** and **Transaction search**, then save.
3. Use a sandbox **Business** account located in the **United States** for the app.
4. Copy the sandbox **Client ID** and **Secret**.
5. Run `python scripts/check_scopes.py` after step 4 below. It should print `Invoicing scope mila: True`.

### 3. Configure

```
cp .env.example .env
```

Fill in `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` and `GROQ_API_KEY`. On Windows PowerShell use `Copy-Item .env.example .env`.

### 4. Start the backend

```
python -m venv venv
venv\Scripts\Activate.ps1        # Windows PowerShell
# source venv/bin/activate       # macOS and Linux
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

The API is now at http://127.0.0.1:8000 and its docs at http://127.0.0.1:8000/docs.

### 5. Start the dashboard

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### 6. Optional: demo data

```
python -m scripts.seed_demo
```

This creates four demo clients with different payment histories (on time, late, mixed, brand new) in your sandbox, so the risk scores and tones differ. It also cancels older open test invoices. Run it once.

### 7. Try it

1. In the chat, type `Create an invoice for <name> (<email>) for 1 logo design at $200, net 10`. A draft appears in the **Approval Inbox**.
2. Type `Send that invoice now`. The agent refuses and points you to the Approval Inbox.
3. Click **Approve and Send**. The invoice is sent through PayPal and shows as `SENT`.
4. In **Collections agent**, click **Preview**, pick a later **Simulate date**, and watch the tone move from friendly to firm to final.
5. Click **Run now** to send the reminders. The activity log records each one with its tone.

### Paying an invoice as the buyer

Sending invoices to the fake demo-client emails works, but only a real sandbox buyer can pay one. To see a payment:

1. Create a sandbox **Personal** account (also US-based) and draft an invoice to its email.
2. Open an **incognito window** and go to www.sandbox.paypal.com.
3. Open the invoice link and pay with that Personal account. Paying with the Business account fails with `CANNOT_PAY_SELF`.
4. Click **Sync with PayPal** in the dashboard. The invoice becomes `PAID`.

## Known limitations

- **Sandbox only.** No real payments.
- **US sandbox merchant.** In our testing the Invoicing permission was not granted to an app linked to India-based sandbox accounts, so the demo uses a US-based sandbox business account.
- **Fake client emails.** Demo clients use `example.com` addresses. Reminders go to the PayPal sandbox, not to real inboxes.
- **No sign-in.** The demo has no user accounts. It is meant for sandbox data only.
- **Free hosting.** The SQLite file is wiped when Render restarts the service. On startup the app re-imports invoices from PayPal, but the local activity log and reminder counts start over.
- **Polling, not webhooks.** Payment status updates when the dashboard syncs or an action refreshes an invoice.
- **Date simulation** only changes how decisions are made. Invoice dates in PayPal do not change.

## License

MIT. See [LICENSE](LICENSE).