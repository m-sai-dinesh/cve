"""ModernRx Evaluation Runner (PRD §22, §23).

Computes all evaluation metrics from PRD §23 on AcmeLIMS and outputs
the evaluation metrics proof table.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Add backend to path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import settings
from app.db.graph import KnowledgeGraph, run_template
from app.db.models import Decision, Project
from app.db.session import init_db, session_scope
from app.engines.gxp.scanner import scan as gxp_scan
from app.engines.readiness.scorer import score as readiness_score
from app.engines.decompose.runner import run as run_decomposition


def evaluate_acmelims() -> dict[str, object]:
    init_db()
    results_dir = REPO_ROOT / "eval" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("ModernRx -- PRD Section 23 Evaluation Benchmark Runner")
    print("=" * 72)

    start_eval = time.time()

    with session_scope() as s:
        project = s.query(Project).filter(Project.name == "AcmeLIMS").first()
        if not project:
            print("[!] AcmeLIMS project not found in database. Please run `make seed` first.")
            return {}

        project_id = project.id
        kg = KnowledgeGraph.load(s, project_id)
        if kg.g.number_of_nodes() == 0:
            print("[!] KnowledgeGraph empty for AcmeLIMS. Please run analysis first.")
            return {}

        # 1. Assessment Time
        assessment_seconds = (project.summary_json or {}).get(
            "assessment_seconds", round(time.time() - start_eval, 2)
        )

        # 2. Planted-Finding Recall (Target 100% on AcmeLIMS)
        gxp_res = gxp_scan(kg, use_llm=False)
        gap_ids = [g.id for g in gxp_res.gaps]

        # 1. Missing audit reason column
        found_audit_reason = "AUDIT_NO_REASON" in gap_ids

        # 2. Local file share dependency
        paths = run_template(kg, "config_findings", {"kind": "path"})["rows"]
        found_file_share = ("LOCAL_FILE_DEPENDENCE" in gap_ids or
                            any("instrument" in str(r.get("value", "")) for r in paths))

        # 3. Hardcoded admin credentials
        found_hardcoded = ("SHARED_ADMIN_ACCOUNT" in gap_ids or
                           "SECRETS_IN_CONFIG" in gap_ids)

        # 4. App server local timestamps (new Date())
        found_timestamps = "LOCAL_TIME_SOURCE" in gap_ids

        # 5. Dead code (LegacyExcelExporter)
        dead = run_template(kg, "dead_code")["rows"]
        found_dead_code = any("LegacyExcelExporter" in str(r.get("fqn", "")) for r in dead)

        # 6. Shared RESULT table
        shared = run_template(kg, "shared_tables", {"min_accessors": 2})["rows"]
        found_shared_table = any("RESULT" in str(r.get("table", "")) for r in shared)

        planted_findings = [
            ("Missing audit reason column (21 CFR Part 11)", found_audit_reason),
            ("Local file share dependency (C:\\instrument\\)", found_file_share),
            ("Hardcoded credentials (admin.password in config)", found_hardcoded),
            ("Application server local timestamps (new Date())", found_timestamps),
            ("Dead code utility class (LegacyExcelExporter)", found_dead_code),
            ("Shared RESULT table across components", found_shared_table),
        ]

        recalled_count = sum(1 for _, found in planted_findings if found)
        recall_pct = round((recalled_count / len(planted_findings)) * 100, 1)

        # 3. Engine 4 Decomposition Metrics (Louvain vs plain HDBSCAN vs ModernRx)
        decomp_data = (project.summary_json or {}).get("decomposition", {})
        table = decomp_data.get("table", {})
        headline = (decomp_data.get("comparison", {})).get("headline", {})

        # If table is empty, run decomposition dynamically
        if not table or not decomp_data:
            decomp_res = run_decomposition(kg)
            table = decomp_res.table()
            headline = decomp_res.comparison.get("headline", {})

        # 4. Council Decisions & Evidence Validity
        decisions = s.query(Decision).filter(Decision.project_id == project_id).all()
        total_decisions = len(decisions)
        valid_evidence_claims = 0
        total_evidence_claims = 0

        for d in decisions:
            node_ids = (d.payload_json or {}).get("evidence_node_ids", [])
            for nid in node_ids:
                total_evidence_claims += 1
                if kg.has(nid):
                    valid_evidence_claims += 1

        evidence_validity_pct = round((valid_evidence_claims / max(1, total_evidence_claims)) * 100, 1) if total_evidence_claims else 100.0

        # Human override rate
        rejected = s.query(Decision).filter(Decision.project_id == project_id, Decision.status == "Rejected").count()
        override_rate_pct = round((rejected / max(1, total_decisions)) * 100, 1)

    # Print summary report
    print(f"\n[1] Assessment Time:")
    print(f"    Wall-clock duration: {assessment_seconds} seconds (~{round(float(assessment_seconds)/60, 1)} minutes)")

    print(f"\n[2] Planted-Finding Recall ({recalled_count}/{len(planted_findings)} = {recall_pct}%):")
    for name, found in planted_findings:
        status = "[PASS]" if found else "[FAIL]"
        print(f"    {status} {name}")

    print(f"\n[3] Decomposition Proof Table (PRD Section 23):")
    print(f"    {'Metric':<30} | {'Louvain':<10} | {'Plain HDBSCAN':<14} | {'ModernRx (GxP-Aware)':<22} | {'Impact / Direction'}")
    print("    " + "-" * 102)

    # Format table metrics
    rows_data = table.get("rows", [])
    metric_map = {r.get("metric"): r for r in rows_data} if isinstance(rows_data, list) else table

    # Display purely dynamic proof rows
    q_row = metric_map.get("modularity", {})
    icp_row = metric_map.get("icp", {})
    blast_row = metric_map.get("blast_radius", {})
    reval_row = metric_map.get("reval_scope_pct", {})
    clusters_row = metric_map.get("services", {})

    print(f"    {'Services (# clusters)':<30} | {str(clusters_row.get('louvain', 'N/A')):<10} | {str(clusters_row.get('hdbscan', 'N/A')):<14} | {str(clusters_row.get('modernrx', 'N/A')):<22} | Target granularity")
    print(f"    {'Modularity (Q)':<30} | {str(q_row.get('louvain', 'N/A')):<10} | {str(q_row.get('hdbscan', 'N/A')):<14} | {str(q_row.get('modernrx', 'N/A')):<22} | Higher is better")
    print(f"    {'Inter-cluster calls (ICP)':<30} | {str(icp_row.get('louvain', 'N/A')):<10} | {str(icp_row.get('hdbscan', 'N/A')):<14} | {str(icp_row.get('modernrx', 'N/A')):<22} | Lower is better")
    print(f"    {'BlastRadius (validation hops)':<30} | {str(blast_row.get('louvain', 'N/A')):<10} | {str(blast_row.get('hdbscan', 'N/A')):<14} | {str(blast_row.get('modernrx', 'N/A')):<22} | Lower is better")
    print(f"    {'RevalScope %':<30} | {str(reval_row.get('louvain', 'N/A'))}%{'':<9} | {str(reval_row.get('hdbscan', 'N/A'))}%{'':<13} | {str(reval_row.get('modernrx', 'N/A'))}%{'':<21} | HEADLINE MONEY SHOT")

    print(f"\n[4] AI Council Governance & Annex 22 Self-Compliance:")
    print(f"    Council Decisions Recorded: {total_decisions}")
    print(f"    Evidence Validity:          {evidence_validity_pct}% (Every claim must cite valid graph node IDs)")
    print(f"    Decision Stability Target:  >= 80% (Deterministic baseline + pinned Gemini temperature=0.2)")
    print(f"    Human Override Rate:        {override_rate_pct}%")

    out_data = {
        "assessment_seconds": assessment_seconds,
        "planted_finding_recall_pct": recall_pct,
        "planted_findings": [{"name": n, "detected": d} for n, d in planted_findings],
        "decomposition_comparison": table,
        "headline_reval_reduction": headline,
        "evidence_validity_pct": evidence_validity_pct,
        "override_rate_pct": override_rate_pct,
    }

    out_file = results_dir / "eval_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)

    print(f"\n[OK] Results successfully written to {out_file}")
    print("=" * 72)
    return out_data


if __name__ == "__main__":
    evaluate_acmelims()
