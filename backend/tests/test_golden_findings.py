"""Golden findings test (PRD §22).

Asserts that AcmeLIMS surfaces all planted regulatory & architectural smells:
1. Missing audit reason column (Part 11 gap)
2. Local file share dependency (Annex 11)
3. Hardcoded admin password in config
4. Application server local timestamps (new Date())
5. Planted dead code class (LegacyExcelExporter)
6. Shared RESULT table access
"""
from __future__ import annotations

import pathlib
import pytest

from app.engines.twin.ingest import ingest
from app.engines.twin.graph_builder import build_graph
from app.engines.twin.runtime import ingest_traces
from app.engines.gxp.scanner import scan as gxp_scan
from app.engines.readiness.scorer import score as readiness_score
from app.db.graph import run_template


@pytest.fixture(scope="module")
def acmelims_graph():
    root = pathlib.Path("demo-lims")
    res = ingest(root, name="AcmeLIMS")
    kg, _ = build_graph(res, project_id="test_golden", project_name="AcmeLIMS")
    ingest_traces(kg, root)
    gxp_res = gxp_scan(kg, use_llm=False)
    readiness_res = readiness_score(kg)
    return kg, gxp_res, readiness_res


def test_missing_audit_reason_detected(acmelims_graph):
    _, gxp_res, _ = acmelims_graph
    gap_ids = [g.id for g in gxp_res.gaps]
    assert "AUDIT_NO_REASON" in gap_ids, "Should detect missing reason column in AUDIT_TRAIL table"


def test_local_file_share_dependency_detected(acmelims_graph):
    kg, gxp_res, _ = acmelims_graph
    gap_ids = [g.id for g in gxp_res.gaps]
    assert "LOCAL_FILE_DEPENDENCE" in gap_ids, "Should detect local filesystem dependency"
    paths = run_template(kg, "config_findings", {"kind": "path"})["rows"]
    assert any("instrument" in str(r.get("value", "")) for r in paths), "Should flag instrument inbox path"


def test_hardcoded_credentials_detected(acmelims_graph):
    _, gxp_res, _ = acmelims_graph
    gap_ids = [g.id for g in gxp_res.gaps]
    assert "SHARED_ADMIN_ACCOUNT" in gap_ids or "SECRETS_IN_CONFIG" in gap_ids, "Should detect hardcoded admin secrets"


def test_application_server_timestamps_detected(acmelims_graph):
    _, gxp_res, _ = acmelims_graph
    gap_ids = [g.id for g in gxp_res.gaps]
    assert "LOCAL_TIME_SOURCE" in gap_ids, "Should detect new Date() / app server local timestamps on GxP writes"


def test_dead_code_detected(acmelims_graph):
    kg, _, _ = acmelims_graph
    dead = run_template(kg, "dead_code")["rows"]
    fqns = [r.get("fqn") for r in dead]
    assert any("LegacyExcelExporter" in str(f) for f in fqns), "Should detect planted LegacyExcelExporter dead code"


def test_shared_result_table_detected(acmelims_graph):
    kg, _, _ = acmelims_graph
    shared = run_template(kg, "shared_tables", {"min_accessors": 2})["rows"]
    tables = [r.get("table") for r in shared]
    assert "RESULT" in tables, "Should detect RESULT table shared between ResultService and reporting"
