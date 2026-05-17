# PRD: Voice Profiles for Non-Users

**Status**: Draft. Uses the per-household role enum already in `jarvis-auth` (`HouseholdRole.{ADMIN, POWER_USER, MEMBER}`) and the existing `required_role` gating helpers. Cross-cuts with `node-owner.md` only at the mobile settings UI.

## Overview

Add support for voice profiles that aren't tied to a Jarvis account. A household admin can create a named "guest" — a child, a frequent visitor, a non-phone-having family member — enroll their voice, and from then on the speaker-ID pipeline can recognize and attribute them. Guests have stable identity, can have memories, but no login, no credentials, and no household-management rights.

## Motivation

Today voice profiles are 1:1 with `users` in `jarvis-auth`. Speaker identification returns a `user_id` or nothing. That excludes:

- **Children**: too young for an account but the family wants Jarvis to know who they are ("Bobby is asking about his homework"), remember things about them, and eventually apply restrictions.
- **Frequent guests**: extended family, partners, regulars. The household doesn't want them as full members (no shared invite codes, secrets, settings access) but does want them recognized.
- **Multi-person utterances**: "tell mom I'm running late" — Mom needs to be a recognizable target identity even if she isn't a phone-having user.

Without this, Jarvis treats every non-account speaker as an anonymous voice. The system loses personalization, memory, and any future per-person rules.

## Scope

**In scope (Phase 1)**
- New entity for non-user voice identities (working name `household_guest`)
- Voice enrollment + identification across the user + guest pool
- Speaker-ID pipeline returns a discriminated identity (user vs guest)
- Memory service stores memories keyed by either user or guest identity
- Mobile UI for admins / power users to CRUD guests

**Out of scope (Phase 1)**
- Per-guest command restrictions / parental controls (Phase 2)
- Quiet hours, curfews, time-of-day rules per guest (Phase 2)
- Authenticating a guest into the mobile app (never — they're voice-only by design)
- Guests installing packages or holding secrets (never — that's what `users` are for)

## Architecture

### Data model

New table in `jarvis-auth`: `household_guests`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | Primary key |
| `household_id` | FK → households | The household this guest belongs to |
| `display_name` | string | "Bobby", "Mom", "Steve from next door" |
| `relationship` | enum | `child` / `family` / `friend` / `other` — informs LLM context + future restriction defaults |
| `created_by_user_id` | FK → users | Who enrolled them; for audit |
| `created_at` | timestamp | |

Voice profile audio extends the existing `voice_profiles/{household_id}/...` layout:
- Existing: `voice_profiles/{household_id}/{hash(user_id)}.wav`
- New: `voice_profiles/{household_id}/guests/{hash(guest_id)}.wav`

### Speaker identity (the wire change)

Today the whisper API returns:

```
{ text, speaker: { user_id, confidence } }
```

Change to a discriminated identity:

```
{
  text,
  speaker: {
    identity_type: "user" | "guest" | "unknown",
    identity_id: int | uuid | null,
    display_name: string | null,
    confidence: float
  }
}
```

Command-center's speaker resolver fans out:
- `identity_type=user` → existing user-lookup path; pulls display name + memories from `users`.
- `identity_type=guest` → new lookup against `household_guests`; pulls display name + memories scoped to the guest.
- `identity_type=unknown` → anonymous; no memories injected, LLM addressed without a name.

### Memory service

Today, `memories` in `jarvis_command_center` is keyed by `(user_id, key)`. Migrate to polymorphic subject:

| Column | Type | Notes |
|---|---|---|
| existing `user_id` | int, nullable | Phased out; written to during transition for backward compat reads |
| new `subject_type` | enum `{user, guest}` | |
| new `subject_id` | string (stores int or uuid as text) | Polymorphic key |

Migration:

1. Add new columns, default `subject_type='user'`, `subject_id = user_id::text`.
2. New writes use the polymorphic columns only.
3. Reads prefer polymorphic columns, fall back to `user_id` for legacy rows.
4. Eventually drop `user_id` column after a release cycle.

`remember` / `forget` tools route by the speaker's identity type — no change to their interface from the LLM's POV.

### Whisper API changes

- `POST /voice-profiles/enroll-guest` — body: `{household_id, guest_id, audio}`. Adds samples to the guest's profile.
- `DELETE /voice-profiles/guest/{guest_id}` — removes the guest's voice samples.
- `GET /voice-profiles/identify` — match space extends to include guest embeddings; response shape changes to discriminated identity as above.
- Existing user enrollment endpoints unchanged.

### Mobile UI

New section: **Household Settings → Voice Identities** (or similar). Two lists:

1. **Members** — existing Jarvis users in the household, with enrollment status. Each user can re-enroll their own voice from their device.
2. **Guests** — `household_guests`, with display_name + relationship + enrollment status. CRUD for admins/power users.

Enrollment UX for guests reuses the existing voice-recording flow (record 3–5 samples). The admin holds the phone for the guest to speak into.

### Role-based access

Uses the existing `HouseholdRole` enum and `_require_membership(..., required_role)` dependency pattern in `jarvis-auth` — same pattern already enforced on invite endpoints. Mobile gates on the `'admin' | 'power_user' | 'member'` role string already exposed via `AuthContext`.

| Action | Allowed roles |
|---|---|
| Create / edit / delete a guest | `admin`, `power_user` |
| Enroll a guest's voice | `admin`, `power_user` |
| View guest list | All members |
| Memories about a guest | Visible to all members in the household |

## API changes

`jarvis-auth`:

- `POST /households/{household_id}/guests` — admin/power_user only.
- `GET /households/{household_id}/guests` — any member.
- `PATCH /households/{household_id}/guests/{guest_id}` — admin/power_user only.
- `DELETE /households/{household_id}/guests/{guest_id}` — admin/power_user only.

`jarvis-whisper-api`:

- `POST /voice-profiles/enroll-guest`
- `DELETE /voice-profiles/guest/{guest_id}`
- `GET /voice-profiles/identify` — response shape change

`jarvis-command-center`:

- Speaker resolver returns discriminated identity.
- `mobile_voice_profiles` router proxies guest CRUD to jarvis-auth + whisper.
- Memory service polymorphic on `subject_type` / `subject_id`.
- Memory tool routing reads identity type from request context.

`jarvis-node-mobile`:

- New guest list screen + enrollment flow.
- Re-render LLM context name for guests transparently in the chat history view.

## Phased plan

1. **Schema** — `household_guests` + memories polymorphic columns + migrations.
2. **Whisper API** — guest enrollment + identification.
3. **Speaker resolver** — discriminated identity end-to-end through command-center.
4. **Memory service** — polymorphic subject + tool routing.
5. **Mobile UI** — guest CRUD + enrollment flow.
6. **LLM context** — system prompt uses `display_name` regardless of user vs guest. Speaker name flows through transparently.

## Phase 2 (separate, not in this PRD)

- Per-guest command restrictions: kids can't unlock doors, can't make purchases, can't dispatch destructive smart-home actions.
- Default restriction templates per `relationship` (child = restricted; family = unrestricted; friend = lightly restricted on smart-home).
- Quiet hours / curfew per guest.
- Per-guest "do not remember" mode for sensitive contexts.

## Design decisions

**0. Naming: `household_guest`.** Considered `household_speaker`, `voice_identity`, `non_user_profile`. Chose `household_guest` for brevity and because it reflects how users naturally describe the relationship.

**1. Separate table, not pseudo-users.** Considered creating "shadow user" rows in `users` for guests. Rejected — `users` carries auth credentials, JWT identity, household memberships, settings, and superuser flags. Voice-only guests don't belong in that table; the separation keeps invariants clean ("a row in `users` can log in").

**2. Polymorphic memory subject, not separate tables.** Memories about guests behave identically to memories about users from the LLM's POV. Splitting into two tables would force every memory-reading code path to UNION; polymorphic columns keep the code shape unchanged.

**3. Guests stay scoped to a single household.** No cross-household guests, no "follow me when I visit a different family's Jarvis." Simpler privacy model and matches real usage.

**4. Discriminated identity at the API boundary, not "speaker_id is sometimes a user and sometimes a guest."** Explicit type discrimination prevents the kind of bug where a guest's id is accidentally interpreted as a user_id and queried against the wrong table.

**5. Power users can enroll guests.** Otherwise households with one admin become a bottleneck. Members cannot enroll — voice biometrics are sensitive enough to warrant a higher bar.

**6. No raw audio retention beyond enrollment.** Whisper stores voice profile embeddings, not transcripts. The enrollment .wav files exist only long enough to compute the embedding (this is already how user enrollment works — extend the same policy).

## Open questions

- **Confidence threshold**: speaker identification with N users + M guests has a larger search space than today. Need to measure false-positive rates on dev hardware before defaulting thresholds. Conservative reads (memory writes) only on high confidence.
- **Misattribution recovery**: if a memory was written under the wrong speaker (false-positive guest match for a user), how does it get corrected? Phase 2 — for now, memories are editable per-subject via the existing memory management UI.

## Punted

- **Guest → user migration when a guest later joins as a real user.** Defer. First version starts a fresh user profile; existing guest memories and voice profile stay attached to the guest row (which can be deleted manually if no longer needed). Revisit if the friction shows up in practice.

## Cross-cutting with `node-owner.md`

- The per-household role enum (`HouseholdRole.{ADMIN, POWER_USER, MEMBER}`) and the `required_role` gating helper in `jarvis-auth` already exist; both PRDs use them rather than introducing them.
- Both PRDs add new screens under household settings in the mobile app — coordinate placement and any shared role-badge / member-picker components.
- No ordering dependency: this PRD can land independently of `node-owner.md`. The only piece `node-owner.md` actually introduces is `nodes.owner_user_id`, which this PRD does not use.
