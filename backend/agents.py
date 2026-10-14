"""PydanticAI team for Campus Customs, with MCP-only shop data access."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import (
    BaseToolCallPart,
    BaseToolReturnPart,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
)
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.models import AgentEvent, AgentName, AgentRunResult, DelegationRecord

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BACKEND_DIR / "prompts"
AUDIT_PATH = PROJECT_ROOT / "output" / "audit_trail.json"

# The model is intentionally fixed for this homework. Do not make this configurable.
MODEL_NAME: Literal["gpt-6-luna"] = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
REQUEST_TIMEOUT_SECONDS = 60
MAX_AGENT_RUNS = 6  # Boss plus at most five focused consultations.
MAX_DELEGATIONS = MAX_AGENT_RUNS - 1
MAX_DELEGATION_DEPTH = 3
MAX_REQUESTS_PER_AGENT_RUN = 7
MAX_TOOL_CALLS_PER_AGENT_RUN = 8
MAX_AUDIT_TEXT_CHARS = 1600

AGENT_NAMES: tuple[AgentName, ...] = (
    "boss",
    "inventory",
    "accounting",
    "facilities",
    "customer_service",
)

# A project-local .env wins, then the assignment folder's .env, then Downloads/.env.
for _env_file in (
    PROJECT_ROOT.parent / ".env",
    PROJECT_ROOT / ".env",
    BACKEND_DIR / ".env",
):
    if _env_file.is_file():
        load_dotenv(_env_file, override=True)

_AUDIT_LOCK = threading.Lock()
_MODEL_CLIENT: AsyncOpenAI | None = None
_TOOLSET: MCPToolset | None = None

EventCallback = Callable[[AgentEvent], Awaitable[None] | None]


@dataclass
class AgentDeps:
    session: "TeamSession"
    agent_name: AgentName
    depth: int
    path: tuple[AgentName, ...]


@dataclass
class TeamSession:
    run_id: str
    task: str
    ticket_id: int | None = None
    on_event: EventCallback | None = None
    events: list[AgentEvent] = field(default_factory=list)
    agents_invoked: list[AgentName] = field(default_factory=list)
    delegations: list[DelegationRecord] = field(default_factory=list)
    invocation_count: int = 0
    delegation_count: int = 0
    sequence: int = 0
    budget_limited: bool = False
    had_error: bool = False

    async def emit(
        self,
        agent: AgentName,
        kind: str,
        depth: int = 0,
        **details: Any,
    ) -> AgentEvent:
        self.sequence += 1
        event = AgentEvent(
            run_id=self.run_id,
            sequence=self.sequence,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            agent=agent,
            kind=kind,
            depth=depth,
            details=_audit_safe(details),
        )
        self.events.append(event)
        await asyncio.to_thread(_append_audit, event.model_dump(mode="json"))
        if self.on_event is not None:
            result = self.on_event(event)
            if inspect.isawaitable(result):
                await result
        return event


def _audit_safe(value: Any, key: str = "") -> Any:
    """Bound audit size and redact common personal contact fields."""
    if key.lower() in {"requester", "email", "phone", "address", "contact"}:
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): _audit_safe(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_audit_safe(item) for item in value]
    if isinstance(value, str):
        text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted-email]", value)
        text = re.sub(
            r"(?<!\d)(?:\+?\d[\d ().-]{7,}\d)(?!\d)",
            lambda match: "[redacted-phone]"
            if sum(character.isdigit() for character in match.group(0)) >= 10
            else match.group(0),
            text,
        )
        if len(text) > MAX_AUDIT_TEXT_CHARS:
            text = text[: MAX_AUDIT_TEXT_CHARS - 1] + "…"
        return text
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:MAX_AUDIT_TEXT_CHARS]


def _append_audit(entry: dict[str, Any]) -> None:
    """Append one event to the JSON array atomically, preserving prior runs."""
    with _AUDIT_LOCK:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        if AUDIT_PATH.exists():
            text = AUDIT_PATH.read_text(encoding="utf-8").strip()
            if text:
                loaded = json.loads(text)
                if not isinstance(loaded, list):
                    raise ValueError("output/audit_trail.json must contain a JSON array")
                rows = loaded
            else:
                rows = []
        else:
            rows = []
        rows.append(entry)
        tmp_path = AUDIT_PATH.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(AUDIT_PATH)


def _require_api_key() -> str:
    api_key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to Homework 5/.env or Downloads/.env.")
    return api_key


def _build_model() -> OpenAIResponsesModel:
    global _MODEL_CLIENT
    api_key = _require_api_key()
    if _MODEL_CLIENT is None:
        _MODEL_CLIENT = AsyncOpenAI(
            api_key=api_key,
            base_url=PORTKEY_BASE_URL,
            default_headers={"x-portkey-api-key": api_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )
    return OpenAIResponsesModel(
        MODEL_NAME,
        provider=OpenAIProvider(openai_client=_MODEL_CLIENT),
    )


def _mcp_toolset() -> MCPToolset:
    """Attach the same FastMCP server that is separately registered in .mcp.json."""
    global _TOOLSET
    if _TOOLSET is None:
        # Import only the MCP server; backend agents never query SQLite directly.
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from mcp_server.mcp_server import mcp as campus_customs_mcp

        _TOOLSET = MCPToolset(campus_customs_mcp)
    return _TOOLSET


def _load_prompt(agent_name: AgentName) -> str:
    path = PROMPTS_DIR / f"{agent_name}.md"
    return path.read_text(encoding="utf-8")


def _make_agent(agent_name: AgentName) -> Agent[AgentDeps, str]:
    agent: Agent[AgentDeps, str] = Agent(
        deps_type=AgentDeps,
        instructions=_load_prompt(agent_name),
        toolsets=[_mcp_toolset()],
        name=f"campus_customs_{agent_name}",
        defer_model_check=True,
    )

    @agent.tool
    async def delegate_to_agent(
        ctx: RunContext[AgentDeps], recipient: AgentName, task: str
    ) -> str:
        """Ask any other Campus Customs role to help with a focused subtask."""
        deps = ctx.deps
        session = deps.session
        task = task.strip()
        if recipient == deps.agent_name:
            return "Choose another role; an agent cannot delegate to itself."
        if not task:
            return "Provide a specific task before delegating."
        if recipient in deps.path or recipient in session.agents_invoked:
            await session.emit(
                deps.agent_name,
                "delegation_limited",
                deps.depth,
                recipient=recipient,
                reason="role already appears in this run; use its existing findings",
            )
            return "That role has already contributed to this ticket. Use its existing findings or consult a different specialist."
        if len(task) > 1500:
            task = task[:1499] + "…"
        if deps.depth >= MAX_DELEGATION_DEPTH:
            session.budget_limited = True
            await session.emit(
                deps.agent_name,
                "delegation_limited",
                deps.depth,
                recipient=recipient,
                reason="maximum delegation depth reached",
            )
            return "Delegation stopped at the configured depth limit; continue with available facts."
        if session.delegation_count >= MAX_DELEGATIONS or session.invocation_count >= MAX_AGENT_RUNS:
            session.budget_limited = True
            await session.emit(
                deps.agent_name,
                "delegation_limited",
                deps.depth,
                recipient=recipient,
                reason="team run budget reached",
            )
            return "Delegation stopped at the configured team budget; continue with available facts."

        session.delegation_count += 1
        record = DelegationRecord(sender=deps.agent_name, recipient=recipient, task=task)
        session.delegations.append(record)
        await session.emit(
            deps.agent_name,
            "delegation_start",
            deps.depth,
            recipient=recipient,
            task=task,
        )
        delegated_prompt = (
            f"Shared ticket/task context: {session.task}\n\n"
            f"Handoff path so far: {' -> '.join(deps.path)}\n\n"
            f"{deps.agent_name} asks you ({recipient}) to help with: {task}\n\n"
            "Return only the findings and recommendation needed by the requesting agent. "
            "Use MCP for shop facts."
        )
        reply = await _run_agent(
            recipient,
            delegated_prompt,
            session,
            depth=deps.depth + 1,
            path=deps.path + (recipient,),
        )
        record.reply = reply
        if reply.startswith("Agent error:"):
            record.status = "error"
        elif reply.startswith("Agent stopped at its configured"):
            record.status = "limited"
        else:
            record.status = "complete"
        await session.emit(
            deps.agent_name,
            "delegation_finish",
            deps.depth,
            recipient=recipient,
            reply=reply,
            status=record.status,
        )
        return reply

    return agent


AGENTS: dict[AgentName, Agent[AgentDeps, str]] = {
    agent_name: _make_agent(agent_name) for agent_name in AGENT_NAMES
}


async def _record_messages(
    agent_name: AgentName,
    session: TeamSession,
    depth: int,
    messages: list[Any],
) -> None:
    tool_names: dict[str, str] = {}
    for message in messages:
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, BaseToolCallPart):
                    tool_names[part.tool_call_id] = part.tool_name
                elif isinstance(part, TextPart) and part.content.strip():
                    await session.emit(
                        agent_name,
                        "assistant_output",
                        depth,
                        text=part.content,
                    )
        elif isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, BaseToolReturnPart):
                    await session.emit(
                        agent_name,
                        "tool_result",
                        depth,
                        tool=tool_names.get(part.tool_call_id, "unknown"),
                        result=part.content,
                    )
                elif isinstance(part, RetryPromptPart):
                    await session.emit(
                        agent_name,
                        "tool_or_output_retry",
                        depth,
                        tool=tool_names.get(part.tool_call_id or "", "unknown"),
                        message=part.content,
                    )


async def _run_agent(
    agent_name: AgentName,
    prompt: str,
    session: TeamSession,
    *,
    depth: int,
    path: tuple[AgentName, ...],
) -> str:
    if session.invocation_count >= MAX_AGENT_RUNS:
        session.budget_limited = True
        await session.emit(
            agent_name,
            "agent_limited",
            depth,
            reason="maximum agent invocations reached",
        )
        return "Team run budget reached; use the findings already available."

    session.invocation_count += 1
    if agent_name not in session.agents_invoked:
        session.agents_invoked.append(agent_name)
    await session.emit(
        agent_name,
        "agent_start",
        depth,
        task=prompt,
        delegation_path=list(path),
        model=MODEL_NAME,
        request_limit=MAX_REQUESTS_PER_AGENT_RUN,
        tool_call_limit=MAX_TOOL_CALLS_PER_AGENT_RUN,
    )
    run = None
    try:
        async with AGENTS[agent_name].iter(
            prompt,
            deps=AgentDeps(session=session, agent_name=agent_name, depth=depth, path=path),
            model=_build_model(),
            usage_limits=UsageLimits(
                request_limit=MAX_REQUESTS_PER_AGENT_RUN,
                tool_calls_limit=MAX_TOOL_CALLS_PER_AGENT_RUN,
            ),
        ) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    await session.emit(agent_name, "model_step", depth, phase="request")
                elif Agent.is_call_tools_node(node):
                    parts = [
                        part
                        for part in node.model_response.parts
                        if isinstance(part, BaseToolCallPart)
                    ]
                    await session.emit(
                        agent_name,
                        "model_step",
                        depth,
                        phase="tool_calls" if parts else "response",
                        tools=[part.tool_name for part in parts],
                    )
                    for part in parts:
                        await session.emit(
                            agent_name,
                            "tool_call",
                            depth,
                            tool=part.tool_name,
                            arguments=part.args_as_dict(),
                        )
        messages = run.result.new_messages()
        await _record_messages(agent_name, session, depth, messages)
        reply = str(run.result.output).strip()
        await session.emit(agent_name, "agent_finish", depth, reply=reply)
        return reply
    except UsageLimitExceeded as exc:
        session.budget_limited = True
        detail = f"{type(exc).__name__}: agent request/tool-call limit reached"
        await session.emit(agent_name, "agent_limited", depth, reason=detail)
        return "Agent stopped at its configured request/tool-call limit; use completed findings only."
    except Exception as exc:
        session.had_error = True
        detail = f"{type(exc).__name__}: {exc}"[:500]
        await session.emit(agent_name, "agent_error", depth, error=detail)
        return f"Agent error: {detail}"


async def run_team(
    message: str,
    *,
    ticket_id: int | None = None,
    on_event: EventCallback | None = None,
) -> AgentRunResult:
    """Run the Boss on a ticket or operations question and return the full trace."""
    clean_message = message.strip()
    if not clean_message:
        raise ValueError("message must not be empty")
    session = TeamSession(
        run_id=str(uuid.uuid4()),
        task=clean_message,
        ticket_id=ticket_id,
        on_event=on_event,
    )
    if ticket_id is not None:
        root_prompt = (
            f"Review open ticket {ticket_id} from the Campus Customs board. "
            f"Request: {clean_message}\n\n"
            "Retrieve the ticket and needed facts from MCP, delegate focused tasks, "
            "and give the final operational decision."
        )
    else:
        root_prompt = clean_message
    reply = await _run_agent("boss", root_prompt, session, depth=0, path=("boss",))
    status = "budget_limited" if session.budget_limited else "error" if session.had_error else "complete"
    return AgentRunResult(
        run_id=session.run_id,
        ticket_id=ticket_id,
        model=MODEL_NAME,
        status=status,
        reply=reply,
        agents_invoked=session.agents_invoked,
        delegations=session.delegations,
        events=session.events,
    )


async def run_ticket(ticket_id: int, *, on_event: EventCallback | None = None) -> AgentRunResult:
    """Convenience entry point for the later ticket-board API."""
    return await run_team(
        "Resolve this ticket as far as the shop rules allow: verify facts with MCP, delegate only focused work, save any customer draft on the board, and prepare a human-approval request for a linked payment or affordable purchase when that is the safe action. Never execute money movement, contact anyone, promise unconfirmed fulfillment, or claim approval. If all required work is complete, report that clearly; otherwise name the exact approval or operational blocker.",
        ticket_id=ticket_id,
        on_event=on_event,
    )
