"""Dump audit trail for Phase 2 verification."""

import json
import sys
from pathlib import Path

from recovery.audit.trail import load_audit_trail
from recovery.db import connect
from recovery.paths import DEFAULT_DB_PATH

case_id = sys.argv[1] if len(sys.argv) > 1 else "case_0019"

conn = connect(DEFAULT_DB_PATH)
events = load_audit_trail(conn, case_id)

print(f"AUDIT TRAIL for {case_id}")
print("=" * 90)
for i, e in enumerate(events, 1):
    meta = json.dumps(e.metadata) if e.metadata else ""
    action = e.action or "-"
    from_s = e.from_state or "-"
    to_s = e.to_state or "-"
    print(f"{i:2}. {e.timestamp[:19]} | {e.event_type:22} | action={action:22} | {from_s:12} -> {to_s:12}")
    print(f"    actor={e.actor} | {e.reason[:75]}")
    if meta and meta != "{}":
        print(f"    meta={meta}")

print("=" * 90)
print("Total events:", len(events))

required = {
    "DIAGNOSED",
    "ACTION_PROPOSED",
    "POLICY_CHECK",
    "STATE_TRANSITION",
    "ACTION_EXECUTED",
    "RECOVERED",
}
found = {e.event_type for e in events}
print("Required types present:", required <= found)
missing = required - found
if missing:
    print("Missing:", missing)

conn.close()
