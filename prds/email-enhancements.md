# PRD: Email command enhancements — triage, smart replies, subscription cleanup

**Status**: Draft — ideas session 2026-06-10, pending review
**Date**: 2026-06-10
**Owner**: alex
**Prereqs shipped**: Interactive List v1 (jarvis-command-sdk v0.3.2, jarvis-node-mobile v0.1.20, jarvis-node-setup v0.1.113). Email package (jarvis-cmd-email) with Gmail OAuth (`gmail.modify` scope) + full IMAP path (Proton Bridge / Fastmail / Yahoo / Outlook presets).

## Overview

Make email the flagship consumer of Jarvis's generic surfaces. Today the command does
list/read/search/send/reply/archive/trash/star with fast-paths, and the alerts agent fires
VIP/urgent/digest notifications as dead-end text. This PRD adds five pieces, ordered by
dependency:

1. **`JarvisInbox` SDK facade** — packages can post inbox items (today only built-ins can)
2. **Mailbox verbs** — mark read/unread, unstar, forward, batch callback
3. **Interactive inbox triage** — on-demand + daily digest as an interactive list
4. **Smart-reply agent** — LLM-filtered important mail pushed with a pre-written draft
5. **Subscription cleanup** — never-read senders × List-Unsubscribe, one-tap bulk unsubscribe

Pieces 3 and 5 are the Phase 4 "second consumer" for the interactive list (PRD:
generic-interactive-view.md) — they exercise the shapes shopping list didn't: plain checkbox
rows, no gates, multiple actions, destructive styles. Piece 4 deliberately does NOT use the
interactive list (see decision 3).

**Key enabling facts** (verified 2026-06-10):
- OAuth scope is already `gmail.modify` — every verb below fits, no re-auth migration.
- `services/node_llm_client.ask_llm` exists and is proven by jarvis-cmd-news's filter.
- The IMAP service mirrors the Gmail interface, so most features land on both providers.

## Design Decisions

**1. `JarvisInbox` is the load-bearing piece.** jarvis-cmd-email is a Pantry package; the
only package→notification path today is `Alert` (title/summary/priority — no metadata, no
category, no buttons). Built-ins post inbox items via node-internal `clients/rest_client`.
The SDK gets a `JarvisInbox` facade following the `JarvisStorage` backend-injection pattern:

```python
JarvisInbox(command_name).post(
    title=..., summary=..., body=...,
    category=...,                  # e.g. InteractiveList.CATEGORY
    metadata=...,                  # e.g. InteractiveList(...).to_dict()
    interactive_elements=[...],    # optional — InboxDetail-surface buttons
    create_push_notification=True, target_type="user", user_id=...,
)
```

The node runtime implements the backend (same `POST /api/v0/node/inbox-item` the export
command uses; CC injects `node_id`). This completes the platform pitch: one Python file →
voice + push + interactive phone UI, for *community packages*, not just built-ins.
*Rejected*: extending `Alert` with metadata/category — alerts are a rate-limited,
TTL-expiring queue with its own semantics; inbox posting is a different act and the export
command already proved the direct path.

**2. Triage rows default UNCHECKED.** Unlike shopping export (everything selected, user
prunes), triage actions are semi-destructive (archive) or state-changing (mark read). The
user checks what to act on. Actions: `Mark {n} read` (primary), `Archive {n}` (secondary),
`Star {n}` (secondary). All actions receive the same selected set; the callback name
disambiguates. Row: key=message id, label=sender (≤120), caption=subject (≤200),
control=checkbox. The list is a snapshot — acting on it doesn't refresh it (live refresh
stays punted per the interactive-list PRD); the result's `detail_lines` reports what happened
and re-running the command gets a fresh list.

**3. Smart-reply rides the InboxDetail surface, not the interactive list.** A reply draft is
long multi-line text + two buttons — the wrong shape for 200-char list captions, and exactly
the shape InboxDetail already renders generically (full body + `interactive_elements`
dispatching to `@callback`s). Item: title "Reply ready — {sender}", body = original snippet +
the draft, elements **[Send reply]** → `@callback("send_draft_reply")` (existing reply path,
threaded via `thread_id`) and **[Ignore]** → `@callback("dismiss_draft")`. The tap IS the
confirmation — the draft is on screen. Nothing is ever auto-sent. *Rejected*: a custom
draft-editor screen (decision 1 of the interactive-list PRD: rare and deliberate; editing a
draft is what mobile chat reply is for).

**4. The importance filter transplants the news pattern verbatim.** A user-written rule
secret (`EMAIL_NOTIFICATION_FILTER`, e.g. "clients, invoices, anything from my kid's
school"), one `ask_llm` call per agent run, strict JSON-array-of-indices output, **fail
closed**: filter set + LLM unreachable/garbled ⇒ no alerts, retry next run. Reply-worthiness
and the draft are a second `ask_llm` call on the matched email's body. Drafts from local
models will be serviceable, not eloquent — acceptable because the failure mode is "one
mediocre draft you ignore."

**5. Unsubscribe = never-read detection × List-Unsubscribe actuation.**
- *Candidates*: per-sender aged-unread ratio over a 90-day window (`from:sender` total vs
  `is:unread older_than:7d`), sender has ≥3 messages, all/nearly-all unread. Gmail prefilter:
  `category:promotions OR category:updates`; IMAP skips the prefilter.
- *Actuators*, in order: RFC 8058 one-click (HTTP POST to the `List-Unsubscribe-Post` URL —
  mandatory for bulk senders since the 2024 Gmail/Yahoo rules, so coverage is high);
  `mailto:` unsubscribe sent through the user's own send path; otherwise the sender is
  reported in the result as needing a manual click.
- *Surface*: interactive list — checkbox row per sender, caption "{n} unread in 90 days",
  default unchecked, action `Unsubscribe {n}` (style destructive). Optional second action
  `Unsubscribe + archive their mail {n}`.
- *Safety*: never auto-unsubscribe; candidates only ever surface as unchecked checkboxes.
- *Plumbing*: `EmailMessage` gains `unsubscribe_url` / `unsubscribe_post` / `unsubscribe_mailto`
  (headers are parsed today and dropped).

**6. Mailbox verbs are completions, not features.** `mark_read`/`mark_unread` =
`modify_labels` on `UNREAD` (method exists, scope covers it); `unstar` exists in the service,
just unexposed; `forward` = compose-with-quote on the existing send path. Plus a batch
`@callback("triage_apply")` accepting `{action, selected: [{key}]}` from piece 3. Fast-paths
for "mark email 2 as read" / "mark all as read".

**7. Per-user scoping is consciously deferred for agents.** Mail credentials are already
user-scoped, but background agents resolving user-scoped secrets is blocked on the
`_build_secrets`/ContextVar Phase 3 work (May refactor). Single-primary-user households work
today; the filter/VIP secrets stay integration-scoped until that lands. Revisit then.

## Phases

**Phase 1 — `JarvisInbox`** (jarvis-command-sdk + jarvis-node-setup): facade + backend +
forge hints + tests. SDK patch bump.
**Phase 2 — verbs + triage** (jarvis-cmd-email): mark read/unread, unstar, forward,
`triage_apply` callback, "triage my inbox" action emitting the interactive list, daily digest
upgraded to the same payload. This is the interactive-list second consumer.
**Phase 3 — smart-reply agent** (jarvis-cmd-email): `EMAIL_NOTIFICATION_FILTER` +
fail-closed LLM filter + draft generation + Send/Ignore item via `JarvisInbox`.
**Phase 4 — subscription cleanup** (jarvis-cmd-email): unsubscribe header retention,
never-read scan ("clean up my subscriptions" on-demand first; scheduled later if wanted),
RFC 8058/mailto actuators, interactive list + result reporting.

## Punts (explicit)

- Editing the draft in place (use mobile chat reply; revisit only with evidence)
- Auto-send for any tier of sender — never in this PRD
- Attachments, contact extraction, calendar-invite parsing, snooze, custom labels
- Multi-account-per-user
- Scheduled auto-scan for unsubscribe candidates (on-demand first; cadence is an open question)
- Per-user filter/VIP secrets in agents (decision 7 — blocked on `_build_secrets` Phase 3)

## Open Questions (for the build session)

1. Digest-as-triage: does the daily digest item *replace* the text digest or accompany it?
   (Lean: replace — same information, strictly more useful.)
2. Unsubscribe thresholds: window 90d, min messages 3, unread ratio ~100% — tune on Alex's
   real mailbox during testing.
3. Does `triage_apply` need its own rate limiting / max batch size? (Lean: no — capped at
   100 rows by the payload contract; Gmail modify quotas are generous.)
4. Smart-reply frequency guard: max drafts per day? (Lean: reuse the alert rate-limit
   pattern, max 5/run, dedup by message id.)
5. `JarvisInbox` push defaults: opt-in per post (matching `create_push_notification`
   semantics) — confirm no command should ever push-by-default.
