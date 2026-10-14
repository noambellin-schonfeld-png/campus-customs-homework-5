import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { AgentEvent, AgentName, AgentRunResult, ApprovalRequest, Ticket } from "./types";

const AGENTS: Array<{ id: AgentName; name: string; title: string; mark: string; color: string }> = [
  { id: "boss", name: "Boss", title: "Operations lead", mark: "B", color: "ink" },
  { id: "inventory", name: "Inventory", title: "Stock & sourcing", mark: "I", color: "teal" },
  { id: "accounting", name: "Accounting", title: "Cash & margins", mark: "A", color: "gold" },
  { id: "facilities", name: "Facilities", title: "Shop & lease", mark: "F", color: "green" },
  { id: "customer_service", name: "Customer Service", title: "Drafts & replies", mark: "C", color: "plum" },
];

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

function isResolved(ticket: Ticket): boolean {
  return ticket.resolved || ["resolved", "closed"].includes(ticket.status.toLowerCase());
}

function humanDate(value: string | undefined): string {
  if (!value) return "Shop date unavailable";
  const parsed = new Date(`${value.slice(0, 10)}T12:00:00`);
  return new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(parsed);
}

function humanTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "just now";
  return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(parsed);
}

function displayAgent(id: string): string {
  return AGENTS.find((agent) => agent.id === id)?.name ?? id.replaceAll("_", " ");
}

function detailString(value: unknown, max = 420): string {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? "";
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function latestOperationalNote(notes: string): string {
  const approval = notes.lastIndexOf("Human approval recorded:");
  const decision = notes.lastIndexOf("Human decision (");
  const start = Math.max(approval, decision);
  return start > 0 ? notes.slice(start).trim() : notes;
}

function eventCopy(event: AgentEvent): { title: string; body?: string; tone: string } {
  const detail = event.details ?? {};
  switch (event.kind) {
    case "assistant_output":
      return { title: "Thinking out loud", body: detailString(detail.text, 900), tone: "speech" };
    case "tool_call":
      return { title: `Used ${String(detail.tool ?? "a shop tool")}`, body: detailString(detail.arguments), tone: "tool" };
    case "tool_result":
      return { title: `Got a result from ${String(detail.tool ?? "the shop tools")}`, body: detailString(detail.result), tone: "result" };
    case "delegation_start":
      return { title: `Asked ${displayAgent(String(detail.recipient ?? "a teammate"))} for help`, body: detailString(detail.task), tone: "handoff" };
    case "delegation_finish":
      return { title: `${displayAgent(String(detail.recipient ?? "Teammate"))} reported back`, body: detailString(detail.reply), tone: "handoff" };
    case "agent_start":
      return { title: "Joined the ticket", body: detailString(detail.task, 420), tone: "start" };
    case "agent_finish":
      return { title: "Finished their pass", body: detailString(detail.reply, 600), tone: "finish" };
    case "agent_error":
      return { title: "Needs a retry", body: detailString(detail.error), tone: "error" };
    case "agent_limited":
    case "delegation_limited":
      return { title: "Reached the run limit", body: detailString(detail.reason), tone: "error" };
    case "tool_or_output_retry":
      return { title: "Checking a response", body: detailString(detail.message), tone: "result" };
    case "model_step":
      return { title: detail.phase === "tool_calls" ? "Choosing shop tools" : "Reviewing the ticket", tone: "thinking" };
    default:
      return { title: event.kind.replaceAll("_", " "), body: detailString(detail), tone: "result" };
  }
}

function agentSummary(agent: AgentName, events: AgentEvent[]): { text: string; tools: string[]; delegated: string[] } {
  const mine = events.filter((event) => event.agent === agent);
  const latestStatement = [...mine].reverse().find((event) => event.kind === "assistant_output");
  const toolNames = [...new Set(mine.filter((event) => event.kind === "tool_call").map((event) => String(event.details.tool)))];
  const asks = mine.filter((event) => event.kind === "delegation_start").map((event) => displayAgent(String(event.details.recipient)));
  const reply = latestStatement?.details.text;
  return {
    text: typeof reply === "string" ? reply : toolNames.length ? `Checked ${toolNames.join(", ")}.` : "Joined the ticket discussion and reviewed a focused handoff.",
    tools: toolNames,
    delegated: [...new Set(asks)],
  };
}

function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [cash, setCash] = useState<{ name: string; balance: number; date: string } | null>(null);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [runs, setRuns] = useState<Record<number, AgentRunResult>>({});
  const [runningTicket, setRunningTicket] = useState<number | null>(null);
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);
  const [approver, setApprover] = useState("Homework operator (user approved in chat)");
  const [busyApproval, setBusyApproval] = useState<number | null>(null);
  const [busyReset, setBusyReset] = useState(false);
  const [busyRefresh, setBusyRefresh] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const loadDesk = useCallback(async (quiet = false) => {
    if (!quiet) setBusyRefresh(true);
    try {
      const [ticketRows, cashRow, approvalRows, eventRows] = await Promise.all([
        api.tickets(), api.cash(), api.approvals(), api.events(),
      ]);
      setTickets(ticketRows);
      setCash(cashRow);
      setApprovals(approvalRows);
      setEvents(eventRows);
      setSelectedId((current) => current ?? ticketRows[0]?.id ?? null);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The desk could not reach its backend.");
    } finally {
      if (!quiet) setBusyRefresh(false);
    }
  }, []);

  useEffect(() => {
    void loadDesk();
    const timer = window.setInterval(() => void loadDesk(true), 4500);
    return () => window.clearInterval(timer);
  }, [loadDesk]);

  useEffect(() => {
    if (runningTicket === null) return undefined;
    const timer = window.setInterval(() => {
      void api.events().then(setEvents).catch(() => undefined);
      void api.approvals().then(setApprovals).catch(() => undefined);
      void api.cash().then(setCash).catch(() => undefined);
    }, 1100);
    return () => window.clearInterval(timer);
  }, [runningTicket]);

  const selectedTicket = tickets.find((ticket) => ticket.id === selectedId) ?? null;
  const openCount = tickets.filter((ticket) => !isResolved(ticket)).length;
  const historicalRun = useMemo<AgentRunResult | undefined>(() => {
    if (selectedId === null) return undefined;
    const groups = new Map<string, AgentEvent[]>();
    events.forEach((event) => {
      const group = groups.get(event.run_id) ?? [];
      group.push(event);
      groups.set(event.run_id, group);
    });
    const candidates = [...groups.values()].filter((group) => {
      const root = group.find((event) => event.agent === "boss" && event.kind === "agent_start");
      const task = root?.details.task;
      return typeof task === "string" && new RegExp(`Review open ticket\\s+${selectedId}\\b`).test(task);
    });
    const group = candidates[candidates.length - 1];
    if (!group) return undefined;

    const rootOutcome = [...group].reverse().find((event) =>
      event.agent === "boss" && ["agent_finish", "agent_error", "agent_limited"].includes(event.kind));
    const rootReply = rootOutcome?.details.reply ?? rootOutcome?.details.error ?? "Historical run recorded in the agent ledger.";
    const status = group.some((event) => event.kind === "agent_limited")
      ? "budget_limited"
      : group.some((event) => event.kind === "agent_error") ? "error" : "complete";
    const delegations = group.filter((event) => event.kind === "delegation_start").map((event) => {
      const recipient = String(event.details.recipient ?? "");
      const finish = group.find((candidate) => candidate.kind === "delegation_finish"
        && candidate.agent === event.agent
        && candidate.details.recipient === recipient
        && candidate.sequence > event.sequence);
      return {
        sender: event.agent,
        recipient: recipient as AgentName,
        task: String(event.details.task ?? ""),
        reply: String(finish?.details.reply ?? ""),
        status: String(finish?.details.status ?? "running"),
      };
    });
    return {
      run_id: group[0].run_id,
      ticket_id: selectedId,
      model: "gpt-6-luna",
      status,
      reply: String(rootReply),
      agents_invoked: [...new Set(group.filter((event) => event.kind === "agent_start").map((event) => event.agent))],
      delegations,
      events: group,
    };
  }, [events, selectedId]);
  const selectedRun = selectedId === null ? undefined : runs[selectedId] ?? historicalRun;
  const activeForSelection = selectedId !== null && runningTicket === selectedId;

  const runEvents = useMemo(() => {
    if (selectedRun) return events.filter((event) => event.run_id === selectedRun.run_id);
    if (activeForSelection && runStartedAt !== null) {
      return events.filter((event) => new Date(event.timestamp).getTime() >= runStartedAt - 1200);
    }
    return [];
  }, [activeForSelection, events, runStartedAt, selectedRun]);

  const invokedAgents = selectedRun?.agents_invoked ?? [...new Set(runEvents.map((event) => event.agent))];
  const isConnected = tickets.length > 0 && cash !== null && !error;
  const summaries = useMemo(() => {
    const result: Partial<Record<AgentName, ReturnType<typeof agentSummary>>> = {};
    invokedAgents.forEach((agent) => { result[agent] = agentSummary(agent, runEvents); });
    return result;
  }, [invokedAgents, runEvents]);

  async function startRun() {
    if (!selectedTicket || runningTicket !== null || isResolved(selectedTicket)) return;
    const ticketId = selectedTicket.id;
    setError("");
    setNotice("");
    setRuns((current) => {
      const next = { ...current };
      delete next[ticketId];
      return next;
    });
    setRunningTicket(ticketId);
    setRunStartedAt(Date.now());
    try {
      const result = await api.runTicket(ticketId);
      setRuns((current) => ({ ...current, [ticketId]: result }));
      setEvents((current) => {
        const byKey = new Map(current.map((event) => [`${event.run_id}:${event.sequence}`, event]));
        result.events.forEach((event) => byKey.set(`${event.run_id}:${event.sequence}`, event));
        return [...byKey.values()].slice(-500);
      });
      if (result.ticket_status === "resolved") {
        setTickets((current) => current.map((ticket) => ticket.id === ticketId
          ? { ...ticket, status: "resolved", resolved: true }
          : ticket));
        setNotice(`Ticket ${ticketId} resolved. The run summary is saved below.`);
      } else {
        setNotice(`Ticket ${ticketId} run finished with status: ${result.status.replaceAll("_", " ")}.`);
      }
      await loadDesk(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The agent run could not finish.");
      await loadDesk(true);
    } finally {
      setRunningTicket(null);
      setRunStartedAt(null);
    }
  }

  async function approve(request: ApprovalRequest) {
    if (busyApproval !== null || !approver.trim()) return;
    const kind = request.action_type === "payment" ? "payment" : "purchase";
    const ok = window.confirm(`Approve this ${kind} for ${money.format(request.amount)}? This will reduce checking cash.`);
    if (!ok) return;
    setBusyApproval(request.id);
    setError("");
    setNotice("");
    try {
      await api.approve(request.id, approver.trim());
      setNotice(`${money.format(request.amount)} approved. Checking balance refreshed.`);
      await loadDesk(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Approval was not completed.");
      await loadDesk(true);
    } finally {
      setBusyApproval(null);
    }
  }

  async function resetDesk() {
    if (runningTicket !== null || busyReset) return;
    const ok = window.confirm("Restore the working shop database from the original? This clears saved approvals and ticket changes.");
    if (!ok) return;
    setBusyReset(true);
    setError("");
    setNotice("");
    try {
      await api.reset();
      setRuns({});
      setNotice("Working database restored. The audit ledger remains intact.");
      await loadDesk(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The shop could not be reset.");
    } finally {
      setBusyReset(false);
    }
  }

  const shopDate = humanDate(cash?.date);

  return (
    <div className="desk-shell">
      <aside className="left-rail">
        <a className="brand-lockup" href="#top" aria-label="Campus Customs Operations Desk home">
          <span className="brand-stamp" aria-hidden="true">CC</span>
          <span className="brand-wordmark"><strong>Campus</strong><small>CUSTOMS · SHOP OPERATIONS</small></span>
        </a>

        <div className="rail-rule"><span>THE SHOP FLOOR</span></div>
        <div className="rail-nav active" aria-current="page"><span className="nav-glyph">▤</span><span>Operations desk</span><span className="nav-count">{openCount}</span></div>
        <div className="rail-nav muted-nav"><span className="nav-glyph">◷</span><span>Approval queue</span><span className="nav-count subtle-count">{approvals.length}</span></div>

        <section className="rail-crew" aria-label="Agent team">
          <div className="rail-rule crew-rule"><span>AT THE DESK</span><i /></div>
          {AGENTS.map((agent) => (
            <div className="crew-row" key={agent.id}>
              <span className={`crew-mark mark-${agent.color}`}>{agent.mark}</span>
              <span className="crew-label">{agent.name}</span>
              <span className={`crew-light ${runningTicket !== null && runEvents.some((event) => event.agent === agent.id) ? "on" : ""}`} />
            </div>
          ))}
        </section>

        <div className="rail-bottom">
          <div className="desk-lamp" aria-hidden="true"><span /></div>
          <p>Local shop system<br /><strong>No outside messages sent</strong></p>
          <button className="reset-link" onClick={() => void resetDesk()} disabled={runningTicket !== null || busyReset}>
            {busyReset ? "Resetting…" : "↺  Restore original data"}
          </button>
        </div>
      </aside>

      <main className="workbench" id="top">
        <header className="topbar">
          <div className="date-stamp"><span className="tiny-sun">✳</span><span>{shopDate}</span><span className="date-divider">/</span><span className="open-status"><i /> OPEN FOR BUSINESS</span></div>
          <div className="top-actions">
            <span className={`connection ${isConnected ? "" : "offline"}`}><i /> {isConnected ? "API CONNECTED" : "API OFFLINE"}</span>
            <button className="refresh-button" onClick={() => void loadDesk()} disabled={busyRefresh} aria-label="Refresh desk">
              <span className={busyRefresh ? "spin" : ""}>↻</span><span>{busyRefresh ? "Checking" : "Refresh"}</span>
            </button>
          </div>
        </header>

        <div className="page-heading">
          <div>
            <p className="eyebrow">CAMPUS CUSTOMS · DAILY OPERATIONS</p>
            <h1>The desk is <em>open.</em></h1>
            <p className="heading-note">Three tickets, five good heads, one very human final say.</p>
          </div>
          <div className="heading-sketch" aria-hidden="true"><span className="sketch-ring" /><span className="sketch-star">✳</span><span className="sketch-caption">CAMPUS SHOP<br />OPERATIONS DESK</span></div>
        </div>

        {error && <div className="notice error-notice" role="alert"><span className="notice-mark">!</span><span>{error}</span><button onClick={() => setError("")} aria-label="Dismiss error">×</button></div>}
        {notice && <div className="notice success-notice" role="status"><span className="notice-mark">✓</span><span>{notice}</span><button onClick={() => setNotice("")} aria-label="Dismiss notice">×</button></div>}

        <section className="overview-strip" aria-label="Shop overview">
          <div className="overview-card queue-overview"><span className="overview-label">OPEN TICKETS</span><strong>{String(openCount).padStart(2, "0")}</strong><span className="overview-foot">on the board today</span><span className="overview-stamp">◉</span></div>
          <div className="overview-card approval-overview"><span className="overview-label">NEEDS YOUR EYES</span><strong>{String(approvals.length).padStart(2, "0")}</strong><span className="overview-foot">{approvals.length === 1 ? "decision waiting" : "decisions waiting"}</span><span className="overview-stamp">✳</span></div>
          <div className="overview-card cash-overview"><span className="overview-label">CHECKING · AVAILABLE</span><strong>{cash ? money.format(cash.balance) : "—"}</strong><span className="overview-foot">Cash only goes out</span><span className="cash-sparkline" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /></span></div>
        </section>

        <div className="main-grid">
          <section className="ticket-column" aria-label="Ticket board">
            <div className="section-heading board-heading">
              <div><p className="eyebrow">INBOX · 03</p><h2>On the board</h2></div>
              <span className="section-aside">Select a ticket to open its file</span>
            </div>
            <div className="ticket-stack">
              {tickets.map((ticket, index) => {
                const resolved = isResolved(ticket);
                return (
                  <button
                    className={`ticket-card ${selectedId === ticket.id ? "selected" : ""} ${resolved ? "ticket-resolved" : ""}`}
                    key={ticket.id}
                    onClick={() => setSelectedId(ticket.id)}
                    disabled={runningTicket !== null && runningTicket !== ticket.id}
                    aria-pressed={selectedId === ticket.id}
                  >
                    <span className="ticket-index">0{index + 1}</span>
                    <span className="ticket-main-copy"><strong>{ticket.subject}</strong><small>{ticket.requester}</small></span>
                    <span className={`ticket-status ${resolved ? "status-resolved" : "status-open"}`}><i />{resolved ? "RESOLVED" : ticket.status.replaceAll("_", " ").toUpperCase()}</span>
                    <span className="ticket-arrow" aria-hidden="true">↗</span>
                  </button>
                );
              })}
              {tickets.length === 0 && <div className="empty-card">Your board is quiet. Check the backend connection.</div>}
            </div>

            {selectedTicket && (
              <article className="ticket-file">
                <div className="file-topline"><span className="file-id">TICKET / {selectedTicket.id}</span><span className={isResolved(selectedTicket) ? "file-state resolved-state" : "file-state"}>{isResolved(selectedTicket) ? "✓  CLOSED OUT" : "●  OPEN FILE"}</span></div>
                <div className="file-body">
                  <div className="file-title-row">
                    <div><p className="eyebrow">{selectedTicket.type.replaceAll("_", " ").toUpperCase()}</p><h2>{selectedTicket.subject}</h2><p className="requester-line">Filed by <strong>{selectedTicket.requester}</strong></p></div>
                    <span className="ticket-seal" aria-hidden="true">{String(selectedTicket.id).slice(-2)}</span>
                  </div>
                  <div className="ticket-facts">
                    {selectedTicket.sku && <div className="fact"><span>ITEM</span><strong>{selectedTicket.sku}</strong></div>}
                    {selectedTicket.size && <div className="fact"><span>SIZE</span><strong>{selectedTicket.size}</strong></div>}
                    {selectedTicket.qty !== null && <div className="fact"><span>QUANTITY</span><strong>{selectedTicket.qty} units</strong></div>}
                    {selectedTicket.invoice_id !== null && <div className="fact"><span>LINKED INVOICE</span><strong>#{selectedTicket.invoice_id}</strong></div>}
                    {selectedTicket.lease_id !== null && <div className="fact"><span>LEASE</span><strong>#{selectedTicket.lease_id}</strong></div>}
                  </div>
                  {selectedTicket.notes && <blockquote className="ticket-note"><span>LATEST BOARD NOTE</span><p>“{latestOperationalNote(selectedTicket.notes)}”</p></blockquote>}
                  <div className="file-actions">
                    <div className="run-caption"><span className="run-pulse" /><span>{activeForSelection ? "The team is working this file" : selectedRun ? `Last run · ${selectedRun.status.replaceAll("_", " ")}` : "The Boss will coordinate a focused review"}</span></div>
                    <button className="run-button" onClick={() => void startRun()} disabled={isResolved(selectedTicket) || runningTicket !== null}>
                      <span className="run-icon">{activeForSelection ? <span className="button-loader" /> : "↗"}</span>
                      {activeForSelection ? "Team at work…" : selectedRun ? "Run team again" : "Start the team"}
                    </button>
                  </div>
                </div>
                <div className="file-footer"><span>✳  NOTES STAY ON THE BOARD</span><span>NO CUSTOMER OR VENDOR IS CONTACTED</span></div>
              </article>
            )}

            <section className="agent-summary-section">
              <div className="section-heading summary-heading">
                <div><p className="eyebrow">HANDOFF NOTES</p><h2>{selectedRun ? "Who did what" : "Meet the crew"}</h2></div>
                {selectedRun && <span className="run-id">RUN {selectedRun.run_id.slice(0, 8).toUpperCase()}</span>}
              </div>
              {!selectedRun && <p className="summary-intro">Specialists join only when their work helps this ticket. A quiet seat is part of a focused plan.</p>}
              <div className="agent-grid">
                {AGENTS.map((agent) => {
                  const summary = summaries[agent.id];
                  const isInvoked = invokedAgents.includes(agent.id);
                  const isWorking = activeForSelection && runEvents.some((event) => event.agent === agent.id);
                  return (
                    <article className={`agent-card agent-${agent.color} ${!isInvoked && selectedRun ? "agent-idle" : ""}`} key={agent.id}>
                      <div className="agent-card-head"><span className={`agent-mark mark-${agent.color}`}>{agent.mark}</span><div><strong>{agent.name}</strong><small>{agent.title}</small></div><span className={`agent-state ${isWorking ? "working" : isInvoked ? "finished" : "standby"}`}>{isWorking ? "IN MOTION" : isInvoked ? "ON TICKET" : selectedRun ? "STANDBY" : "READY"}</span></div>
                      {summary ? <>
                        <p className="agent-summary-text">{summary.text}</p>
                        {summary.tools.length > 0 && <div className="tool-chips">{summary.tools.map((tool) => <span key={tool}>{tool}</span>)}</div>}
                        {summary.delegated.length > 0 && <small className="delegation-foot">Asked {summary.delegated.join(", ")} for help</small>}
                      </> : <p className="agent-summary-text muted-summary">{selectedRun ? "This specialist was left out of this ticket's plan." : "Ready when a ticket calls for this specialty."}</p>}
                    </article>
                  );
                })}
              </div>
            </section>
          </section>

          <aside className="right-column">
            <section className="approval-panel" aria-label="Human approval queue">
              <div className="approval-panel-head"><div><p className="eyebrow">HUMAN CHECKPOINT</p><h2>Needs your say</h2></div><span className="approval-count">{approvals.length}</span></div>
              <p className="approval-explainer">Agents can prepare a request. Only you can send money out.</p>
              <label className="approver-field">APPROVAL RECORDED AS<input value={approver} onChange={(event) => setApprover(event.target.value)} maxLength={120} /></label>
              {approvals.length === 0 ? (
                <div className="approval-empty"><span className="empty-stamp">✓</span><strong>No decisions waiting</strong><small>The queue will appear here when an agent prepares a payment or purchase.</small></div>
              ) : (
                <div className="approval-list">
                  {approvals.map((request) => (
                    <article className="approval-card" key={request.id}>
                      <div className="approval-card-top"><span className={`approval-type ${request.action_type === "payment" ? "type-payment" : "type-purchase"}`}>{request.action_type === "payment" ? "PAYMENT" : "PURCHASE"}</span><span>#{request.id} · T{request.ticket_id}</span></div>
                      <strong className="approval-amount">{money.format(request.amount)}</strong>
                      <p className="approval-detail">{request.details}</p>
                      <div className="approval-card-meta"><span>{request.account ?? "checking"}</span><span>Pending your review</span></div>
                      <button className="approve-button" onClick={() => void approve(request)} disabled={busyApproval !== null || !approver.trim()}>
                        {busyApproval === request.id ? <><span className="button-loader" /> Processing…</> : <>{request.action_type === "payment" ? "Approve payment" : "Approve purchase"} <span>↗</span></>}
                      </button>
                    </article>
                  ))}
                </div>
              )}
              <div className="approval-rule"><span>YOU STAY IN CONTROL</span><span aria-hidden="true">✳</span></div>
            </section>

            <section className="cash-card" aria-label="Checking account">
              <div className="cash-card-top"><span className="cash-icon">$</span><span className="cash-chip"><i /> LIVE BALANCE</span></div>
              <p className="eyebrow">SHOP CHECKING</p>
              <strong className="cash-total">{cash ? money.format(cash.balance) : "—"}</strong>
              <div className="cash-divider"><span>AVAILABLE TO SPEND</span><span>{cash?.date ?? "—"}</span></div>
              <div className="cash-note"><span className="cash-note-mark">↘</span><span>Balance updates after each approved outflow. No sales are counted in this ledger.</span></div>
              <div className="ledger-lines" aria-hidden="true"><i /><i /><i /><i /></div>
            </section>

            <section className="live-panel" aria-label="Live team activity">
              <div className="live-panel-heading"><div><p className="eyebrow">THE BACK ROOM</p><h2>Live activity</h2></div><span className={`live-dot ${activeForSelection ? "live-now" : ""}`} /></div>
              {activeForSelection && <p className="live-ticket-label">TICKET {selectedId} · TEAM IN SESSION</p>}
              <div className="event-list" aria-live="polite" aria-relevant="additions text">
                {runEvents.length === 0 ? (
                  <div className="activity-empty"><span className="activity-illustration" aria-hidden="true">☕</span><strong>{activeForSelection ? "Connecting the team…" : "A quiet moment at the desk"}</strong><p>{activeForSelection ? "Boss is reading the ticket and calling the right first specialist." : "Start a ticket run to see handoffs, shop lookups, and decisions unfold."}</p></div>
                ) : runEvents.slice(-45).reverse().map((event) => {
                  const copy = eventCopy(event);
                  const agent = AGENTS.find((item) => item.id === event.agent);
                  return (
                    <article className={`event-item event-${copy.tone}`} key={`${event.run_id}-${event.sequence}`}>
                      <span className={`event-avatar mark-${agent?.color ?? "ink"}`}>{agent?.mark ?? "·"}</span>
                      <div className="event-content"><div className="event-meta"><strong>{agent?.name ?? displayAgent(event.agent)}</strong><time>{humanTime(event.timestamp)}</time></div><b>{copy.title}</b>{copy.body && <p>{copy.body}</p>}</div>
                    </article>
                  );
                })}
              </div>
              <div className="activity-footer"><span>LIVE FROM THE AGENT LEDGER</span><span>↻ AUTO-REFRESH</span></div>
            </section>
          </aside>
        </div>

        <footer className="workbench-footer"><span>Campus Customs Operations · Shop desk</span><span>Built for careful work, good notes, and human judgment.</span><span>CC / 05</span></footer>
      </main>
    </div>
  );
}

export default App;
