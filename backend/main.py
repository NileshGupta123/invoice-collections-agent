"""FastAPI app: REST endpoints for the invoice dashboard and the agent."""

from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend import agent, collections_engine, database, services
from backend.paypal_client import PayPalError


@asynccontextmanager
async def lifespan(app):
    database.init_db()
    yield


app = FastAPI(title="AI Invoice and Collections Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class InvoiceItem(BaseModel):
    name: str
    description: str = ""
    quantity: float = Field(1, gt=0)
    unit_amount: float = Field(..., gt=0)


class InvoiceCreate(BaseModel):
    client_name: str
    client_email: str
    items: List[InvoiceItem] = Field(..., min_length=1)
    currency: str = "USD"
    note: Optional[str] = None
    payment_term: str = "NET_10"


class ReminderRequest(BaseModel):
    subject: Optional[str] = None
    note: Optional[str] = None


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: List[ChatTurn] = Field(default_factory=list)


class CollectionsRunRequest(BaseModel):
    execute: bool = False
    as_of: Optional[str] = None


@app.exception_handler(PayPalError)
async def paypal_error_handler(request, exc):
    return JSONResponse(
        status_code=502,
        content={
            "error": "paypal_error",
            "paypal_status": exc.status_code,
            "details": exc.payload,
        },
    )


@app.exception_handler(services.ServiceError)
async def service_error_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code, content={"error": exc.message}
    )


@app.exception_handler(agent.AgentError)
async def agent_error_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code, content={"error": exc.message}
    )


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/invoices/sync")
def sync_invoices():
    return services.sync_all()


@app.get("/invoices")
def list_invoices():
    return {"invoices": database.list_invoices()}


@app.post("/invoices", status_code=201)
def create_invoice(payload: InvoiceCreate):
    return services.create_draft_invoice(
        client_name=payload.client_name,
        client_email=payload.client_email,
        items=[item.model_dump() for item in payload.items],
        currency=payload.currency,
        note=payload.note,
        payment_term=payload.payment_term,
    )


@app.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: str):
    row = services.refresh_invoice(invoice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return row


@app.post("/invoices/{invoice_id}/approve-send")
def approve_send(invoice_id: str):
    return services.approve_and_send(invoice_id)


@app.post("/invoices/{invoice_id}/remind")
def remind(invoice_id: str, payload: Optional[ReminderRequest] = None):
    payload = payload or ReminderRequest()
    return services.send_reminder(
        invoice_id, subject=payload.subject, note=payload.note
    )


@app.post("/collections/run")
def run_collections(payload: CollectionsRunRequest):
    return collections_engine.run(
        execute=payload.execute, as_of=payload.as_of, actor="agent"
    )


@app.get("/clients/risk")
def clients_risk(as_of: Optional[str] = None):
    return collections_engine.client_risk_report(as_of=as_of)


@app.post("/agent/chat")
def agent_chat(payload: ChatRequest):
    return agent.chat(
        payload.message,
        history=[turn.model_dump() for turn in payload.history],
    )


@app.get("/activity")
def activity(limit: int = 50):
    return {"activity": database.list_activity(limit)}