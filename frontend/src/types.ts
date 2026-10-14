export type AgentName =
  | "boss"
  | "inventory"
  | "accounting"
  | "facilities"
  | "customer_service";

export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  status: string;
  notes: string | null;
  created_at: string;
  resolved: boolean;
}

export interface AgentEvent {
  run_id: string;
  sequence: number;
  timestamp: string;
  agent: AgentName;
  kind: string;
  depth: number;
  details: Record<string, unknown>;
}

export interface ApprovalRequest {
  id: number;
  ticket_id: number;
  action_type: "payment" | "purchase_order";
  reference_type: string | null;
  reference_id: number | null;
  vendor_id: number | null;
  sku: string | null;
  size: string | null;
  quantity: number | null;
  amount: number;
  account: string | null;
  details: string;
  status: string;
  created_at: string;
}

export interface CashAccount {
  name: string;
  balance: number;
  date: string;
}

export interface AgentRunResult {
  run_id: string;
  ticket_id: number;
  model: string;
  status: "complete" | "budget_limited" | "error";
  reply: string;
  agents_invoked: AgentName[];
  delegations: Array<{
    sender: AgentName;
    recipient: AgentName;
    task: string;
    reply: string;
    status: string;
  }>;
  events: AgentEvent[];
  ticket_status?: string;
}
