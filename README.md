# ModernRx — GxP-Aware AI Application Modernization Advisor

[![Tests](https://img.shields.io/badge/pytest-9%20passed-brightgreen.svg)](file:///backend/tests)
[![Evaluation Recall](https://img.shields.io/badge/Planted--Finding%20Recall-100%25-brightgreen.svg)](file:///eval/results/eval_report.json)
[![Evidence Validity](https://img.shields.io/badge/Evidence%20Validity-100%25-brightgreen.svg)](file:///eval/results/eval_report.json)
[![License](https://img.shields.io/badge/License-Proprietary-blue.svg)](#)

> **Generic AI tools rewrite code. ModernRx tells a pharma company *what* to modernize, *in which order*, and *how to prove to FDA/EMA that nothing broke*.**

---

## Overview

Legacy pharma systems (LIMS, MES, QMS, eBR) are frozen for years because every architectural change triggers costly re-validation and data-integrity risks under FDA 21 CFR Part 11 and EU GMP Annex 11.

**ModernRx** is an intelligent modernization advisory platform that:
1. Builds a **Living Architecture Twin** from source code, SQL DDL, configs, git commits, and runtime traces.
2. Evaluates components across **GxP Criticality** and **Cloud Readiness**.
3. Employs a novel **Blast-Radius-Aware Decomposition algorithm** to minimize re-validation scope.
4. Convenes an **AI Architecture Council** of 5 specialized agents that debate 7R migration strategies.
5. Optimizes a migration **Roadmap & Monte Carlo Simulator** respecting GxP freeze windows.
6. Generates an **Audit-Ready Evidence Pack** (FDA CSA-aligned) with characterization tests and traceability matrix.
7. Complies with **EU Annex 22** within its own architecture (cryptographic SHA-256 audit log, pinned models, mandatory human approval gates).

---

## 7-Engine Pipeline

```
  Upload Repo / ZIP / Git
            │
            ▼
  [1] Living Architecture Twin  ── code + DB + config + traces → Knowledge Graph
            │
            ├──► [2] GxP Criticality Scanner   (Part 11 / Annex 11 / CSA risk tagging)
            ├──► [3] Cloud Readiness Scorer    (12-factor, tech debt, dependencies)
            │
            ▼
  [4] Blast-Radius-Aware Decomposition  (HDBSCAN + GxP constraint)
            │
            ▼
  [5] AI Architecture Council  (5 agents debate → 7R + target pattern)
            │
            ▼
  [6] Roadmap Optimizer + Monte Carlo  (CP-SAT solver, wave plan, P50/P80 dates)
            │
            ▼
  [7] Evidence Pack Generator  (CSA assurance plan, characterization tests, PDF)
            │
            ▼
  Interactive Dashboard + Twin Cytoscape + Annex 22 Hash-Chained Audit Trail
```

---

## Proof Metrics (PRD §23 Benchmark on AcmeLIMS)

| Metric | Louvain Baseline | Plain HDBSCAN | ModernRx (GxP-Aware) | Evaluation Result |
|---|---|---|---|---|
| **Planted-Finding Recall** | — | — | **100% (6/6)** | Target 100% achieved |
| **Assessment Time** | — | — | **~8 seconds** | Sub-minute automated analysis |
| **Modularity (Q)** | 0.6057 | 0.2399 | **0.4798** | High cohesion |
| **Inter-Cluster Call Ratio** | 0.28 | 0.22 | **0.16** | 43% lower coupling |
| **Blast Radius** | 1.0286 | 0.8571 | **0.7714** | Lower validation exposure |
| **Re-Validation Scope %** | 77.1% | 77.1% | **62.9%** | **Headline reduction** |
| **Evidence Validity** | — | — | **100%** | Zero hallucinations |

---

## Quick Start & Running Locally

### Prerequisites
- Python 3.11+
- Node.js 20 LTS
- (Optional) Docker for Neo4j (the embedded NetworkX/SQLite graph runs zero-infrastructure out of the box)
- (Optional) Google Gemini API Key in `.env` (deterministic offline mode works fully when no key is provided)

### Setup Commands

```bash
# 1. Install dependencies
cd backend && pip install -r requirements.txt && cd ..
cd frontend && npm install && cd ..

# 2. Seed demo users and AcmeLIMS project
make seed

# 3. Run backend tests & golden findings suite
make test

# 4. Run PRD §23 evaluation benchmarks
make eval

# 5. Start Backend Server
uvicorn backend.app.main:app --reload --port 8000

# 6. Start Frontend Server
cd frontend && npm run dev
```

Open **http://localhost:3000** in your browser.

---

## Repository Structure

```
├── README.md                      # Project documentation
├── Makefile                       # Developer shortcuts (seed, test, eval, up)
├── docker-compose.yml             # Optional Neo4j graph container
├── PRD.MD                         # Complete Technical Blueprint
├── backend/                       # FastAPI backend & 7 Engines
│   ├── app/
│   │   ├── api/                   # REST & WebSocket endpoints
│   │   ├── core/                  # Audit log (hash chain), LLM client, logging
│   │   ├── db/                    # SQLAlchemy models & KnowledgeGraph
│   │   └── engines/               # 7 Engines (twin, gxp, readiness, decompose, council, roadmap, evidence)
│   └── tests/                     # Pytest suite & golden findings test
├── frontend/                      # Next.js 14 App Router
│   ├── app/                       # 10 screens & layout
│   ├── components/                # TwinCytoscape, MermaidViewer, navigation
│   └── lib/                       # API clients, Zustand state store
├── demo-lims/                     # AcmeLIMS legacy Java Spring target application
├── eval/                          # PRD benchmark apps and evaluation runner
│   ├── benchmark_apps.md
│   ├── run_eval.py
│   └── results/
└── docs/                          # Architecture, prompts catalog, and pitch guide
    ├── architecture.md
    ├── prompts.md
    └── pitch/
```

---

## Self-Compliance & Regulatory Alignment
- **21 CFR Part 11 & EU GMP Annex 11:** Automated electronic record & signature detection, immutable append-only audit trail.
- **FDA CSA Guidance (Feb 2026):** Risk-scaled assurance strategy substituting heavy paper CSV for digital automated evidence.
- **EU GMP Annex 22 (AI):** Pinned model versions, cryptographic prompt/input hashing, evidence node validation, and human approval gates.
