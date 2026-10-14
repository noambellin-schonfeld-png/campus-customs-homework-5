# AI Prompts Log

## Problem 1: Vibe Coder Prompts

**Prompt typed:** Create and maintain an `AI_prompts.md` file in the Homework 5 project. Keep a separate section for each problem. For every section, record the problem number and title, at least one prompt I gave you rewritten in my own words, and a follow-up prompt if one was needed. If there was a follow-up, add one sentence explaining what the first response was missing.

**Follow-up prompt:** None needed.

## Problem 2: Study the Campus Customs Database

**Prompt typed:** Inspect every table and its fields in the original Campus Customs database. Keep the original unchanged and use the matching `data/campus_customs_new.db` copy for later updates. Trace the three open tickets to the related records in the other tables, then start `output/harness.md` with each table's fields and a short explanation of why the agents need it. Continue expanding the harness as later problems add implementation details.

**Follow-up prompt:** None needed.

## Problem 3: Build the MCP Server

**Prompt typed:** Create a FastMCP server in `mcp_server/` that reads the working SQLite database at `data/campus_customs_new.db`. Add three clearly named lookup tools for facts needed to handle the existing tickets, and never supply values that are not in the database. The server does not need to be started or connected yet. Document each tool's source tables, ticket relevance, and ticket-specific purpose in the harness, and add a short README describing the server, database path, and tools.

**Follow-up prompt:** None needed.

## Problem 4: Add the MCP Server to Vibe Coder and Test Each Tool

**Prompt typed:** Register the Campus Customs stdio MCP server with the project-level vibe-coder settings, then issue one focused request for each of its three tools. Save the exact requests, tool names, and returned database-backed values as `output/mcp_smoke.json` so the MCP wiring can be reviewed.

**Follow-up prompt:** None needed.

## Problem 5: Build the Agent Team and Grow the MCP Tools

**Prompt typed:** Build five PydanticAI roles—Boss, Inventory, Accounting, Facilities, and Customer Service—with detailed, separate prompts and a bounded delegation tool so any role can ask another for help. Keep every model call fixed to `gpt-6-luna` through Portkey using `PORTKEY_API_KEY`. Let agents obtain and update shop facts only through the existing FastMCP server, adding the board, cash, vendor, note, and human-approval tools they need. Make money movement and external messages impossible for agents, append an auditable event for each loop step without erasing earlier runs, and document the agents, complete MCP table/tool mapping, and business/token guardrails in the harness and MCP README.

**Follow-up prompt:** None needed.

## Problem 6: Plan the Three Tickets

**Prompt typed:** Before running the agents, create a standalone `output/desk_tickets.html` with tabs for tickets 101, 102, and 103, plus empty Cash and Reflection tabs for later. In each ticket tab, fill only an Expected section: identify the first specialist the Boss should consult and why, spell out the focused delegation chain, and name the MCP tools the team should use. Keep an Actual section reserved for after the run, and make the plans ticket-specific instead of sending every specialist to every ticket.

**Follow-up prompt:** None needed.

## Problem 7: Backend Routes

**Prompt typed:** Add a FastAPI app in `backend/main.py` for the dashboard: list the three tickets with their current resolution status, start the existing agent team for a selected ticket, expose recent agent/tool audit events, return the checking balance, and reset the working database from the untouched original. Add a human-triggered approval endpoint that rechecks funds and updates payment records and cash only after approval. Document every route in one line in `output/harness.md`, then start the local server on port 8000 from `backend/`.

**Follow-up prompt:** None needed.

## Problem 8: Agent Dashboard

**Prompt typed:** Build a responsive React, Vite, and TypeScript desk in `frontend/` that connects to the FastAPI backend at `http://localhost:8000`. Let an operator browse all three tickets, choose one to run through the agent team, watch the agent and tool activity, and see a concise summary of who helped. Show the checking balance and pending human payment or purchase approvals, and refresh the balance after an approval. Keep ticket status in sync when a run finishes, allow the Vite origin through backend CORS, start the UI with `npm run dev`, and document the visual design choices in `output/design.md`.

**Follow-up prompt:** None needed.

## Problem 9: Resolve the Tickets

**Prompt typed:** Reset the working database from the untouched source before the full run and record the shop's starting checking balance. Run the team against tickets 101, 102, and 103; let me make every required payment or purchase approval; and only close a ticket when its approved action or my explicit business decision supports closure. Preserve the Expected plans in `output/desk_tickets.html`, add Actual sections and a correct per-ticket cash ledger, write `output/resolved_tickets.json`, capture one real React board screenshot for each ticket, and append the real agent runs to the existing audit trail. Finish the harness with the schema, tools, agents, routes, dashboard, and safety rules.

**Follow-up prompt:** Show the latest audited run and the latest approved or human-decided board note when a resolved ticket is selected, keep a finished model loop from automatically closing a ticket whose own result says it remains open, and resolve a purchase-order ticket only after human approval.

**What was missing after the first prompt:** The first pass could conflate “the agent run finished” with “the shop ticket is resolved,” and a refreshed dashboard did not restore the ticket's agent summary from the append-only audit.

## Problem 10: Reflection

**Prompt typed:** Fill the Reflection tab in `output/desk_tickets.html` with a detailed first-person review of how the agents handled tickets 101, 102, and 103. Compare each Actual run with its preserved Expected plan, explain which case would have been simpler with one tool-using agent, identify three new ticket types the current app can handle, and identify three it cannot handle yet along with the agents and MCP tools or data those cases would require. Ground every point in the ticket-tab evidence and the Cash ledger.

**Follow-up prompt:** None needed.

## Problem 11: Submit to GitHub

**Prompt typed:** Prepare the Homework 5 project for a public GitHub submission in the pictured layout. Keep both the original and working SQLite databases in `data/`, exclude all real environment secrets, include a safe `.env.example`, explain setup and service startup in the root README, document resetting the working database before a complete three-ticket run, and record the public repository URL in `output/github_url.txt` after publishing. Submit that same URL to Canvas.

**Follow-up prompt:** None needed.
