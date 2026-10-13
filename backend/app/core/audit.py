"""Append-only, tamper-evident audit log (PRD §15).

Each row stores ``prev_hash`` and ``hash = SHA256(prev_hash + canonical_payload)``.
Any edit or deletion anywhere in the chain is detectable by ``verify_chain``.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import AuditLog
from ..db.session import session_scope

GENESIS = "0" * 64

# Appends must be serialised: two concurrent writers reading the same tip would
# fork the chain and make verification fail.
_chain_lock = threading.Lock()


def canonical(payload: Any) -> str:
    """Stable JSON so the same logical payload always hashes identically."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def row_digest(prev_hash: str, row: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical(row)).encode("utf-8")).hexdigest()


def _record_body(entry: AuditLog) -> dict[str, Any]:
    """The fields covered by the hash. ``ts`` is normalised to ISO-8601 UTC."""
    ts_val = None
    if entry.ts:
        if isinstance(entry.ts, dt.datetime):
            ts_obj = entry.ts if entry.ts.tzinfo is not None else entry.ts.replace(tzinfo=dt.timezone.utc)
            ts_val = ts_obj.isoformat()
        else:
            ts_str = str(entry.ts).replace(" ", "T")
            if not ts_str.endswith("+00:00") and not ts_str.endswith("Z"):
                ts_str += "+00:00"
            ts_val = ts_str
    return {
        "ts": ts_val,
        "actor": entry.actor,
        "action": entry.action,
        "entity": entry.entity,
        "entity_id": entry.entity_id,
        "payload": entry.payload_json or {},
    }


def record(
    action: str,
    *,
    actor: str = "system",
    entity: str = "",
    entity_id: str = "",
    payload: dict[str, Any] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Append one row to the chain. Safe to call from background jobs."""

    def _append(s: Session) -> dict[str, Any]:
        tip = s.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
        prev_hash = tip.hash if tip else GENESIS
        entry = AuditLog(
            actor=actor,
            action=action,
            entity=entity,
            entity_id=str(entity_id),
            payload_json=payload or {},
            prev_hash=prev_hash,
        )
        s.add(entry)
        s.flush()  # populates the server-side default for ts
        entry.hash = row_digest(prev_hash, _record_body(entry))
        s.flush()
        return {
            "id": entry.id,
            "ts": entry.ts.isoformat(),
            "actor": entry.actor,
            "action": entry.action,
            "entity": entry.entity,
            "entity_id": entry.entity_id,
            "payload": entry.payload_json,
            "prev_hash": entry.prev_hash,
            "hash": entry.hash,
        }

    with _chain_lock:
        if db is not None:
            out = _append(db)
            db.commit()
            return out
        with session_scope() as s:
            return _append(s)


def verify_chain(db: Session | None = None) -> dict[str, Any]:
    """Recompute every digest. Returns the first break, if any."""
    if db is None:
        with session_scope() as s:
            return verify_chain(s)

    rows = db.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all()
    prev = GENESIS
    for r in rows:
        if r.prev_hash != prev:
            return {
                "valid": False,
                "rows": len(rows),
                "broken_at": r.id,
                "detail": f"row {r.id} points at {r.prev_hash[:12]}… but the previous row hashes to {prev[:12]}…",
            }
        expected = row_digest(prev, _record_body(r))
        if expected != r.hash:
            return {
                "valid": False,
                "rows": len(rows),
                "broken_at": r.id,
                "detail": f"row {r.id} content does not match its digest — the row was altered after it was written",
            }
        prev = r.hash
    return {
        "valid": True,
        "rows": len(rows),
        "broken_at": None,
        "head": prev,
        "detail": f"All {len(rows)} rows verified; chain head {prev[:16]}…",
    }
