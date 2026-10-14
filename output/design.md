# Campus Customs Agent Desk — Design Notes

## Direction

The dashboard feels like a well-kept campus shop's real operations desk: a little archival, a little collegiate, and calm enough for careful decisions. Warm paper and evergreen ink set the base; a copper ticket mark and brass details add the feeling of a stamped order slip. A small seal, dotted paper texture, desk-lamp motif, and restrained shop-floor labels give it a sense of place without making the information harder to scan.

## Layout

- A narrow left rail anchors the Campus Customs identity, the ticket and approval counts, and the five-person crew.
- The workbench opens with the shop date and a compact three-part snapshot for open tickets, decisions waiting, and checking cash.
- The center column is the actual desk: a selectable ticket inbox, a larger ticket file with its recorded facts and note, the team-run control, and a short per-agent handoff summary.
- A right column keeps human approvals, the live checking balance, and the event ledger visible while an operator reads a ticket.
- At tablet width the side rail becomes a compact icon rail; on phones the ticket file and approval cards become a single readable stack.

## Agent voices and activity

The live event ledger gives each role a distinct letter mark and color: Boss uses ink, Inventory uses teal, Accounting uses brass, Facilities uses leaf green, and Customer Service uses plum. Agent statements read like small desk notes; tool calls and returned facts use quieter labels, while delegations are marked as handoffs. The run summary groups only the agents who actually took part and lists the shop tools they used. Agents who were not needed stay visibly on standby, making the team's routing understandable without implying that every specialist touched every ticket.

## Resolved tickets and cash

Resolved tickets receive a muted green status stamp and a check mark; open work carries a warm amber dot. The board refreshes from the backend; a finished model loop by itself does not close a ticket. The latest audited run and latest human-approved or human-decision note return when an operator selects a ticket after reload. Approved rent and purchase orders close their linked ticket, while a human may explicitly close a ticket after reviewing its recorded facts. Checking is shown as a prominent green ledger card with the authoritative balance and date. Its note explains that the homework models outflows only. Approval requests sit above it in a warm paper panel; the human name is visible, each amount is explicit, and approving requires a confirmation before the API executes the outflow. The balance and queue refresh immediately after approval.

## Small touches for the person at the desk

The interface uses generous spacing, paper-like cards, quiet micro-labels, and short pieces of copy instead of a dense admin table. A lamp and coffee-cup empty state make the idle desk feel inhabited; a live dot and small pulse signal work in progress without turning the screen into a noisy alert wall. The approval area stays visually separate from agent activity, reinforcing that recommendations and human decisions are different steps. Resetting the working copy is available from the rail but asks for confirmation. Customer drafts remain on the board, and the footer keeps the promise visible: no customer or vendor is contacted from this desk.


## Resolved run evidence

The board restores the selected ticket's latest recorded agent run from the append-only audit after refresh, so the handoff cards remain useful after a run ends. The Problem 9 evidence page embeds a separate real screenshot for each selected resolved ticket; its captions state the actual outcome and the checking balance.
