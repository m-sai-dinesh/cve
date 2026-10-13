"""Audit log hash-chaining verification test (PRD §15, §22)."""
from __future__ import annotations

import pytest
from app.core.audit import record, verify_chain
from app.db.session import init_db


def test_audit_hash_chain_valid():
    init_db()
    record("test.action_1", payload={"foo": "bar"})
    record("test.action_2", payload={"num": 42})
    record("test.action_3", payload={"user": "QA Approver"})

    res = verify_chain()
    assert res["valid"] is True, f"Audit hash chain must be mathematically valid: {res.get('detail')}"
    assert res["rows"] >= 3
    assert res["head"] is not None
