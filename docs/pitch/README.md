# ModernRx — Pitch & Live Demo Guide (PRD §25, §26)

## 1. 5-Minute Live Demo Script

| Time | Segment | What to Show on Screen | Speaking Script / Talking Points |
|---|---|---|---|
| **0:00 - 0:20** | **The Hook** | Landing page (`/`) showing failure statistics and FDA CSA regulatory updates | *"79% of enterprise application modernization projects fail. In life sciences, it's far worse: every architectural modification in a GxP application triggers massive, costly re-validation and data-integrity risks. Organizations freeze their systems for decades because existing AI tools only rewrite code without reasoning about regulatory risk."* |
| **0:20 - 0:40** | **Upload & Twin** | Click "AcmeLIMS" project → Assessment timer finishes in <10s | *"ModernRx converts legacy pharma monoliths into a Living Architecture Twin. We parse AST, DDL tables, config, git commits, and runtime traces into a queryable knowledge graph."* |
| **0:40 - 1:20** | **Twin Exploration** | Cytoscape Twin Graph (`/twin`) + Ask the Twin drawer | *Click `ReviewService`. Show inbound calls, write tables, and runtime hits. Open 'Ask the Twin': 'Which components write batch disposition data?' Show that answers cite verified graph node IDs.* |
| **1:20 - 2:00** | **GxP Criticality & Heatmap** | GxP Heatmap (`/gxp`) | *Show red regulated core vs amber/green. Review detected compliance gaps: missing audit reason column, local file share `C:\\instrument\\`, local timestamps, hardcoded admin credentials.* |
| **2:00 - 2:50** | **Blast-Radius Decomposition** | Decomposition Screen (`/decomposition`) | *The Money Shot: Compare Louvain baseline vs Plain HDBSCAN vs ModernRx. Show the RevalScope% reduction card: 'By constraining regulated write paths together, ModernRx slashes re-validation scope significantly while maintaining superior modularity.'* |
| **2:50 - 3:40** | **Council Debate & Governance** | Multi-Agent Council (`/council`) | *Watch the 5 specialist agents debate in real-time. Show the Validation Lead pushing back on refactoring the core; show recorded dissent. Click **Approve** as QA Lead and verify immediate entry in the immutable audit log.* |
| **3:40 - 4:20** | **Roadmap & Monte Carlo** | Roadmap Screen (`/roadmap`) | *Show wave Gantt, GxP freeze windows, and 10,000 PERT Monte Carlo runs with P50/P80/P95 dates. Drag what-if squad sliders to re-simulate in seconds.* |
| **4:20 - 4:45** | **Evidence Pack Export** | Evidence Pack (`/evidence`) | *Download the audit-ready PDF/HTML package: C4 diagrams, CSA testing strategy, traceability matrix, and data migration checksums.* |
| **4:45 - 5:00** | **Closing** | Audit Chain Screen (`/audit`) | *Click 'Verify Chain ✓' to prove tamper-evident SHA-256 integrity. 'ModernRx: Modernize pharma apps faster, and prove to regulators that nothing broke.'* |

---

## 2. Pitch Deck Outline (10 Slides)

1. **Title:** ModernRx — GxP-Aware AI Application Modernization Advisor
2. **The Problem:** $1.5M average cost, 79% modernization failure rate, multi-year validation freeze.
3. **The Regulatory Catalyst:** FDA CSA Final Guidance (Sept 2025 / Feb 2026), EU GMP Annex 11 & Annex 22 (AI) revisions.
4. **The Market Gap:** Generic tools (AWS Transform, Copilots) transform syntax but are blind to GxP risk.
5. **The Solution:** 7-Engine AI Pipeline from Living Twin to Audit-Ready Evidence Pack.
6. **The Moat & Novelty:** Blast-Radius-Constrained Microservice Decomposition + Self-Compliant Annex 22 AI Architecture.
7. **The Proof (Evaluation Results):** 100% Planted Finding Recall on AcmeLIMS, measured RevalScope% reduction.
8. **Live Demo Walkthrough:** Visual summary of the 8 screens.
9. **Technical Architecture:** Zero-infrastructure local execution, NetworkX graph, FastAPI, Next.js, CP-SAT scheduler.
10. **Vision & Commercial Roadmap:** Enterprise LIMS/MES migration advisory SaaS.
