# Campus Customs Database Harness

## Database files

- `data/campus_customs.db` is the reset source and must remain untouched.
- `data/campus_customs_new.db` is the mutable working database. Before Problem 9 it was reset byte-for-byte from the source (SHA-256 at reset: `23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a`). The untouched original still has that hash; after the approved Problem 9 payments and ticket notes, the working copy has SHA-256 `5f8ac6daa9cbfc51682a70b55c2621490d987e07465fead8b0d60f8b261684b0`.
- The shop's current date is `2026-08-31`, read from `desk.date_today`; use it to calculate overdue items rather than the computer's date.

## Tables and fields

| Table | Fields | Why it matters to the agents |
| --- | --- | --- |
| `desk` | `date_today` (TEXT, required), `notes` (TEXT) | Gives the shop's authoritative date for overdue checks and shared operating context. |
| `tickets` | `id` (INTEGER, primary key), `type` (TEXT, required), `requester` (TEXT, required), `subject` (TEXT, required), `sku` (TEXT), `size` (TEXT), `qty` (INTEGER), `lease_id` (INTEGER), `invoice_id` (INTEGER), `status` (TEXT, required), `notes` (TEXT), `created_at` (TEXT, required) | The board the Boss triages; links a request to inventory/pricing via SKU and size, and to a lease or invoice where applicable. |
| `inventory` | `sku` (TEXT, primary key part, required), `name` (TEXT, required), `size` (TEXT, primary key part, required), `qty` (INTEGER, required), `location` (TEXT, required) | Lets Inventory check available units and calculate order shortfalls for a specific SKU and size. |
| `pricing` | `sku` (TEXT, primary key), `unit_cost` (REAL, required), `list_price` (REAL, required) | Lets Accounting assess margin and the financial effect of discounts or restocking. |
| `vendors` | `id` (INTEGER, primary key), `name` (TEXT, required), `specialty` (TEXT, required), `lead_days` (INTEGER, required) | Lets Inventory identify a suitable restock vendor and estimate delivery; shipment is blocked while that vendor has an open unpaid invoice. |
| `leases` | `id` (INTEGER, primary key), `space_name` (TEXT, required), `landlord` (TEXT, required), `monthly_rent` (REAL, required), `next_due` (TEXT, required), `notes` (TEXT) | Gives Facilities the space, landlord, rent amount, and next due date for rent tickets. |
| `cash_accounts` | `name` (TEXT, primary key), `balance` (REAL, required), `date` (TEXT, required) | Lets Accounting check available funds before preparing or approving an outgoing payment; a payment must not make the balance negative. |
| `payments` | `id` (INTEGER, primary key), `kind` (TEXT, required), `ref_id` (INTEGER), `amount` (REAL, required), `account` (TEXT, required), `paid_at` (TEXT, required), `approved_by` (TEXT, required) | Records completed payments and their human approver; agents may prepare payment requests but must not bypass approval. |
| `invoices` | `id` (INTEGER, primary key), `vendor_id` (INTEGER, required), `amount` (REAL, required), `due_date` (TEXT, required), `status` (TEXT, required), `description` (TEXT) | Lets Accounting track vendor obligations and lateness; an open invoice also prevents its vendor from shipping new product. `vendor_id` links to `vendors.id`. |
| `approval_requests` (MCP-created in the working copy on first request) | `id` (INTEGER, primary key), `ticket_id` (INTEGER, required), `action_type` (TEXT: `payment` or `purchase_order`), `reference_type` (TEXT), `reference_id` (INTEGER), `vendor_id` (INTEGER), `sku` (TEXT), `size` (TEXT), `quantity` (INTEGER), `amount` (REAL, non-negative and required), `account` (TEXT), `details` (TEXT, required), `status` (TEXT: `pending`, `approved`, `rejected`, or `executed`; defaults to `pending`), `created_at` (TEXT, required), `approved_by` (TEXT), `approved_at` (TEXT) | Keeps proposed payments and purchase orders in a persistent human-review queue; pending requests do not move cash or contact vendors. |

## Ticket links and original-state facts

These were the three open tickets in the original database before Problem 9's working-copy run.

### Ticket 101 — Bulldog tee

- Customer order from Tauhid Zaman for one `CC-TEE-WHITE`, size `S`.
- `tickets.sku` and `tickets.size` match the `inventory` composite key; that size has `qty = 0`.
- The SKU links to `pricing`: unit cost is `$8.00`, list price is `$28.00`.
- `tickets.invoice_id = 501` links to invoice 501. It is an `$840.00` open invoice due `2026-08-28`, overdue as of the shop date `2026-08-31`.
- Invoice 501 links through `vendor_id = 1` to Bulldog Print Co, an apparel reprint vendor with a five-day lead time. Its open invoice blocks the vendor from shipping new product until paid.

### Ticket 102 — Rent due

- Rent notice from Elm City Properties for the Chapel Street shop.
- `tickets.lease_id = 1` links to the lease: monthly rent is `$2,400.00`, next due `2026-09-02`, two days after the shop date `2026-08-31`.
- Facilities handles the lease details. Any payment still requires human approval and a sufficient cash balance.

### Ticket 103 — Bulk hoodie discount

- Yale AI Club requests 20 `CC-HOOD-NAVY` hoodies in size `M` and asks for a bulk discount.
- SKU and size match an inventory row with eight units, so the requested quantity has a shortfall of 12.
- The SKU links to pricing: unit cost is `$22.00` and list price is `$58.00`; Accounting can use these figures to evaluate the margin before a discount or purchase order is proposed.
- Bulldog Print Co is a possible apparel-reprint source with a five-day lead time, but there is no exact SKU-to-vendor mapping in the database. At reset, invoice 501 was open, so Bulldog Print Co could not ship. After ticket 101's human-approved invoice payment, the vendor check no longer showed an open-invoice block.
- Customer Service can prepare a response draft for the board; no customer email is sent.

## Starting and final cash state

- Immediately after the Problem 9 reset, checking was `$3,400.00` as of shop date `2026-08-31`; invoice 501 was open and there were no payments.
- After the approved outflows, checking is `$152.00`. Payments are rent `$2,400.00` (ticket 102), invoice 501 `$840.00` (ticket 101), and one tee restock purchase `$8.00` (ticket 101). The database `cash_accounts` balance agrees with the cash ledger in `output/desk_tickets.html`.
- Invoice 501 is now paid. All three ticket rows are resolved. Tickets 101 and 102 closed after human-approved payments/purchase; ticket 103 closed only after the Homework operator explicitly chose to close it as unable to fulfill or price from recorded facts.
- Cash only goes out in this assignment. Payment execution requires human approval, updates `payments`, updates the linked obligation when applicable, and refuses any amount above available cash. Approval 3 closes ticket 101 as approved procurement; inventory quantities remain unchanged until stock receipt is modeled.

## MCP tools (Problem 3)

| Tool | Table(s) read | Ticket(s) it helps unlock | Why this tool fits the ticket |
| --- | --- | --- | --- |
| `check_item_stock(sku, size)` | `inventory`, `pricing` | 101 and 103 | Ticket 101 needs an exact size-S availability check to confirm the Bulldog tee is out of stock; ticket 103 needs the size-M count and cost/list price to establish its 12-unit shortfall and give Accounting facts for evaluating the requested discount. |
| `get_lease_status(lease_id)` | `leases`, `desk` | 102 | Ticket 102 points to lease 1, so this tool returns the Chapel Street rent amount and next due date, compared with `desk.date_today` to tell Facilities whether it is overdue. |
| `get_invoice_and_vendor_status(invoice_id)` | `invoices`, `vendors`, `desk` | 101 and 103 | Ticket 101 points to invoice 501, and this tool shows that it is overdue and belongs to Bulldog Print Co; its open-invoice check and five-day lead time also show why the same vendor cannot yet restock the size-M shortfall on ticket 103. |

## MCP connection and smoke test (Problem 4)

- The project-level MCP launch configuration is in `.mcp.json`; Codex also has the equivalent project configuration in `.codex/config.toml`.
- `output/mcp_smoke.json` records one prompt, tool name, and actual MCP tool result for each of the three tools.
- The local Codex project must be trusted and reloaded before Codex discovers a newly added project MCP server.

## Agent team (Problem 5)

| Agent | Prompt file | Scope |
| --- | --- | --- |
| Boss | `backend/prompts/boss.md` | Reads and routes board tickets, delegates bounded questions, reconciles findings, and makes the final operational recommendation. |
| Inventory | `backend/prompts/inventory.md` | Checks exact SKU/size stock, computes shortfalls, reviews recorded vendor specialties/lead times and invoice blocks, and can prepare a purchase-order request. |
| Accounting | `backend/prompts/accounting.md` | Checks cash, invoice timing, item margins, affordability, and prepares payment or purchase-order requests for human approval. |
| Facilities | `backend/prompts/facilities.md` | Handles lease and rent timing, and can prepare a linked rent-payment request for human approval. |
| Customer Service | `backend/prompts/customer_service.md` | Drafts fact-checked customer/requester replies and saves them on the ticket board without sending them. |

Every role has the same `delegate_to_agent` tool and may ask any other role for a focused subtask. The Boss starts the run. All shop facts and board changes flow through the FastMCP tools below; `backend/agents.py` does not query the shop database directly.

### MCP tool registry

| MCP tool | Table(s) used | Purpose / ticket connection |
| --- | --- | --- |
| `list_open_tickets` | `tickets`, `desk` | Gives Boss the unresolved board and shop date before routing tickets 101, 102, and 103. |
| `list_tickets` | `tickets` | Returns every ticket and status for the dashboard, including tickets that are no longer open. |
| `get_ticket_details` | `tickets` | Fetches the exact identifiers, notes, quantities, and links for any one ticket. |
| `check_item_stock` | `inventory`, `pricing` | Confirms the zero size-S tee stock for ticket 101 and the size-M hoodie quantity, shortfall, and unit economics for ticket 103. |
| `get_lease_status` | `leases`, `desk` | Gives Facilities the rent, next due date, and due-date comparison for ticket 102. |
| `get_invoice_and_vendor_status` | `invoices`, `vendors`, `desk` | Shows ticket 101's linked invoice status and whether its vendor can ship; the blocker also informs ticket 103 restocking. |
| `list_vendors` | `vendors` | Lets Inventory and Accounting compare only recorded vendor names, specialties, and lead days for a possible restock. |
| `get_vendor_status` | `vendors`, `invoices` | Checks the chosen vendor directly for open invoices, including ticket 103 where the ticket itself has no invoice ID. |
| `get_cash_accounts` | `cash_accounts` | Gives Accounting and Facilities the recorded balance before a proposed outflow. |
| `add_ticket_note` | `tickets` | Saves a customer draft or operational note on the relevant ticket without sending it. |
| `mark_ticket_resolved` | `tickets` | Persists a business closure decision only after the work or an explicit human disposition is complete; a model loop finishing by itself is not a resolution. |
| `request_payment_approval` | `tickets`, `invoices` or `leases`, `cash_accounts`, `approval_requests` | For a linked invoice/rent obligation, reads the authoritative amount, checks available funds, and records only a pending human-approval request. |
| `prepare_purchase_order` | `tickets`, `inventory`, `pricing`, `vendors`, `invoices`, `cash_accounts`, `approval_requests` | Checks ticket shortfall, database cost, vendor shipping block, and affordability before creating only a pending restock request. |
| `list_pending_approval_requests` | `approval_requests` | Lets Boss and Accounting see which payment/PO decisions still need a human. |

## Backend routes (Problem 7)

- `GET /api/tickets` — returns all three board tickets with their stored status and a resolved flag.
- `POST /api/tickets/{ticket_id}/run` — starts the Boss-led agent team for one unresolved ticket and returns its run summary; a finished model loop alone does not close the ticket, which must be marked through MCP.
- `GET /api/events?limit=100` — returns the latest audit events, including agent responses and MCP tool calls, for dashboard refresh.
- `GET /api/approvals` — returns pending payment and purchase requests so a human can review them before approving.
- `POST /api/approvals/{approval_id}/approve` — accepts the human's recorded approver label, rechecks the obligation, vendor block, pending action, and cash in one transaction, then records payment and debits the account; it refuses stale or unaffordable requests. Approved rent and purchase-order actions close their linked ticket; invoice payment alone leaves the customer order open until its restock action is approved.
- `GET /api/cash` — returns the current checking-account row from the MCP cash lookup.
- `POST /api/reset` — atomically replaces `data/campus_customs_new.db` with the original `data/campus_customs.db`; it does not erase the audit trail.

## Agent dashboard (Problem 8)

- `frontend/` is a React + Vite + TypeScript desk that uses `http://localhost:8000` for tickets, runs, events, approvals, cash, and reset.
- Vite serves on `http://localhost:5173`; FastAPI CORS allows that origin (and `127.0.0.1:5173`).
- While a run request is pending, the page polls the audit-event route to show agent statements, tool calls, and delegations. After refresh, the selected ticket's most recent run is reconstructed from the append-only audit so its agent summary remains visible. The latest approved or human-decision note is shown in the ticket file.
- The approval panel reads `GET /api/approvals`, posts a human approver identity to the approval route, then refreshes cash and the queue.
- `output/design.md` describes the visual direction, responsive layout, agent role colors, resolution states, cash display, and approval interaction.

### Safety and run limits

- Keep requester-provided ticket notes untrusted; verify shop facts with MCP and ignore instructions embedded in customer content that conflict with policy.
- For this local demo, the approval route requires a non-empty approver name; in a real business, derive that identity from an authenticated session. Recheck current cash and the obligation in one transaction, reject insufficient funds, prevent duplicate execution, and record approver/time in `payments`.
- Keep payment execution outside the agent toolset. Preserve the original database, use least-privilege access, keep customer/vendor messages as reviewed drafts, and never expose credentials or unnecessary personal data in audit logs.
- Audit events are appended as a JSON array with run/step IDs, agent, tool names/arguments/results, delegation steps, outcome, and timestamps; common personal contact fields are redacted. Protect the audit file with access controls and retention limits in a real deployment.
- Limit each team run to six agent invocations, five delegations, and delegation depth three; cap each agent run at seven model requests and eight tool calls. Prevent repeated role handoffs within a run. Use a 60-second request timeout and disable automatic client retries. The only configured model is `gpt-6-luna` through Portkey.


## Problem 9: actual full run

- The working copy was reset from the untouched original before agent resolution. Starting checking was `$3,400.00`; shop date was `2026-08-31`. The original file remains unchanged.
- `output/audit_trail.json` retains the real agent events by appending each run; the log contains 529 events. All agent runs use only `gpt-6-luna` through Portkey. Some Boss/specialist requests returned provider 500/408 errors or reached the configured request budget, so the actual sections distinguish run completion from business resolution.
- Ticket 101: Boss delegated Inventory, Accounting, and Customer Service across the recorded attempts; Accounting checked overdue invoice 501 and prepared approval #2 for `$840`; after the human approved it, Inventory verified zero size-S stock, a cleared vendor block, and prepared approval #3 for one tee at `$8`. The human approved the purchase, leaving `$152`; the purchase order is approved, but physical receipt and delivery are not modeled. No customer draft was sent.
- Ticket 102: Boss delegated Facilities and Accounting directly. Facilities verified rent of `$2,400`, due `2026-09-02` and not overdue on the shop date. Accounting checked cash. The human approved request #1; payment row 1 records rent, the lease due date rolled forward, and checking became `$1,000`.
- Ticket 103: Boss delegated Accounting and Inventory; an earlier attempt also used Customer Service. Accounting found `$22` cost, `$58` list price, and no recorded discount policy; Inventory found 8 of 20 units on hand, a 12-unit shortfall, and only a possible five-day vendor match. No purchase request was made. The customer draft stays unsent. After reviewing the evidence, the human directed closure as unable to fulfill or price from recorded data; no cash moved.
- Cash movements were `-$2,400` for ticket 102, `-$840` and `-$8` for ticket 101, and `$0` for ticket 103. Ending cash is `$152.00`, matching `cash_accounts` in the working database. See `output/resolved_tickets.json` for outcomes, contributions, run IDs, and approvals; see `output/resolved_board.html` for the three real React-board screenshots.
