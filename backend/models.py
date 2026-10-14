"""Shared request, event, and result types for the Campus Customs agent team."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
RunStatus = Literal["complete", "budget_limited", "error"]


class AgentEvent(BaseModel):
    run_id: str
    sequence: int
    timestamp: str
    agent: AgentName
    kind: str
    depth: int = 0
    details: dict[str, Any] = Field(default_factory=dict)


class DelegationRecord(BaseModel):
    sender: AgentName
    recipient: AgentName
    task: str
    reply: str = ""
    status: Literal["running", "complete", "error", "limited"] = "running"


class AgentRunResult(BaseModel):
    run_id: str
    ticket_id: int | None = None
    model: Literal["gpt-6-luna"] = "gpt-6-luna"
    status: RunStatus = "complete"
    reply: str
    agents_invoked: list[AgentName] = Field(default_factory=list)
    delegations: list[DelegationRecord] = Field(default_factory=list)
    events: list[AgentEvent] = Field(default_factory=list)
    audit_path: str = "output/audit_trail.json"
