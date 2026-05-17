# PRD: Node Owner

**Status**: Draft. Prerequisite for OpenClaw integration Phase 1 and a foundation for several future per-user features.

## Overview

Every node gets a single owner — a user whose identity is the "primary" for that node. The owner is set automatically at provisioning to whoever set the node up. Admins can reassign ownership through a dropdown in Hardware Settings → Device Info in the mobile app.

The owner is used to resolve user-scoped secrets when agents run on the node, to attribute the node in the mobile UI, and as a stable hook for future per-user integrations (Gmail OAuth, OpenClaw Gateway, etc.).

## Motivation

User-scoped secrets (e.g. `OPENCLAW_GATEWAY_URL`, future per-user OAuth tokens) need a deterministic `user_id` to resolve against when an agent runs on a node, independent of who is speaking at any given moment. Today, agent code that needs user-scoped data falls through to `user_id=None` because the agent scheduler never sets a user context — integrations silently degrade.

Beyond unblocking OpenClaw, the owner concept enables:
- Per-user OAuth integrations on a per-node basis (the "owner's Gmail" model)
- Notification routing for node-level events ("Alex's office node went offline")
- Attribution and display labels in the mobile app

## Scope

**In scope**
- Add `owner_user_id` to the `nodes` table
- Auto-assign during provisioning to the registering user
- Introduce a per-household role concept (admin / power_user / member)
- Mobile UI for admins to reassign ownership

**Out of scope**
- Per-node access control (who can *use* the node) — separate concern
- Multi-owner / co-owner ownership — keep singular for v1
- Cross-household ownership (a node owned by a user in a different household) — not supported

## Architecture

### Schema changes

`jarvis-auth`:

- `nodes.owner_user_id` — FK to `users.id`, nullable to support migration of existing nodes.
- `household_memberships.role` — new column, enum `{admin, power_user, member}`, default `member`.

Alembic migration plan:

1. Add the two columns (both nullable / defaulted).
2. Backfill `household_memberships.role`: the oldest (lowest `id`) membership in each household → `admin`. The rest → `member`. Power users are opt-in via the UI later.
3. Backfill `nodes.owner_user_id`: for each node, pick the household's admin. If a node has no household admin yet (edge case), leave null; mobile will prompt the next admin who signs in to pick.

### Roles introduced

Power users can do almost everything an admin can. The boundary is narrow: admins are the only role that can change other people's roles or delete the household. Everything else is shared.

| Action | `admin` | `power_user` | `member` |
|---|---|---|---|
| Voice commands | yes | yes | yes |
| Install / remove Pantry packages | yes | yes | no |
| Enroll voice guests | yes | yes | no |
| Eligible to own a node | yes | yes | no |
| Reassign node owner | yes | yes | no |
| Invite new members | yes | yes | no |
| Remove members from household | yes | yes (cannot remove admins) | no |
| Promote / demote membership roles | yes | no | no |
| Delete the household | yes | no | no |

- Every household has at least one admin.
- Power users cannot remove admins (only admins can demote-then-remove).
- Admins cannot demote themselves if they are the last admin.

### Provisioning flow

Today: mobile app (logged in as user X) sends provisioning payload to the Pi over the AP-mode setup network → Pi calls back to command-center → CC calls jarvis-auth to create the node row.

Change: the provisioning payload carries the user JWT. jarvis-auth records `nodes.owner_user_id = jwt.user_id` at node-create time. No new UI step at setup — provisioner is owner by default, by design.

If the provisioner isn't `admin` or `power_user` in their household (i.e. they're a `member`), the node is still created but owner is set to the first admin in the household and the provisioner is shown a "Owner set to {admin name}" toast.

### Mobile UI: owner reassignment

Location: **Hardware Settings → Device Info → Owner**.

- Row shows current owner's display name.
- Visible to everyone in the household.
- Tappable only by `admin` users.
- Tap → bottom sheet picker → list of household members with `role IN (admin, power_user)` → confirm → PATCH the node.

### Agent scheduler integration

Once owner exists, `AgentSchedulerService` sets `jarvis_command_sdk.context.set_current_user_id(node.owner_user_id)` before invoking each agent's `run()`. This is the line that unblocks OpenClaw integration Phase 1, but it also makes every existing agent that reads user-scoped secrets behave correctly.

### Leaving / being removed from a household

When a user leaves a household (or is removed by an admin/power_user), their personal data tied to that household's nodes is deleted. The flow:

1. The user (or the admin initiating the removal) sees a confirmation:

   > Leaving will delete your personal data on this household's nodes:
   > - User-scoped secrets (e.g. Gmail tokens, OpenClaw gateway URL)
   > - Personal memories ("your favorite color is blue", etc.)
   > - Voice profile
   >
   > This cannot be undone. Continue?

2. On confirmation, jarvis-auth orchestrates:
   - Delete `secrets` rows where `user_id = leaving_user.id` (all scopes that include user_id).
   - Delete `memories` rows where `subject_type='user' AND subject_id = leaving_user.id`.
   - Delete the user's voice profile artifacts.
   - If the leaving user owned any nodes, reassign each to the household's first admin (lowest membership id). The new owner is shown a notification.
   - Remove the `household_memberships` row.

3. Blocked states (UI prevents the action, returns 409):
   - Leaving user is the **last admin** in the household. Promote another admin first.
   - Leaving user is the **last member** in the household. Deleting the household is the intended action; route to the household-delete flow instead.

The same flow runs whether the user voluntarily leaves or an admin removes them — the only difference is who sees the confirmation dialog. An admin removing someone is committing to the same cascade on that user's behalf.

The cascade emits structured `JarvisLogger` events at the `info` level for each deletion step (e.g. `event="leave_cascade", action="delete_user_secrets", user_id=…, count=…`) so the trail is searchable through standard log tooling. No separate audit table.

## API changes

`jarvis-auth`:

- `PATCH /nodes/{node_id}/owner` — body: `{owner_user_id}`. Requires `admin` role in the node's household. Returns updated node.
- `GET /households/{household_id}/members` — extend response to include `role`.
- `PATCH /households/{household_id}/members/{user_id}/role` — body: `{role}`. Admin-only. Cannot demote the last admin.

`jarvis-node-mobile`:

- New picker sheet for owner selection.
- Role badge on member rows in household settings.

## Phased plan

1. **Schema + migration** (`jarvis-auth`)
2. **Provisioning auto-assign** (`jarvis-auth`, `jarvis-command-center`, `jarvis-node-setup`, `jarvis-node-mobile`)
3. **Owner reassignment UI** (`jarvis-node-mobile`)
4. **Role-based gating throughout mobile** (`jarvis-node-mobile`, with `jarvis-auth` enforcing on the API side)
5. **Agent scheduler uses owner context** (`jarvis-node-setup`) — *this is the unblock for OpenClaw Phase 1*

## Design decisions

**1. Singular owner.** Multi-owner / co-owner adds significant complexity (secret resolution, conflict cases, mobile UX) for marginal value. Pick one. Admins can reassign anytime.

**2. Provisioner = owner by default.** No extra setup step; the person bothering to set up the node is almost always the right owner.

**3. Three roles, not two.** `member` exists so households can have voice-only adults who don't need any management capability. `power_user` ≈ `admin` minus two specific operations — changing other members' roles and deleting the household. The intuition: admins control *who is in charge* and *whether the household exists*; everyone else with capability is a power user. This keeps the admin gate narrow and meaningful while letting households comfortably grant power-user status broadly (spouse, older kid with a phone, etc.).

**4. Roles are per-household, not global.** `is_superuser` stays as a global admin flag (today's behavior — system-wide privileges). Household roles are scoped to a single household.

**5. Migration assigns admin by recency.** Lowest `household_memberships.id` → admin per household. Reasonable default; admins can adjust afterward.

## Open questions

- **Edge case: last admin demotes themselves.** API enforces "can't demote the last admin." Mobile should show that constraint in the UI.
- **Existing nodes with no owner after backfill.** Mobile prompts the first admin who opens the app per affected node, with a "set owner" call-to-action.

## Cross-cutting with the voice-profile PRD

This PRD introduces `admin` / `power_user` / `member` roles. The voice-profile-for-non-users PRD relies on those roles to gate guest enrollment (admin + power_user can enroll; member cannot). Both PRDs should land in coordinated batches so the role enforcement is consistent across surfaces.
