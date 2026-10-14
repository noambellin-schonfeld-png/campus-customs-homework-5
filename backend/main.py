"""FastAPI routes for the Campus Customs dashboard and human approvals."""

from __future__ import annotations

import asyncio
import calendar
import json
import shutil
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp_server.mcp_server import (
    DB_PATH,
    get_cash_accounts,
    list_pending_approval_requests,
    list_tickets,
    mark_ticket_resolved,
)

ORIGINAL_DB_PATH = PROJECT_ROOT / "data" / "campus_customs.db"
AUDIT_PATH = PROJECT_ROOT / "output" / "audit_trail.json"

app = FastAPI(title="Campus Customs Operations API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

_write_lock = asyncio.Lock()
_active_ticket_runs: set[int] = set()


class ApprovalBody(BaseModel):
    approved_by: str = Field(min_length=1, max_length=120)


def _connect_working_db() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise HTTPException(status_code=500, detail="Working database is missing.")
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def _money(value: float) -> int:
    """Convert a database dollar amount to integer cents for comparisons."""
    return round(float(value) * 100)


def _next_month(value: str) -> str:
    due = date.fromisoformat(value)
    month = due.month + 1
    year = due.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(due.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


@app.get("/api/tickets")
def get_tickets() -> dict[str, Any]:
    """Return all board tickets, including ones already resolved."""
    tickets = list_tickets()
    for ticket in tickets:
        ticket["resolved"] = str(ticket["status"]).lower() in {"resolved", "closed"}
    return {"tickets": tickets}


@app.post("/api/tickets/{ticket_id}/run")
async def run_ticket_agents(ticket_id: int) -> dict[str, Any]:
    """Run the Boss team for a single known, unresolved ticket."""
    tickets = list_tickets()
    ticket = next((row for row in tickets if int(row["id"]) == ticket_id), None)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if str(ticket["status"]).lower() in {"resolved", "closed"}:
        raise HTTPException(status_code=409, detail="Ticket is already resolved.")
    if ticket_id in _active_ticket_runs:
        raise HTTPException(status_code=409, detail="This ticket is already being processed.")

    _active_ticket_runs.add(ticket_id)
    try:
        from backend.agents import run_ticket

        result = await run_ticket(ticket_id)
        response = result.model_dump(mode="json")
        # A finished model loop means the agents returned; it does not mean the
        # business ticket is resolved. Only the MCP status tool can close it.
        resolved_by_agent = any(
            event.kind == "tool_call"
            and event.details.get("tool") == "mark_ticket_resolved"
            for event in result.events
        )
        if result.status == "complete" and resolved_by_agent:
            resolution = mark_ticket_resolved(ticket_id)
            response["ticket_status"] = resolution.get("status", "open")
        else:
            response["ticket_status"] = "open"
        return response
    finally:
        _active_ticket_runs.discard(ticket_id)


@app.get("/api/events")
def get_recent_events(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    """Return the latest audit events, including agent text and MCP tool calls."""
    if not AUDIT_PATH.exists():
        return {"events": [], "count": 0}
    try:
        events = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not read the audit trail: {exc}")
    if not isinstance(events, list):
        raise HTTPException(status_code=500, detail="The audit trail must be a JSON array.")
    recent = events[-limit:]
    return {"events": recent, "count": len(recent)}


@app.get("/api/approvals")
def get_pending_approvals() -> dict[str, Any]:
    """Return queued human decisions so the dashboard can render approval controls."""
    requests = list_pending_approval_requests()
    return {"approvals": requests, "count": len(requests)}


@app.post("/api/approvals/{approval_id}/approve")
async def approve_request(approval_id: int, body: ApprovalBody) -> dict[str, Any]:
    """Execute a pending payment or purchase only after an explicit human approval."""
    approved_by = body.approved_by.strip()
    if not approved_by:
        raise HTTPException(status_code=422, detail="approved_by cannot be blank.")

    async with _write_lock:
        conn = _connect_working_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if not _table_exists(conn, "approval_requests"):
                raise HTTPException(status_code=404, detail="Approval request not found.")
            request = conn.execute(
                "SELECT * FROM approval_requests WHERE id = ?", (approval_id,)
            ).fetchone()
            if request is None:
                raise HTTPException(status_code=404, detail="Approval request not found.")
            if request["status"] != "pending":
                raise HTTPException(status_code=409, detail="This request is no longer pending.")

            account = request["account"] or "checking"
            cash = conn.execute(
                "SELECT balance FROM cash_accounts WHERE name = ?", (account,)
            ).fetchone()
            if cash is None:
                raise HTTPException(status_code=409, detail="The request's cash account is missing.")
            if _money(request["amount"]) > _money(cash["balance"]):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Insufficient cash; no payment was made.",
                        "requested": float(request["amount"]),
                        "available": float(cash["balance"]),
                    },
                )

            desk = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
            if desk is None or not desk["date_today"]:
                raise HTTPException(status_code=409, detail="Shop date is missing.")
            shop_date = date.fromisoformat(desk["date_today"]).isoformat()
            amount = float(request["amount"])
            action_type = request["action_type"]

            if action_type == "payment":
                kind, reference_id = _validate_obligation(conn, request)
                if kind == "invoice":
                    updated = conn.execute(
                        "UPDATE invoices SET status = 'paid' WHERE id = ? AND LOWER(status) = 'open'",
                        (reference_id,),
                    ).rowcount
                    if updated != 1:
                        raise HTTPException(status_code=409, detail="Invoice is no longer open.")
                else:
                    lease = conn.execute(
                        "SELECT next_due FROM leases WHERE id = ?", (reference_id,)
                    ).fetchone()
                    conn.execute(
                        "UPDATE leases SET next_due = ? WHERE id = ?",
                        (_next_month(lease["next_due"]), reference_id),
                    )
                    conn.execute(
                        "UPDATE tickets SET status = 'resolved' WHERE id = ?",
                        (request["ticket_id"],),
                    )
                payment_ref_id = reference_id
            elif action_type == "purchase_order":
                _validate_purchase_order(conn, request)
                kind = "purchase_order"
                payment_ref_id = approval_id
                # A purchase order is the ticket's approved operational action.
                # The inventory remains unchanged until receipt is modeled.
                conn.execute(
                    "UPDATE tickets SET status = 'resolved' WHERE id = ?",
                    (request["ticket_id"],),
                )
            else:
                raise HTTPException(status_code=409, detail="Unsupported approval action.")

            conn.execute(
                "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (kind, payment_ref_id, amount, account, shop_date, approved_by),
            )
            conn.execute(
                "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
                (round(float(cash["balance"]) - amount, 2), shop_date, account),
            )
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            conn.execute(
                "UPDATE approval_requests SET status = 'executed', approved_by = ?, "
                "approved_at = ? WHERE id = ? AND status = 'pending'",
                (approved_by, timestamp, approval_id),
            )
            conn.commit()
            return {
                "approved": True,
                "approval_id": approval_id,
                "action_type": action_type,
                "amount_paid": amount,
                "account": account,
                "remaining_balance": round(float(cash["balance"]) - amount, 2),
                "status": "executed",
                "approved_by": approved_by,
                "paid_at": shop_date,
            }
        except HTTPException:
            conn.rollback()
            raise
        except (sqlite3.Error, ValueError, TypeError) as exc:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Approval failed: {exc}") from exc
        finally:
            conn.close()


def _validate_obligation(conn: sqlite3.Connection, request: sqlite3.Row) -> tuple[str, int]:
    reference_type = request["reference_type"]
    reference_id = request["reference_id"]
    ticket = conn.execute(
        "SELECT invoice_id, lease_id FROM tickets WHERE id = ?", (request["ticket_id"],)
    ).fetchone()
    if ticket is None:
        raise HTTPException(status_code=409, detail="The request's ticket no longer exists.")
    if reference_type == "invoice" and reference_id is not None:
        if ticket["invoice_id"] != reference_id:
            raise HTTPException(status_code=409, detail="Invoice does not match the request ticket.")
        invoice = conn.execute(
            "SELECT amount, status FROM invoices WHERE id = ?", (reference_id,)
        ).fetchone()
        if invoice is None or invoice["status"].lower() != "open":
            raise HTTPException(status_code=409, detail="Invoice is missing or is no longer open.")
        if _money(invoice["amount"]) != _money(request["amount"]):
            raise HTTPException(status_code=409, detail="Invoice amount changed after approval was requested.")
        return "invoice", int(reference_id)
    if reference_type == "lease" and reference_id is not None:
        if ticket["lease_id"] != reference_id:
            raise HTTPException(status_code=409, detail="Lease does not match the request ticket.")
        lease = conn.execute(
            "SELECT monthly_rent FROM leases WHERE id = ?", (reference_id,)
        ).fetchone()
        if lease is None or _money(lease["monthly_rent"]) != _money(request["amount"]):
            raise HTTPException(status_code=409, detail="Lease amount changed after approval was requested.")
        return "lease", int(reference_id)
    raise HTTPException(status_code=409, detail="Payment reference is invalid.")


def _validate_purchase_order(conn: sqlite3.Connection, request: sqlite3.Row) -> None:
    ticket = conn.execute(
        "SELECT sku, size, qty FROM tickets WHERE id = ?", (request["ticket_id"],)
    ).fetchone()
    if ticket is None or ticket["sku"] != request["sku"] or ticket["size"] != request["size"]:
        raise HTTPException(status_code=409, detail="Purchase item no longer matches its ticket.")
    if not request["quantity"] or int(request["quantity"]) <= 0:
        raise HTTPException(status_code=409, detail="Purchase quantity is invalid.")
    stock = conn.execute(
        "SELECT qty FROM inventory WHERE sku = ? AND size = ?",
        (request["sku"], request["size"]),
    ).fetchone()
    price = conn.execute(
        "SELECT unit_cost FROM pricing WHERE sku = ?", (request["sku"],)
    ).fetchone()
    if stock is None or price is None:
        raise HTTPException(status_code=409, detail="Purchase item facts are missing.")
    shortfall = max(int(ticket["qty"] or 0) - int(stock["qty"]), 0)
    if int(request["quantity"]) > shortfall:
        raise HTTPException(status_code=409, detail="Purchase quantity now exceeds the shortfall.")
    vendor = conn.execute(
        "SELECT id FROM vendors WHERE id = ?", (request["vendor_id"],)
    ).fetchone()
    if vendor is None:
        raise HTTPException(status_code=409, detail="Purchase vendor is missing.")
    blocker = conn.execute(
        "SELECT 1 FROM invoices WHERE vendor_id = ? AND LOWER(status) = 'open' LIMIT 1",
        (request["vendor_id"],),
    ).fetchone()
    if blocker is not None:
        raise HTTPException(status_code=409, detail="Vendor has an open unpaid invoice.")
    expected = _money(price["unit_cost"]) * int(request["quantity"])
    if expected != _money(request["amount"]):
        raise HTTPException(status_code=409, detail="Purchase amount changed after approval was requested.")


@app.get("/api/cash")
def get_checking_balance() -> dict[str, Any]:
    """Return the checking balance using the MCP server's cash lookup."""
    accounts = get_cash_accounts()
    checking = next((account for account in accounts if account["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(status_code=404, detail="Checking account not found.")
    return checking


@app.post("/api/reset")
async def reset_working_database() -> dict[str, str]:
    """Restore the working database from the untouched original assignment file."""
    async with _write_lock:
        if _active_ticket_runs:
            raise HTTPException(
                status_code=409,
                detail="Wait for active ticket runs to finish before resetting.",
            )
        if not ORIGINAL_DB_PATH.is_file():
            raise HTTPException(status_code=500, detail="Original reset database is missing.")
        temporary_path = DB_PATH.with_suffix(".db.reset.tmp")
        try:
            shutil.copy2(ORIGINAL_DB_PATH, temporary_path)
            temporary_path.replace(DB_PATH)
        except OSError as exc:
            temporary_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"Database reset failed: {exc}") from exc
    return {"reset": "ok", "database": "data/campus_customs_new.db"}
