# Campus Customs MCP Server

This FastMCP server is the only shop-data interface for the Campus Customs agent team. It uses `data/campus_customs_new.db`; `data/campus_customs.db` remains the reset source. Read tools return database facts or calculations based on `desk.date_today`. Write tools append ticket notes, prepare requests for a human, or persist ticket resolution after a completed run; none sends messages, contacts vendors, approves a request, or executes a payment.

The first payment or purchase-order request creates an `approval_requests` queue table in the working copy. The original reset database is never changed by the server.

## Tools

- `list_open_tickets()`: unresolved tickets and the shop date (`tickets`, `desk`).
- `list_tickets()`: every board ticket and its current status, including resolved tickets (`tickets`).
- `get_ticket_details(ticket_id)`: one board ticket (`tickets`).
- `check_item_stock(sku, size)`: exact stock and SKU cost/list price (`inventory`, `pricing`).
- `get_lease_status(lease_id)`: lease facts and rent timing using the shop date (`leases`, `desk`).
- `get_invoice_and_vendor_status(invoice_id)`: invoice, vendor lead time, overdue status, and open invoice blockers (`invoices`, `vendors`, `desk`).
- `list_vendors()`: recorded vendor specialties and lead times (`vendors`); it does not infer item/vendor mappings.
- `get_vendor_status(vendor_id)`: vendor facts and invoices that block shipment (`vendors`, `invoices`).
- `get_cash_accounts()`: recorded account balances (`cash_accounts`).
- `add_ticket_note(ticket_id, note)`: append a board note or customer draft (`tickets`); no message is sent.
- `mark_ticket_resolved(ticket_id)`: persist the board's resolved status after a completed team run (`tickets`).
- `request_payment_approval(ticket_id, obligation_type, reference_id, account)`: queue a correctly linked invoice or rent amount after an affordability check (`tickets`, `invoices` or `leases`, `cash_accounts`, `approval_requests`). It does not move cash.
- `prepare_purchase_order(ticket_id, vendor_id, sku, size, quantity, account)`: verify shortfall, cost, vendor invoice block, and affordability, then queue human approval (`tickets`, `inventory`, `pricing`, `vendors`, `invoices`, `cash_accounts`, `approval_requests`).
- `list_pending_approval_requests()`: list requests awaiting a human (`approval_requests`).

The agent backend connects to these tools through PydanticAI's MCP toolset. Install the dependency with `python3 -m pip install -r requirements.txt`. Run `python mcp_server.py` from this directory to serve tools over stdio.

The project MCP connection is saved in `.mcp.json`; Codex's project-scoped equivalent is also in `.codex/config.toml`. After installing FastMCP and trusting/reloading the project in Codex, the configured server is available as `campus_customs`. The agent backend attaches this same FastMCP server using PydanticAI's MCP toolset rather than querying SQLite itself.
