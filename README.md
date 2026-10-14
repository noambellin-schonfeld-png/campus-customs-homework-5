# Homework 5: Campus Customs Multi-Agent Operations

Campus Customs is a local operations desk built from a FastMCP server, a FastAPI backend with five PydanticAI agents, and a React dashboard. The agents use `gpt-6-luna` through Portkey. The dashboard runs at `http://localhost:5173` and calls the backend at `http://localhost:8000`.

## Data and clean runs

- `data/campus_customs.db` is the original assignment database and reset source. Keep it unchanged.
- `data/campus_customs_new.db` is the working copy used by the MCP server and backend. The submitted copy contains the recorded Problem 9 run.
- The shop's current date comes from `desk.date_today`; overdue checks use that value.

To restore a clean working copy manually, stop active ticket runs and run this from the project root:

```sh
cp data/campus_customs.db data/campus_customs_new.db
```

The dashboard's **Restore original data** control or `POST http://localhost:8000/api/reset` performs the same reset without changing the original database. Reset the working database before a fresh full run of tickets 101, 102, and 103. The append-only `output/audit_trail.json` is not cleared by a database reset. Approve each proposed payment or purchase in the dashboard; agents only prepare approval requests. Customer and vendor messages remain drafts.

## Setup

From the project root, install the Python dependencies and make a private local environment file:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `PORTKEY_API_KEY` to your own key. **Do not commit `.env` or publish the key.** `.env.example` is safe to commit and contains only a placeholder. Install the dashboard dependencies once:

```sh
cd frontend
npm install
cd ..
```

## Start the services

### MCP server

The FastMCP server uses stdio, not an HTTP port. Its project connection is in `.mcp.json`. From the project root, an MCP client can start it with:

```sh
python3 mcp_server/mcp_server.py
```

The FastAPI agent team starts the same MCP server as a stdio child process for each ticket run, so no separate MCP terminal is needed when using the dashboard.

### FastAPI backend

In a terminal with the project virtual environment active:

```sh
cd backend
uvicorn main:app --reload --port 8000
```

The dashboard is allowed by the backend's CORS settings at the usual Vite origin.

### React dashboard

In another terminal:

```sh
cd frontend
npm run dev
```

Open the local Vite URL printed by the command, usually `http://localhost:5173`. Pick ticket 101, 102, or 103 to run the team. Review each pending payment or purchase request and approve it explicitly in the dashboard.

## Project layout

```text
AI_prompts.md                 Prompt log for Problems 1–11
requirements.txt              Python dependencies
.env.example                  Safe placeholder for the local Portkey key
.gitignore                    Excludes secrets, caches, and installed packages
.mcp.json                     Local stdio MCP server connection
README.md
data/
  campus_customs.db           Untouched source database
  campus_customs_new.db       Working database
mcp_server/
  mcp_server.py               FastMCP tools
  README.md
backend/
  main.py                     FastAPI routes and human approval endpoint
  models.py
  agents.py
  prompts/                    The five agent instructions
frontend/                     React, Vite, and TypeScript dashboard
output/                       Harness, plans, run evidence, screenshots, and audit
```

## Guardrails

Shop facts come from the MCP server and the working database. Agents cannot send customer or vendor messages or execute payments. A person must approve payments and purchase orders, and the backend refuses an approval if checking does not have enough cash. The original database is retained for repeatable resets.
