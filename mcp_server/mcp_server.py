"""Campus Customs database tools exposed through FastMCP.

Read tools use the working database in read-only mode. The few write tools only
append ticket notes or create requests awaiting a human decision; there is no
agent-facing tool that sends messages or executes payments.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "campus_customs_new.db"

mcp = FastMCP("Campus Customs Operations")


def _connect_read_only() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Campus Customs working database not found: {DB_PATH}")
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _database() -> Any:
    conn = _connect_read_only()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _writable_database() -> Any:
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Campus Customs working database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _shop_date(conn: sqlite3.Connection) -> date | None:
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    if row is None or not row["date_today"]:
        return None
    return date.fromisoformat(row["date_today"])


def _ensure_approval_table(conn: sqlite3.Connection) -> None:
    """Add an approval queue to the working copy; never touch the reset database."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS approval_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            action_type TEXT NOT NULL CHECK (action_type IN ('payment', 'purchase_order')),
            reference_type TEXT,
            reference_id INTEGER,
            vendor_id INTEGER,
            sku TEXT,
            size TEXT,
            quantity INTEGER,
            amount REAL NOT NULL CHECK (amount >= 0),
            account TEXT,
            details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'executed')),
            created_at TEXT NOT NULL,
            approved_by TEXT,
            approved_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_approval_requests_status "
        "ON approval_requests(status, created_at)"
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@mcp.tool
def list_open_tickets() -> dict[str, Any]:
    """List unresolved board tickets with the shop's authoritative date."""
    with _database() as conn:
        shop_date = _shop_date(conn)
        rows = conn.execute(
            """
            SELECT id, type, requester, subject, sku, size, qty, lease_id,
                   invoice_id, status, notes, created_at
            FROM tickets
            WHERE LOWER(status) IN ('open', 'in_progress', 'waiting_approval')
            ORDER BY id
            """
        ).fetchall()
        return {
            "shop_date": shop_date.isoformat() if shop_date else None,
            "tickets": [dict(row) for row in rows],
        }


@mcp.tool
def list_tickets() -> list[dict[str, Any]]:
    """List every board ticket, including its current open/resolved status."""
    with _database() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """SELECT id, type, requester, subject, sku, size, qty, lease_id,
                          invoice_id, status, notes, created_at
                   FROM tickets ORDER BY id"""
            )
        ]


@mcp.tool
def get_ticket_details(ticket_id: int) -> dict[str, Any]:
    """Fetch one ticket exactly as stored on the board."""
    with _database() as conn:
        row = conn.execute(
            """
            SELECT id, type, requester, subject, sku, size, qty, lease_id,
                   invoice_id, status, notes, created_at
            FROM tickets WHERE id = ?
            """,
            (ticket_id,),
        ).fetchone()
        if row is None:
            return {"found": False, "ticket_id": ticket_id}
        return {"found": True, "ticket": dict(row)}


@mcp.tool
def check_item_stock(sku: str, size: str) -> dict[str, Any]:
    """Look up exact SKU and size stock, along with its database cost and list price."""
    with _database() as conn:
        stock = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        ).fetchone()
        if stock is None:
            return {"found": False, "sku": sku, "size": size}
        price = conn.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?",
            (sku,),
        ).fetchone()
        return {
            "found": True,
            "inventory": dict(stock),
            "pricing": dict(price) if price is not None else None,
        }


@mcp.tool
def get_lease_status(lease_id: int) -> dict[str, Any]:
    """Return lease details and compare its next rent date with the shop date."""
    with _database() as conn:
        lease = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if lease is None:
            return {"found": False, "lease_id": lease_id}
        shop_date = _shop_date(conn)
        due_date = date.fromisoformat(lease["next_due"])
        return {
            "found": True,
            "lease": dict(lease),
            "shop_date": shop_date.isoformat() if shop_date else None,
            "is_overdue": due_date < shop_date if shop_date else None,
            "days_until_due": (due_date - shop_date).days if shop_date else None,
        }


@mcp.tool
def get_invoice_and_vendor_status(invoice_id: int) -> dict[str, Any]:
    """Return invoice/vendor facts, overdue status, lead time, and open invoice blockers."""
    with _database() as conn:
        invoice = conn.execute(
            """
            SELECT i.id AS invoice_id, i.vendor_id, i.amount, i.due_date, i.status,
                   i.description, v.name AS vendor_name, v.specialty, v.lead_days
            FROM invoices AS i
            JOIN vendors AS v ON v.id = i.vendor_id
            WHERE i.id = ?
            """,
            (invoice_id,),
        ).fetchone()
        if invoice is None:
            return {"found": False, "invoice_id": invoice_id}
        blockers = conn.execute(
            "SELECT id, amount, due_date, status, description FROM invoices "
            "WHERE vendor_id = ? AND LOWER(status) = 'open' ORDER BY id",
            (invoice["vendor_id"],),
        ).fetchall()
        shop_date = _shop_date(conn)
        due_date = date.fromisoformat(invoice["due_date"])
        return {
            "found": True,
            "invoice": dict(invoice),
            "shop_date": shop_date.isoformat() if shop_date else None,
            "is_overdue": due_date < shop_date if shop_date else None,
            "vendor_has_open_invoice": bool(blockers),
            "vendor_open_invoices": [dict(row) for row in blockers],
        }


@mcp.tool
def list_vendors() -> list[dict[str, Any]]:
    """List vendor specialties and lead times; this tool takes no arguments."""
    with _database() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT id, name, specialty, lead_days FROM vendors ORDER BY id"
            )
        ]


@mcp.tool
def get_vendor_status(vendor_id: int) -> dict[str, Any]:
    """Return a vendor's recorded specialty, lead time, and every open invoice that blocks shipment."""
    with _database() as conn:
        vendor = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?",
            (vendor_id,),
        ).fetchone()
        if vendor is None:
            return {"found": False, "vendor_id": vendor_id}
        open_invoices = conn.execute(
            "SELECT id, amount, due_date, status, description FROM invoices "
            "WHERE vendor_id = ? AND LOWER(status) = 'open' ORDER BY id",
            (vendor_id,),
        ).fetchall()
        return {
            "found": True,
            "vendor": dict(vendor),
            "vendor_has_open_invoice": bool(open_invoices),
            "vendor_open_invoices": [dict(row) for row in open_invoices],
        }


@mcp.tool
def get_cash_accounts() -> list[dict[str, Any]]:
    """Return recorded account balances for affordability checks."""
    with _database() as conn:
        return [
            dict(row)
            for row in conn.execute("SELECT name, balance, date FROM cash_accounts ORDER BY name")
        ]


@mcp.tool
def add_ticket_note(ticket_id: int, note: str) -> dict[str, Any]:
    """Append a board note or customer-message draft; this tool never sends messages."""
    cleaned = note.strip()
    if not cleaned:
        return {"saved": False, "reason": "A non-empty note is required."}
    if len(cleaned) > 4000:
        return {"saved": False, "reason": "Notes must be 4000 characters or fewer."}
    with _writable_database() as conn:
        row = conn.execute("SELECT notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"saved": False, "reason": "Ticket not found.", "ticket_id": ticket_id}
        prior = row["notes"] or ""
        updated = f"{prior}\n{cleaned}" if prior else cleaned
        conn.execute("UPDATE tickets SET notes = ? WHERE id = ?", (updated, ticket_id))
        return {"saved": True, "ticket_id": ticket_id, "notes": updated}


@mcp.tool
def mark_ticket_resolved(ticket_id: int) -> dict[str, Any]:
    """Mark a ticket resolved after the team has completed its run."""
    with _writable_database() as conn:
        row = conn.execute(
            "SELECT id, status FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if row is None:
            return {"updated": False, "reason": "Ticket not found.", "ticket_id": ticket_id}
        conn.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))
        return {
            "updated": True,
            "ticket_id": ticket_id,
            "previous_status": row["status"],
            "status": "resolved",
        }


@mcp.tool
def request_payment_approval(
    ticket_id: int,
    obligation_type: str,
    reference_id: int,
    account: str = "checking",
) -> dict[str, Any]:
    """Queue an invoice or rent payment for human approval; this never moves cash."""
    if obligation_type not in {"invoice", "lease"}:
        return {"created": False, "reason": "obligation_type must be 'invoice' or 'lease'."}
    with _writable_database() as conn:
        _ensure_approval_table(conn)
        ticket = conn.execute(
            "SELECT id, invoice_id, lease_id FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if ticket is None:
            return {"created": False, "reason": "Ticket not found.", "ticket_id": ticket_id}
        if obligation_type == "invoice":
            if ticket["invoice_id"] != reference_id:
                return {"created": False, "reason": "Invoice does not match this ticket."}
            obligation = conn.execute(
                "SELECT id, amount, status, description FROM invoices WHERE id = ?",
                (reference_id,),
            ).fetchone()
            if obligation is None or obligation["status"].lower() != "open":
                return {"created": False, "reason": "Invoice is missing or is not open."}
            amount = float(obligation["amount"])
            reference_details = f"Invoice {reference_id}: {obligation['description'] or ''}".strip()
        else:
            if ticket["lease_id"] != reference_id:
                return {"created": False, "reason": "Lease does not match this ticket."}
            obligation = conn.execute(
                "SELECT id, space_name, monthly_rent FROM leases WHERE id = ?",
                (reference_id,),
            ).fetchone()
            if obligation is None:
                return {"created": False, "reason": "Lease not found."}
            amount = float(obligation["monthly_rent"])
            reference_details = f"Rent for {obligation['space_name']} (lease {reference_id})"

        cash = conn.execute(
            "SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,)
        ).fetchone()
        if cash is None:
            return {"created": False, "reason": "Cash account not found.", "account": account}
        available = float(cash["balance"])
        if amount > available:
            return {
                "created": False,
                "reason": "Insufficient cash; no approval request was created.",
                "amount": amount,
                "available_balance": available,
                "account": account,
            }

        existing = conn.execute(
            """SELECT id, amount, account, status FROM approval_requests
               WHERE ticket_id = ? AND action_type = 'payment' AND reference_type = ?
                 AND reference_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1""",
            (ticket_id, obligation_type, reference_id),
        ).fetchone()
        if existing is not None:
            return {"created": False, "already_pending": True, "request": dict(existing)}

        details = f"{reference_details}; requires human approval before payment."
        cursor = conn.execute(
            """INSERT INTO approval_requests
               (ticket_id, action_type, reference_type, reference_id, amount, account,
                details, status, created_at)
               VALUES (?, 'payment', ?, ?, ?, ?, ?, 'pending', ?)""",
            (ticket_id, obligation_type, reference_id, amount, account, details, _now()),
        )
        return {
            "created": True,
            "status": "pending_approval",
            "request_id": cursor.lastrowid,
            "ticket_id": ticket_id,
            "amount": amount,
            "account": account,
            "available_balance": available,
            "details": details,
            "cash_moved": False,
        }


@mcp.tool
def prepare_purchase_order(
    ticket_id: int,
    vendor_id: int,
    sku: str,
    size: str,
    quantity: int,
    account: str = "checking",
) -> dict[str, Any]:
    """Queue an affordable restock for human approval, refusing vendors with open invoices."""
    if quantity <= 0:
        return {"created": False, "reason": "quantity must be a positive integer."}
    with _writable_database() as conn:
        _ensure_approval_table(conn)
        ticket = conn.execute(
            "SELECT id, sku, size, qty FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if ticket is None:
            return {"created": False, "reason": "Ticket not found.", "ticket_id": ticket_id}
        if ticket["sku"] != sku or ticket["size"] != size:
            return {"created": False, "reason": "Item does not match the ticket's SKU and size."}
        if ticket["qty"] is None:
            return {"created": False, "reason": "Ticket has no requested quantity."}

        stock = conn.execute(
            "SELECT qty FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone()
        price = conn.execute(
            "SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
        vendor = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()
        if stock is None or price is None or vendor is None:
            return {
                "created": False,
                "reason": "Matching inventory, pricing, or vendor record was not found.",
            }
        shortfall = max(int(ticket["qty"]) - int(stock["qty"]), 0)
        if shortfall <= 0:
            return {"created": False, "reason": "Current stock already covers the ticket quantity."}
        if quantity > shortfall:
            return {
                "created": False,
                "reason": "Purchase quantity exceeds the ticket shortfall.",
                "shortfall": shortfall,
            }

        blockers = conn.execute(
            "SELECT id, amount, due_date, status FROM invoices "
            "WHERE vendor_id = ? AND LOWER(status) = 'open' ORDER BY id",
            (vendor_id,),
        ).fetchall()
        if blockers:
            return {
                "created": False,
                "reason": "Vendor cannot ship while it has an open unpaid invoice.",
                "vendor": dict(vendor),
                "vendor_open_invoices": [dict(row) for row in blockers],
            }

        total = round(float(price["unit_cost"]) * quantity, 2)
        cash = conn.execute(
            "SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,)
        ).fetchone()
        if cash is None:
            return {"created": False, "reason": "Cash account not found.", "account": account}
        available = float(cash["balance"])
        if total > available:
            return {
                "created": False,
                "reason": "Insufficient cash; no purchase order request was created.",
                "amount": total,
                "available_balance": available,
                "account": account,
            }

        existing = conn.execute(
            """SELECT id, amount, account, status FROM approval_requests
               WHERE ticket_id = ? AND action_type = 'purchase_order' AND vendor_id = ?
                 AND sku = ? AND size = ? AND quantity = ? AND status = 'pending'
               ORDER BY id DESC LIMIT 1""",
            (ticket_id, vendor_id, sku, size, quantity),
        ).fetchone()
        if existing is not None:
            return {"created": False, "already_pending": True, "request": dict(existing)}

        details = (
            f"Restock {quantity} x {sku} size {size} from {vendor['name']} "
            f"({vendor['lead_days']} day lead time); human approval required."
        )
        cursor = conn.execute(
            """INSERT INTO approval_requests
               (ticket_id, action_type, reference_type, reference_id, vendor_id, sku, size,
                quantity, amount, account, details, status, created_at)
               VALUES (?, 'purchase_order', 'vendor', ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (
                ticket_id, vendor_id, vendor_id, sku, size, quantity, total, account,
                details, _now(),
            ),
        )
        return {
            "created": True,
            "status": "pending_approval",
            "request_id": cursor.lastrowid,
            "ticket_id": ticket_id,
            "vendor": dict(vendor),
            "sku": sku,
            "size": size,
            "quantity": quantity,
            "unit_cost": float(price["unit_cost"]),
            "amount": total,
            "account": account,
            "available_balance": available,
            "details": details,
            "cash_moved": False,
        }


@mcp.tool
def list_pending_approval_requests() -> list[dict[str, Any]]:
    """List pending human decisions; an absent approval table means the queue is empty."""
    with _database() as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='approval_requests'"
        ).fetchone()
        if table is None:
            return []
        return [
            dict(row)
            for row in conn.execute(
                """SELECT id, ticket_id, action_type, reference_type, reference_id,
                          vendor_id, sku, size, quantity, amount, account, details,
                          status, created_at
                   FROM approval_requests WHERE status = 'pending' ORDER BY id"""
            )
        ]


if __name__ == "__main__":
    mcp.run()
