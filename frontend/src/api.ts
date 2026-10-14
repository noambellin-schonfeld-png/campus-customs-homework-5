import type { AgentEvent, AgentRunResult, ApprovalRequest, CashAccount, Ticket } from "./types";

export const API_BASE = "http://localhost:8000";

interface TicketResponse { tickets: Ticket[] }
interface ApprovalResponse { approvals: ApprovalRequest[]; count: number }
interface EventResponse { events: AgentEvent[]; count: number }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    throw new Error("The operations API is offline. Start the backend at localhost:8000 and try again.");
  }

  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      else if (body.detail) message = JSON.stringify(body.detail);
    } catch {
      // Keep the concise HTTP message if the response was not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  tickets: async () => (await request<TicketResponse>("/api/tickets")).tickets,
  cash: () => request<CashAccount>("/api/cash"),
  approvals: async () => (await request<ApprovalResponse>("/api/approvals")).approvals,
  events: async () => (await request<EventResponse>("/api/events?limit=500")).events,
  runTicket: (ticketId: number) => request<AgentRunResult>(`/api/tickets/${ticketId}/run`, { method: "POST" }),
  approve: (approvalId: number, approvedBy: string) => request<Record<string, unknown>>(
    `/api/approvals/${approvalId}/approve`,
    { method: "POST", body: JSON.stringify({ approved_by: approvedBy }) },
  ),
  reset: () => request<{ reset: string }>("/api/reset", { method: "POST" }),
};
