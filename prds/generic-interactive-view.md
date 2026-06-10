# PRD: Generic Interactive View — server-driven UI for inbox notifications

**Status**: Draft — approved direction, pending fresh-context build session
**Date**: 2026-06-10
**Owner**: alex
**Prereqs shipped**: shopping list export flow (jarvis-node-setup `2a8d939`, jarvis-node-mobile `b1628d9`) — the reference consumer and proof-of-concept this generalizes

## Overview

One mobile screen — `InteractiveListScreen` — that renders **any** command's interactive UI from a payload the command ships in its inbox-item metadata. Sections of rows with selection controls, action buttons that fire `@callback`s carrying the collected state, and standardized result affordances (open a URL / copy text / show a message).

**The pitch this enables**: a Pantry package author writes one Python file and gets voice + push + an interactive phone UI — no mobile code, no app store, no certification, fully private. Combined with Forge hints, the AI builder can generate packages with phone UIs from a plain-English description.

**End state (explicit goal)**: **zero command-specific views in the mobile app.** The existing `ExportShoppingListScreen` and `WalmartIdPickerScreen` migrate onto the generic surface and are deleted. The shopping list export — including the Walmart ID picker flow, the hardest case — is the reference consumer that proves the vocabulary is sufficient.

| Piece | Repo | What |
|---|---|---|
| `InteractiveListScreen` | jarvis-node-mobile | The one generic screen |
| `WebViewPickerScreen` | jarvis-node-mobile | Generic value-picker (generalized `WalmartIdPickerScreen`) |
| Routing | jarvis-node-mobile | `data.type === 'interactive_list'` → screen, before the generic inbox fallback |
| Payload builders | jarvis-command-sdk | `InteractiveList` / `Section` / `Row` / `Action` dataclasses + `__forge_hints__` |
| Producers | jarvis-node-setup + Pantry packages | Any command POSTing `/api/v0/node/inbox-item` with the payload in `metadata` |

No CC or jarvis-notifications changes — the pipeline (arbitrary `metadata`, push `data = {type: category, inbox_item_id}`, `getInboxItem` fetch, callback API) already exists and is exercised by the shopping list flow.

## Design Decisions

**1. Vocabulary, not layout engine.** The schema is a *list-with-selections* renderer: sections → rows → one control per row, actions at the bottom. There are exactly three standardized behavioral primitives beyond static rendering (decisions 5–7). Anything else — conditional expressions, nested sections, custom styling, arbitrary widgets — is rejected; a feature that can't be expressed in this vocabulary gets a custom screen (and that should be rare and deliberate). *Rejected alternative*: a declarative layout DSL (component trees, bindings). That's how you end up maintaining a bad React; the vocabulary must stay describable on one page.

**2. N actions with a layout rule.** `actions` is an array. ≤2 actions → side-by-side bottom bar; >2 → vertical stack at the bottom. Each action = `{label, callback, style?}`; every action sends the **same** collected state to its named `@callback` on the originating command. This covers confirm flows, approve/reject (the adapter-proposal flow is consumer #2), and pick-one-of-N flows. *Rejected*: per-action state filters — the callback can ignore what it doesn't need.

**3. Pantry packages from day one, made safe by content rules.** The renderer is text-only: no images, no HTML/markdown in rows, no row-level URLs except via the standardized primitives. Caps enforced at render: ≤6 sections, ≤100 rows total, label ≤120 chars, caption ≤200 chars, ≤6 actions. Callbacks dispatch only to the originating `command_name` (already enforced by the callback API's command lookup). A package can waste the user's attention but cannot phish, spoof other commands, or render arbitrary content. *Rejected*: built-ins-first trial period — gating the headline capability defeats the pitch, and the content rules bound the blast radius.

**4. Typed SDK builders with forge hints.** `jarvis_command_sdk.interactive` ships `InteractiveList`, `Section`, `Row`, `RowAction`, `Action` dataclasses with `to_dict()`/validation at construction time, plus `__forge_hints__` so the Forge AI builder learns the schema. The wire format is the documented contract; the builders are the ergonomic path. Permissive parsing on mobile (unknown keys ignored, absent keys defaulted) per the SDK's wire-format convention, so the schema can grow additively.

**5. Primitive: `requires_record_field` (live record gating).** A row may declare `requires_record_field: {command_name, field}`. Semantics are fixed: at load, the screen fetches that command's records via the existing `listRecords` API and the row is **enabled iff the record (keyed by the row's `key`) has a non-empty value for `field`**; the value is shown in the row caption as `{field_label}: {value}`. Disabled rows show the row's `disabled_caption`. This is exactly the Walmart mapping gate, generalized — and because it re-fetches live data on every load, it also solves the stale-inbox-snapshot problem as a class. *Rejected*: arbitrary `enabled_when` expressions — one fixed, named behavior instead of a condition language.

**6. Primitive: `webview_pick` row action.** A row action of type `webview_pick` opens `WebViewPickerScreen` with `{start_url, pattern, save: {command_name, field}}`. Fixed semantics: the WebView watches navigation; when the current URL matches `pattern` (regex, capture group 1 = the value), a bottom bar offers "Use this value"; on confirm it PATCHes `{[field]: value}` onto the record (`command_name` + row `key`) via the existing `updateRecord` API, returns via route-param roundtrip, and the generic screen marks the row enabled + selected and updates its caption. `start_url` supports one substitution: `{label}` (URL-encoded row label) for search seeding; an optional `view_url` template (`{value}` substitution) lets a second action open the picker directly on the stored value (the "View" affordance). This is `WalmartIdPickerScreen` with the Walmart parts as data. *Rejected*: arbitrary JS injection or postMessage protocols — URL-pattern sniffing covers the real use case and keeps the WebView dumb.

**7. Primitive: standardized result affordances.** Callback results render from `context_data`: `message` (always shown), `url` (auto-open + "Open link" re-open button), `text` (selectable monospace block + "Copy to clipboard" with copied-confirmation), `detail_lines: [string]` (checkmarked list, e.g. exported item names). Exactly the trio the export screen proved out, plus the detail list. Unknown result keys ignored.

**8. Controls v1: `none` | `checkbox` | `checkbox_stepper`.** `none` renders an info row (no selection state). `checkbox_stepper` adds the −/input/+ quantity stepper (number-pad, clamp 1–99, seeded from `default.quantity`). Collected state per selected row: `{key, selected: true, quantity?}`. *Punted*: radio/single-select sections, free-text input rows, date pickers — add when a real consumer needs them, not before (lesson: this platform's dormant-surface history).

**9. Selection semantics fixed, not configurable.** Default selection comes from each row's `default.selected` (with `requires_record_field` overriding to deselected+disabled when unmet). Select-all/clear affordance appears when any section has >3 selectable rows. Disabled rows are never selectable. Tapping a row toggles it; controls capture their own touches.

**10. Migration is the acceptance test.** Phase 3 rebuilds the shopping list export payload node-side using the SDK builders, and the feature must work identically through the generic screen — including Find ID / View / Change ID via `webview_pick`, mapping gates via `requires_record_field`, quantity steppers, notes copy-to-clipboard, and the regulars-back-on-the-list result message. Then `ExportShoppingListScreen` and `WalmartIdPickerScreen` are **deleted**. If migration requires a vocabulary addition, that addition goes through decision 1's filter first.

## Payload Schema (wire format)

Lives in inbox-item `metadata`. `category` (= push `data.type`) is `interactive_list`.

```jsonc
{
  "type": "interactive_list",
  "version": 1,                      // renderer ignores payloads with version > supported
  "title_override": "Shopping list — 7 items",   // optional; falls back to inbox item title
  "command_name": "export_shopping_list",        // callback + record-API target
  "sections": [
    {
      "title": "Regulars",           // optional; untitled section = flat list
      "rows": [
        {
          "key": "milk",             // unique within payload; the callback identifier
          "label": "milk",
          "caption": null,           // optional static caption
          "control": "checkbox_stepper",   // none | checkbox | checkbox_stepper
          "default": { "selected": true, "quantity": 2 },
          "disabled_caption": "No Walmart match",  // shown when gated off
          "requires_record_field": {  // optional — decision 5
            "command_name": "export_shopping_list",
            "field": "walmart_item_id",
            "field_label": "ID"
          },
          "row_actions": [            // optional — ≤2 per row, text buttons
            {
              "label": "Find ID",
              "type": "webview_pick",
              "start_url": "https://www.walmart.com/search?q={label}",
              "pattern": "/ip/(?:[^/]+/)?(\\d{5,})",
              "save": { "command_name": "export_shopping_list", "field": "walmart_item_id" }
            },
            {
              "label": "View",
              "type": "webview_pick",
              "start_url": "https://www.walmart.com/ip/{value}",   // {value} = current field value
              "pattern": "/ip/(?:[^/]+/)?(\\d{5,})",
              "save": { "command_name": "export_shopping_list", "field": "walmart_item_id" }
            }
          ]
        }
      ]
    }
  ],
  "actions": [
    { "label": "Export {n} items", "callback": "export_selected", "style": "primary" }
    // {n} substitutes the live selection count; style: primary | secondary | destructive
  ],
  "empty_text": "Nothing to export"
}
```

**Callback request** (existing `sendInteractiveCallback`, `navigation_type: "stack"`):

```jsonc
{
  "command_name": "export_shopping_list",
  "callback_name": "export_selected",
  "data": {
    "action": "export_selected",          // which button was tapped
    "selected": [ { "key": "milk", "quantity": 2 } ],
    "context": { "provider": "walmart" }  // payload.context echoed verbatim (opaque to mobile)
  },
  "target_node_id": "<metadata.node_id — CC-injected>"
}
```

`payload.context` is an optional opaque object the producer sets and mobile echoes — this is how the provider echo survives generalization without mobile knowing what a provider is.

**Callback result** `context_data`: `{ message, url?, text?, detail_lines?: [string] }` (decision 7).

## Mobile Implementation Notes

- **Files**: `src/screens/Inbox/InteractiveListScreen.tsx`, `src/screens/Inbox/WebViewPickerScreen.tsx` (rename/generalize), routing entries in `App.tsx` (`interactive_list` branch before the generic `inbox_item_id` fallback), `routeForCategory`, `InboxStackParamList`, `InboxStackNavigator`. Follow the adapter-screens recipe (commit `8a18403`) exactly.
- **Load sequence**: `getInboxItem(itemId)` → parse payload → collect distinct `requires_record_field.command_name`s → one `listRecords` call each → compute gating + captions → default selection. Record fetch failure degrades to snapshot-only (rows with unmet-unknown gates render disabled).
- **State**: selection `Set<string>`, quantities `Record<string, string>` (text state, parse-on-use, clamp 1–99), gate overrides `Record<string, string>` (webview_pick write-backs take precedence over fetched records — same pattern as today's `idOverrides`).
- **Callback flow**: existing `sendInteractiveCallback` + 1s polling, 30s timeout, retry-preserves-selection — lift verbatim from `ExportShoppingListScreen`.
- **Renderer hygiene**: all text via `<Text>` (never HTML/markdown), caps from decision 3 enforced with truncation + a single "content truncated" notice, unknown control/action types render as disabled text (forward compat).
- **Validation**: a malformed payload (missing `command_name`, no rows, no actions) renders the inbox item's plain body via the existing generic detail view instead — never a crash.

## Phases

**Phase 1 — SDK builders** (jarvis-command-sdk): `interactive.py` dataclasses + construction-time validation + `to_dict()` + `__forge_hints__` + tests. Wire format doc in the SDK CLAUDE.md.
**Phase 2 — Mobile renderer**: `InteractiveListScreen` + generalized `WebViewPickerScreen` + routing. Storybook-style local test payload behind a dev flag if cheap; otherwise test via Phase 3.
**Phase 3 — Reference migration**: shopping list export emits the generic payload via SDK builders; verify full parity (walmart gates + picker, notes copy, steppers, trip-boundary messages); **delete** `ExportShoppingListScreen` + `WalmartIdPickerScreen`.
**Phase 4 — Second consumer + docs**: migrate or build one more consumer (adapter approve/reject is the candidate) to prove non-shopping shapes; write the package-author doc page; add the schema to the Forge spec.

## Punts (explicit)

- Radio/single-select sections, text-input rows, date/number fields — wait for a real consumer.
- Images/icons in rows, theming, markdown — content rules say no for now.
- Multi-step wizards / navigation between generic screens.
- Live refresh/subscription (payload re-fetch on focus is enough).
- Conditional visibility beyond `requires_record_field`.
- CC-side schema validation of metadata (mobile validates; producers use SDK builders).

## Open Questions (for the build session)

1. `WebViewPickerScreen` URL allowlist: any https URL, or a per-package declared domain list in the manifest? (Lean: any https in v1 — the user is present and driving the WebView — revisit if Pantry abuse surfaces.)
2. Does `requires_record_field` need a second fetch target (records owned by a *different* command)? The schema allows it via `command_name`; confirm the data-browser API permits cross-command reads from mobile (it should — same household JWT).
3. Version negotiation: renderer ignores `version > 1` payloads and shows the plain-body fallback — confirm that's acceptable vs. a "update your app" hint row.
