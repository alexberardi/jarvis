#!/usr/bin/env python3
"""Seed a complete, reproducible dev environment: logins, household, nodes, data.

Rebuilds a dev stack that looks lived-in — real users you can log into the web
and mobile apps with, a household with rooms and devices, a registered node that
actually authenticates, plus voice history, memories, routines and a phonebook.

Written after the 2026-08-31 loss of the local dev volumes. The point is that
losing them should cost minutes, not a working environment, so this is
re-runnable and deterministic rather than a one-off.

Two layers, deliberately different:

  * IDENTITY + NODES go through the REAL APIs (/auth/setup, /auth/register,
    /households, /api/v0/admin/nodes). Passwords get properly hashed, node keys
    are minted by command-center and registered with jarvis-auth. A seeded login
    is a real login; a seeded node genuinely authenticates.
  * CONTENT is written straight to the database. Going through APIs for a
    hundred transcript rows would be slow and buys nothing — there are no
    invariants to honour that a plain INSERT breaks.

Personas are PSEUDONYMOUS on purpose. Dev data flows into prompts, and
tools/call_sim.py ships transcripts to OpenAI, so real household names would
leave the building the first time someone runs the harness. The shape mirrors a
real household (two adults, a child, two dogs on medication, kitchen + living
room nodes); the names do not.

PREREQUISITES on a machine whose Docker state was wiped. None of these are
obvious from a cold start, and the seeder cannot do its job without them:

  1. docker network create jarvis-net           (external network, not recreated)
  2. cd jarvis-data-services && docker compose up -d   (postgres/redis/minio)
  3. ./scripts/reset_all_databases.sh --confirm  (creates the 10 DBs + migrates)
  4. Register app clients in auth, or every node call fails
     "401 Invalid app credentials" — auth's app_clients table is empty after a
     DB reset. `./jarvis start --all` does this via _auto_register, but it
     cannot finish on macOS (jarvis-whisper-api needs an NVIDIA driver and the
     run dies before the registration step). Register manually:
        POST /admin/app-clients  {"app_id": "...", "name": "..."}
        header: X-Jarvis-Admin-Token: $JARVIS_AUTH_ADMIN_TOKEN
     then write the returned key into that service's .env as JARVIS_APP_KEY
     and restart it.
  5. ./jarvis start jarvis-config-service jarvis-auth jarvis-command-center

Usage (needs sqlalchemy + psycopg2 — command-center's venv has both):

    jarvis-command-center/.venv/bin/python scripts/seed_dev.py --profile rich
    ... --reset            # wipe seeded rows first
    ... --profile minimal  # identity + topology only, no content
    ... --node-id <uuid>   # match an existing node instead of the fixed dev one
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from sqlalchemy import create_engine, text
except ImportError:  # pragma: no cover - dependency guidance
    sys.exit(
        "sqlalchemy/psycopg2 required. Run with command-center's venv:\n"
        "  jarvis-command-center/.venv/bin/python scripts/seed_dev.py"
    )

# ── Fixed identifiers ─────────────────────────────────────────────────────────
# Deterministic so reruns are idempotent and so the node config below stays
# valid across rebuilds — the whole point is that you paste it once.
HOUSEHOLD_ID = "5eed0000-0000-4000-8000-00000000d0e5"
DEV_NODE_ID = "5eed0000-0000-4000-8000-00000000a0de"
LIVING_NODE_ID = "5eed0000-0000-4000-8000-00000000117e"

DEFAULT_PASSWORD = "DevPass123!"
PRIMARY_EMAIL = "test@jarvisautomation.io"

PEOPLE = [
    # (email, username, display, role, is_primary)
    (PRIMARY_EMAIL, "jordan", "Jordan", "admin", True),
    ("casey@jarvisautomation.io", "casey", "Casey", "admin", False),
    ("sam@jarvisautomation.io", "sam", "Sam", "member", False),
]

ROOMS = [
    ("Kitchen", "kitchen", "chef-hat"),
    ("Living Room", "living_room", "sofa"),
    ("Bedroom", "bedroom", "bed"),
    ("Office", "office", "desk"),
]


def log(msg: str, indent: int = 0) -> None:
    print(f"{'  ' * indent}{msg}", flush=True)


# ── HTTP helpers (stdlib only, so the script has no HTTP dependency) ──────────
def _request(method, url, body=None, headers=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode() or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode() or "{}"
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"detail": raw[:200]}
    except Exception as e:  # noqa: BLE001 - connection refused etc.
        return 0, {"detail": str(e)}


def wait_for(url: str, name: str, timeout_s: int = 90) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status, _ = _request("GET", url, timeout=5)
        if status == 200:
            log(f"✅ {name} healthy", 1)
            return
        time.sleep(2)
    sys.exit(f"❌ {name} not healthy at {url} after {timeout_s}s — is the stack up?")


# ── Layer 1: identity (real APIs, real password hashes) ───────────────────────
def seed_identity(auth_url: str, password: str) -> dict:
    """Create the superuser, the household, and the other members.

    Idempotent: an already-set-up auth service answers 409 to /auth/setup and
    400 to a duplicate /auth/register, and both fall through to a plain login.
    """
    log("── identity ──")
    tokens: dict[str, str] = {}
    email, _, display, _, _ = PEOPLE[0]

    status, body = _request("POST", f"{auth_url}/auth/setup", {
        "email": email, "username": PEOPLE[0][1], "password": password,
    })
    if status in (200, 201):
        log(f"created superuser {email}", 1)
    elif status == 409:
        log("superuser already exists — reusing", 1)
    else:
        sys.exit(f"❌ /auth/setup failed: {status} {body}")

    status, body = _request("POST", f"{auth_url}/auth/login",
                            {"email": email, "password": password})
    if status != 200:
        sys.exit(
            f"❌ cannot log in as {email}: {status} {body}\n"
            "   If auth was set up previously with a different password, "
            "run with --reset or drop the auth DB."
        )
    tokens[email] = body["access_token"]
    log(f"logged in as {display}", 1)

    auth_hdr = {"Authorization": f"Bearer {tokens[email]}"}

    # Household. The API mints its own id, so a rerun must REUSE the existing
    # one rather than creating a second household and orphaning all the content
    # seeded against the first.
    household_id = None
    status, body = _request("GET", f"{auth_url}/households", headers=auth_hdr)
    if status == 200 and isinstance(body, list) and body:
        household_id = body[0].get("id") or body[0].get("household_id")
        log(f"reusing household {household_id}", 1)

    if not household_id:
        status, body = _request("POST", f"{auth_url}/households",
                                {"name": "Avery Household"}, auth_hdr)
        if status in (200, 201):
            household_id = body.get("id") or body.get("household_id")
            log(f"created household {household_id}", 1)
        else:
            sys.exit(f"❌ could not create household: {status} {body}")

    # Invite + register the rest. register() accepts invite_code, so each member
    # is created and joined in one call.
    for email_i, username, display_i, role, _ in PEOPLE[1:]:
        code = None
        status, body = _request(
            "POST", f"{auth_url}/households/{household_id}/invites",
            {"role": role}, auth_hdr,
        )
        if status in (200, 201):
            code = body.get("code") or body.get("invite_code")

        payload = {"email": email_i, "username": username, "password": password}
        if code:
            payload["invite_code"] = code
        status, body = _request("POST", f"{auth_url}/auth/register", payload)
        if status in (200, 201):
            log(f"created {display_i} ({email_i})", 1)
        elif status == 400:
            log(f"{display_i} already exists — reusing", 1)
        elif status == 429:
            log(f"⚠️  rate limited creating {display_i}; retrying once", 1)
            time.sleep(5)
            _request("POST", f"{auth_url}/auth/register", payload)
        else:
            log(f"⚠️  could not create {display_i}: {status} {body}", 1)

    return {"household_id": household_id, "tokens": tokens}


# ── Layer 2: topology (nodes via command-center's admin API) ──────────────────
def seed_nodes(cc_url: str, admin_key: str, household_id: str, node_id: str,
               cc_db: str) -> dict:
    log("── nodes ──")
    keys: dict[str, str] = {}
    # command-center's admin API authenticates with X-API-Key (see
    # jarvis-node-setup/utils/authorize_node.py::_make_cc_request).
    hdr = {"X-API-Key": admin_key}

    for nid, room, name in (
        (node_id, "kitchen", "dev-kitchen"),
        (LIVING_NODE_ID, "living_room", "dev-living-room"),
    ):
        status, body = _request("POST", f"{cc_url}/api/v0/admin/nodes", {
            "node_id": nid, "household_id": household_id,
            "room": room, "user": "default", "voice_mode": "brief", "name": name,
        }, hdr)
        if status in (200, 201):
            keys[nid] = body.get("node_key") or body.get("api_key") or ""
            log(f"registered {name} ({room})", 1)
        else:
            # Already registered from a previous run. Do NOT re-create it: the
            # printed config snippet is meant to be pasted onto the Pi once, and
            # a new key would silently invalidate it. command-center stores the
            # key, so recover it and carry on — that keeps the snippet stable
            # AND lets verification actually exercise node auth.
            existing = _node_key_from_db(cc_db, nid)
            if existing:
                keys[nid] = existing
                log(f"reusing existing {name} ({room})", 1)
            else:
                log(f"⚠️  node {name}: {status} {body.get('detail', body)}", 1)
    return keys


def _node_key_from_db(cc_db: str, node_id: str) -> str:
    """Read a registered node's key back out of command-center."""
    try:
        engine = create_engine(cc_db, future=True)
        with engine.begin() as cx:
            row = cx.execute(
                text("SELECT api_key FROM nodes WHERE node_id = :n"), {"n": node_id}
            ).fetchone()
        return row[0] if row else ""
    except Exception:  # noqa: BLE001 - best effort; caller degrades to a warning
        return ""


# ── Layer 3: content (direct DB — no invariants that an INSERT breaks) ────────
def seed_content(db_url: str, household_id: str, node_id: str,
                 user_ids: dict[str, int], rng: random.Random, rich: bool) -> dict:
    log("── content ──")
    engine = create_engine(db_url, future=True)
    counts: dict[str, int] = {}
    # CC's DateTime columns are naive, so store naive UTC (not tz-aware).
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    primary = user_ids.get(PRIMARY_EMAIL, 1)
    partner = user_ids.get("casey@jarvisautomation.io", primary)

    with engine.begin() as cx:
        # Rooms ------------------------------------------------------------
        room_ids: dict[str, str] = {}
        for i, (name, norm, icon) in enumerate(ROOMS):
            rid = f"5eed0000-0000-4000-8000-{i:012d}"
            room_ids[norm] = rid
            cx.execute(text("""
                INSERT INTO rooms (id, household_id, name, normalized_name, icon,
                                   created_at, updated_at)
                VALUES (:id, :hh, :name, :norm, :icon, :now, :now)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """), {"id": rid, "hh": household_id, "name": name,
                   "norm": norm, "icon": icon, "now": now})
        counts["rooms"] = len(ROOMS)

        # Devices ----------------------------------------------------------
        devices = [
            ("light.kitchen_ceiling", "Kitchen Ceiling", "light", "kitchen", "lifx"),
            ("light.kitchen_under_cabinet", "Under Cabinet", "light", "kitchen", "lifx"),
            ("kettle.smart_kettle", "Smart Kettle", "kettle", "kitchen", "govee"),
            ("light.living_room_lamp", "Living Room Lamp", "light", "living_room", "lifx"),
            ("climate.thermostat", "Thermostat", "climate", "living_room", "nest"),
            ("camera.front_door", "Front Door", "camera", "living_room", "nest"),
            ("lock.front_door", "Front Door Lock", "lock", "living_room", "schlage"),
            ("light.bedroom_lamp", "Bedroom Lamp", "light", "bedroom", "lifx"),
            ("switch.office_fan", "Office Fan", "switch", "office", "kasa"),
        ]
        for i, (eid, name, domain, room, proto) in enumerate(devices):
            cx.execute(text("""
                INSERT INTO devices (id, household_id, room_id, entity_id, name, domain,
                                     protocol, source, is_controllable, is_active,
                                     created_at, updated_at)
                VALUES (:id, :hh, :room, :eid, :name, :domain, :proto, 'seed',
                        true, true, :now, :now)
                ON CONFLICT (id) DO NOTHING
            """), {"id": f"5eed0001-0000-4000-8000-{i:012d}", "hh": household_id,
                   "room": room_ids.get(room), "eid": eid, "name": name,
                   "domain": domain, "proto": proto, "now": now})
        counts["devices"] = len(devices)

        # Phonebook --------------------------------------------------------
        # Numbers are 555-01xx — the reserved fictional range, so a stray
        # auto-dial in dev cannot reach a real business.
        contacts = [
            ("Cedar Street Pharmacy", "+15550100", "pharmacy", "24 Cedar St"),
            ("Dr. Nkemelu Family Practice", "+15550101", "doctor", "8 Field Rd"),
            ("Brightpaw Veterinary", "+15550102", "vet", "150 Mill Ave"),
            ("Nonna's Pizza", "+15550103", "restaurant", "31 Market St"),
            ("Riverside Dental", "+15550104", "dentist", "9 Riverside Dr"),
            ("Meadow Lane School", "+15550105", "school", "2 Meadow Ln"),
            ("Ace Plumbing", "+15550106", "trade", None),
            ("Kwik Auto Service", "+15550107", "trade", "77 Depot St"),
        ]
        for i, (name, number, kind, addr) in enumerate(contacts):
            cx.execute(text("""
                INSERT INTO phone_contacts (id, household_id, name, normalized_name,
                                            number, address, source, notes,
                                            do_not_call, created_at, updated_at)
                VALUES (:id, :hh, :name, :norm, :num, :addr, 'manual', :notes,
                        false, :now, :now)
                ON CONFLICT (id) DO NOTHING
            """), {"id": f"5eed0002-0000-4000-8000-{i:012d}", "hh": household_id,
                   "name": name, "norm": name.lower(), "num": number,
                   "addr": addr, "notes": kind, "now": now})
        counts["phone_contacts"] = len(contacts)

        # Routines ---------------------------------------------------------
        routines = [
            ("good-morning", "Good Morning", ["good morning", "start the day"],
             [{"command": "get_weather", "args": {}},
              {"command": "get_calendar_events", "args": {"resolved_datetimes": ["today"]}}],
             "Give a warm short briefing."),
            ("good-night", "Good Night", ["good night", "bedtime"],
             [{"command": "control_device", "args": {"entity_id": "light.kitchen_ceiling",
                                                     "action": "turn_off"}}],
             "Confirm briefly and wish them a good night."),
            ("leaving-home", "Leaving Home", ["i'm heading out", "leaving now"],
             [{"command": "control_device", "args": {"entity_id": "lock.front_door",
                                                     "action": "lock"}}],
             "Confirm what was secured in one line."),
        ]
        for i, (slug, name, phrases, steps, instr) in enumerate(routines):
            cx.execute(text("""
                INSERT INTO routines (id, household_id, slug, name, trigger_phrases,
                                      steps, response_instruction, response_length,
                                      enabled, created_at, updated_at)
                VALUES (:id, :hh, :slug, :name, :ph, :st, :instr, 'short',
                        true, :now, :now)
                ON CONFLICT (id) DO NOTHING
            """), {"id": f"5eed0003-0000-4000-8000-{i:012d}", "hh": household_id,
                   "slug": slug, "name": name, "ph": json.dumps(phrases),
                   "st": json.dumps(steps), "instr": instr, "now": now})
        counts["routines"] = len(routines)

        if not rich:
            log("minimal profile — skipping memories/transcripts/signals", 1)
            for k, v in counts.items():
                log(f"{k}: {v}", 2)
            return counts

        # User memories ----------------------------------------------------
        # embedding stays NULL: semantic recall re-embeds on demand, and
        # generating vectors here would drag the embedding model into a seeder.
        memories = [
            (primary, "pets", "Has two golden retrievers, Biscuit and Pepper"),
            (primary, "pets", "Biscuit takes anti-seizure medication twice a day"),
            (primary, "family", "Partner is Casey; they have a toddler named Rowan"),
            (primary, "preferences", "Prefers coffee black, no sugar"),
            (primary, "preferences", "Does not want jokes about work stress"),
            (primary, "home", "Lives in Brookfield"),
            (primary, "food", "Enjoys pizza on Friday nights"),
            (primary, "schedule", "Cuts the grass on Sunday evenings"),
            (partner, "pets", "Biscuit is the older of the two dogs"),
            (partner, "preferences", "Prefers tea in the morning"),
            (partner, "family", "Rowan naps around 1pm"),
            (partner, "schedule", "Works from home on Tuesdays and Thursdays"),
        ]
        for uid, cat, content in memories:
            cx.execute(text("""
                INSERT INTO user_memories (user_id, household_id, category, content,
                                           source, is_active, is_pinned,
                                           created_at, updated_at)
                VALUES (:uid, :hh, :cat, :content, 'seed', true, false, :now, :now)
            """), {"uid": uid, "hh": household_id, "cat": cat,
                   "content": content, "now": now - timedelta(days=rng.randint(1, 60))})
        counts["user_memories"] = len(memories)

        # Conversation transcripts -----------------------------------------
        exchanges = [
            ("What's the weather today?", "It's 68 and sunny — nice day for it."),
            ("Turn on the kitchen lights", None),
            ("Biscuit took his medicine", None),
            ("What's on my calendar tomorrow?", "You've got a dentist appointment at 9."),
            ("Set a timer for 10 minutes", None),
            ("Who is Rowan?", "Rowan is your toddler."),
            ("Play something upbeat", None),
            ("Lock the front door", None),
            ("Is the front door locked?", "Yes, it's locked."),
            ("Add milk to the shopping list", None),
            ("How long does it take to get to the vet?", "About 12 minutes right now."),
            ("Good morning", "Morning! It's 64 out and you're clear until noon."),
            ("What did I ask you to remind me about?", "To call the pharmacy back."),
            ("Turn the thermostat down two degrees", None),
            ("Thanks", "Anytime."),
        ]
        n_tx = 0
        for day in range(14):
            for user_msg, assistant in rng.sample(exchanges, rng.randint(2, 5)):
                uid = rng.choice([primary, partner])
                created = now - timedelta(days=day, hours=rng.randint(0, 14))
                cx.execute(text("""
                    INSERT INTO conversation_transcripts
                        (user_id, household_id, conversation_id, user_message,
                         assistant_message, is_processed, created_at)
                    VALUES (:uid, :hh, :cid, :um, :am, true, :created)
                """), {"uid": uid, "hh": household_id,
                       "cid": f"seed-{day}-{n_tx}", "um": user_msg,
                       "am": assistant, "created": created})
                n_tx += 1
        counts["conversation_transcripts"] = n_tx

        # Signals ----------------------------------------------------------
        signals = [
            ("presence.seen", "jordan", "Jordan was heard in the kitchen"),
            ("presence.seen", "casey", "Casey was heard in the living room"),
            ("appt.upcoming", "dentist", "Dentist appointment tomorrow at 9:00 AM"),
        ]
        for i, (kind, subject, summary) in enumerate(signals):
            cx.execute(text("""
                INSERT INTO signals (household_id, user_id, node_id, room, kind, subject,
                                     source_key, summary, source_agent, cacheable,
                                     is_active, observed_at, created_at, updated_at)
                VALUES (:hh, :uid, :node, 'kitchen', :kind, :subj, :sk, :sum,
                        'seed', false, true, :now, :now, :now)
                ON CONFLICT DO NOTHING
            """), {"hh": household_id, "uid": primary, "node": node_id,
                   "kind": kind, "subj": subject, "sk": f"seed:{kind}:{i}",
                   "sum": summary, "now": now})
        counts["signals"] = len(signals)

    for k, v in counts.items():
        log(f"{k}: {v}", 2)
    return counts


def reset_content(db_url: str, household_id: str) -> None:
    """Remove previously seeded rows so a rerun starts clean.

    Matched by SEED MARKER only — `source='seed'`, `conversation_id LIKE
    'seed-%'`, `id LIKE '5eed...'` — deliberately NOT scoped by household.

    Scoping to the current household looked safer and was actually a hole: if
    an earlier run seeded a different household (which happened once, before
    household reuse was fixed), those rows became invisible to reset and
    silently doubled every count. The markers are specific enough that nothing
    unseeded can match them, so they are the better filter on their own.
    """
    log("── reset ──")
    engine = create_engine(db_url, future=True)
    with engine.begin() as cx:
        for tbl, where in (
            ("signals", "source_agent = 'seed'"),
            ("conversation_transcripts", "conversation_id LIKE 'seed-%'"),
            ("user_memories", "source = 'seed'"),
            ("routines", "id LIKE '5eed0003-%'"),
            ("phone_contacts", "id LIKE '5eed0002-%'"),
            ("devices", "id LIKE '5eed0001-%'"),
            ("rooms", "id LIKE '5eed0000-%'"),
        ):
            res = cx.execute(text(f"DELETE FROM {tbl} WHERE {where}"))
            log(f"{tbl}: -{res.rowcount}", 1)


def resolve_user_ids(auth_db_url: str) -> dict[str, int]:
    engine = create_engine(auth_db_url, future=True)
    with engine.begin() as cx:
        rows = cx.execute(text("SELECT email, id FROM users")).fetchall()
    return {r[0]: r[1] for r in rows}


def verify(auth_url: str, cc_url: str, password: str,
           node_id: str, node_key: str) -> bool:
    """A green run must mean it actually works, not that inserts succeeded."""
    log("── verify ──")
    ok = True
    for email, _, display, _, _ in PEOPLE:
        status, _ = _request("POST", f"{auth_url}/auth/login",
                             {"email": email, "password": password})
        log(f"{'✅' if status == 200 else '❌'} login {display} ({email})", 1)
        ok &= status == 200

    if node_key:
        # /api/v0/node/devices is node-authenticated (200 with a valid key,
        # 400 without). /api/v0/health does not exist and /health is open, so
        # neither would actually prove the key works.
        status, _ = _request("GET", f"{cc_url}/api/v0/node/devices",
                             headers={"X-API-Key": f"{node_id}:{node_key}"})
        log(f"{'✅' if status == 200 else '❌'} node authenticates to command-center", 1)
        ok &= status == 200
    else:
        # A missing key means node registration failed upstream. Reporting the
        # run green here is how a half-seeded environment gets mistaken for a
        # working one, so this is a failure.
        log("❌ no node key — node registration failed", 1)
        ok = False
    return ok


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--auth-url", default=os.getenv("AUTH_URL", "http://localhost:7701"))
    p.add_argument("--cc-url", default=os.getenv("CC_URL", "http://localhost:7703"))
    p.add_argument("--cc-db", default=os.getenv(
        "CC_DB_URL", "postgresql://jarvis:jarvis@localhost:5432/jarvis_command_center"))
    p.add_argument("--auth-db", default=os.getenv(
        "AUTH_DB_URL", "postgresql://jarvis:jarvis@localhost:5432/jarvis_auth"))
    p.add_argument("--admin-key", default=os.getenv("ADMIN_API_KEY", ""))
    p.add_argument("--password", default=os.getenv("SEED_PASSWORD", DEFAULT_PASSWORD))
    p.add_argument("--node-id", default=DEV_NODE_ID,
                   help="use an existing node's id instead of the fixed dev one")
    p.add_argument("--profile", choices=("minimal", "rich"), default="rich")
    p.add_argument("--reset", action="store_true", help="delete seeded rows first")
    p.add_argument("--seed", type=int, default=1337, help="RNG seed (determinism)")
    args = p.parse_args()

    if not args.admin_key:
        return _fail("--admin-key (or ADMIN_API_KEY) is required to register nodes.\n"
                     "  grep ADMIN_API_KEY jarvis-command-center/.env")

    rng = random.Random(args.seed)
    log("Seeding dev environment")
    log(f"auth={args.auth_url}  cc={args.cc_url}  profile={args.profile}")
    log("")

    log("── services ──")
    wait_for(f"{args.auth_url}/health", "jarvis-auth")
    wait_for(f"{args.cc_url}/health", "command-center")

    ident = seed_identity(args.auth_url, args.password)
    household_id = ident["household_id"]

    if args.reset:
        reset_content(args.cc_db, household_id)

    node_keys = seed_nodes(args.cc_url, args.admin_key, household_id,
                           args.node_id, args.cc_db)
    user_ids = resolve_user_ids(args.auth_db)
    seed_content(args.cc_db, household_id, args.node_id, user_ids, rng,
                 rich=args.profile == "rich")

    node_key = node_keys.get(args.node_id, "")
    ok = verify(args.auth_url, args.cc_url, args.password, args.node_id, node_key)

    log("")
    log("=" * 66)
    log(f"household : {household_id}")
    log(f"password  : {args.password}   (all users)")
    for email, _, display, role, _ in PEOPLE:
        log(f"  {display:8} {email:34} {role}")
    if node_key:
        log("")
        log("node config.json snippet — paste onto the dev Pi:")
        log(json.dumps({
            "node_id": args.node_id,
            "api_key": node_key,
            "command_center_url": args.cc_url,
        }, indent=2))
    log("=" * 66)
    log("✅ dev environment ready" if ok else "⚠️  seeded, but verification FAILED")
    return 0 if ok else 1


def _fail(msg: str) -> int:
    print(f"❌ {msg}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
