# ModernRx — GxP‑Aware AI Application Modernization Advisor
### Complete Technical Blueprint (Hackathon Edition)

> **One‑liner:** Generic AI tools rewrite code. ModernRx tells a pharma company *what* to modernize, *in which order*, and *how to prove to FDA/EMA that nothing broke*.

---

## Table of Contents
1. [Problem Statement](#1-problem-statement)
2. [Why Now — Evidence Base](#2-why-now--evidence-base)
3. [Solution Overview](#3-solution-overview)
4. [Mapping to Hackathon Objectives & Outcomes](#4-mapping-to-hackathon-objectives--outcomes)
5. [System Architecture](#5-system-architecture)
6. [Technology Stack (every package, and why)](#6-technology-stack-every-package-and-why)
7. [Repository / Folder Structure](#7-repository--folder-structure)
8. [Engine 1 — Living Architecture Twin](#8-engine-1--living-architecture-twin)
9. [Engine 2 — GxP Criticality Scanner](#9-engine-2--gxp-criticality-scanner)
10. [Engine 3 — Cloud Readiness Scorer](#10-engine-3--cloud-readiness-scorer)
11. [Engine 4 — Blast‑Radius‑Aware Decomposition](#11-engine-4--blast-radius-aware-decomposition)
12. [Engine 5 — AI Architecture Council (Multi‑Agent)](#12-engine-5--ai-architecture-council-multi-agent)
13. [Engine 6 — Roadmap Optimizer & Monte Carlo Simulator](#13-engine-6--roadmap-optimizer--monte-carlo-simulator)
14. [Engine 7 — Evidence Pack Generator](#14-engine-7--evidence-pack-generator)
15. [Self‑Compliance Layer (Annex 22 for the tool itself)](#15-self-compliance-layer-annex-22-for-the-tool-itself)
16. [Data Models & Graph Schema](#16-data-models--graph-schema)
17. [REST / WebSocket API Specification](#17-rest--websocket-api-specification)
18. [Frontend — Screens & Components](#18-frontend--screens--components)
19. [Demo Target Application (Mock LIMS)](#19-demo-target-application-mock-lims)
20. [Environment Setup & Running Locally](#20-environment-setup--running-locally)
21. [Configuration & Environment Variables](#21-configuration--environment-variables)
22. [Testing Strategy](#22-testing-strategy)
23. [Evaluation Metrics (your "proof" slide)](#23-evaluation-metrics-your-proof-slide)
24. [Hackathon Build Plan & Team Split](#24-hackathon-build-plan--team-split)
25. [Live Demo Script (5 minutes)](#25-live-demo-script-5-minutes)
26. [Pitch Deck Outline](#26-pitch-deck-outline)
27. [Risks, Limitations & Honest Answers to Judge Questions](#27-risks-limitations--honest-answers-to-judge-questions)
28. [Glossary](#28-glossary)
29. [References](#29-references)

---

## 1. Problem Statement

Legacy pharma applications — LIMS (Laboratory Information Management), MES (Manufacturing Execution), QMS (Quality Management), eBR (electronic batch records), pharmacovigilance and clinical data systems — are hard to maintain, scale and migrate. The bottleneck is **not only technical**: every architectural change in a GxP system can trigger **re‑validation** and **data‑integrity risk**, so organizations freeze these systems for years.

**Refined statement used in the pitch:**

> Pharma organizations cannot modernize legacy GxP applications quickly because every change triggers costly re‑validation and data‑integrity risk, and existing AI modernization tools are generic — they transform code but do not reason about regulatory risk. ModernRx converts any legacy application into a queryable digital twin, scores every component for cloud readiness **and** GxP criticality, uses a council of specialist AI agents to recommend target architecture, and produces a risk‑simulated migration roadmap with an audit‑ready assurance plan.

---

## 2. Why Now — Evidence Base

| Fact | Why it matters for us | Source |
|---|---|---|
| A vFunction/Wakefield survey of 250 tech leaders reported 79% of app modernization projects fail; average cost ~$1.5M; average timeline 16 months. Top failure reasons: wrong expectations (43%) and need for org change (37%). | Failures are **planning** failures → an *advisor* that sets accurate expectations is the right product. | vFunction / DevOps.com |
| FDA final guidance "Computer Software Assurance for Production and Quality System Software" issued 24 Sep 2025 (updated Feb 2026). Supersedes Section 6 of the 2002 General Principles of Software Validation. Risk‑based; encourages digital evidence such as logs and audit trails. | We can **auto‑generate** risk‑scaled assurance plans and digital evidence. | FDA / NSF / GMP‑Publishing |
| EU/PIC/S published drafts of revised Annex 11 (Computerised Systems), new Annex 22 (AI) and revised Chapter 4 on 7 July 2025. Annex 11 draft explicitly addresses cloud and service providers; Annex 22 covers model validation, data quality, performance metrics, human oversight. | Cloud + AI are now explicitly regulated → tooling must be compliance‑aware. Our tool is designed to comply with Annex 22 itself. | ECA / NSF / GMP Insiders |
| AWS Transform markets itself as an agentic AI modernization service (mainframe, .NET, VMware). | Validates the market, but it is **generic** — no GxP reasoning. That's our gap. | AWS |
| IBM Mono2Micro uses runtime traces of business use cases + clustering to propose microservices. A 2026 comparative study found clustering methods (notably HDBSCAN) gave the most consistent decompositions. | Scientific basis for our decomposition engine. | arXiv 2107.09698, arXiv 2601.23141 |
| Multi‑agent LLM systems (VAPU, LegacyTranslate on ~2.5M lines of PL/SQL) shown effective for multi‑phase legacy modernization. | Scientific basis for our Council of agents. | arXiv 2510.18509, arXiv 2603.14054 |

---

## 3. Solution Overview

ModernRx is a web platform with **7 engines** in a pipeline:

```
 Upload repo / connect Git
        │
        ▼
 [1] Living Architecture Twin  ── code + DB + config + runtime traces → Knowledge Graph
        │
        ├──► [2] GxP Criticality Scanner   (Part 11 / Annex 11 / CSA risk tagging)
        ├──► [3] Cloud Readiness Scorer    (12‑factor, tech debt, dependencies)
        │
        ▼
 [4] Blast‑Radius‑Aware Decomposition  (HDBSCAN + GxP constraint)
        │
        ▼
 [5] AI Architecture Council  (5 agents debate → 7R + target pattern per component)
        │
        ▼
 [6] Roadmap Optimizer + Monte Carlo  (wave plan, P50/P80 dates, risk)
        │
        ▼
 [7] Evidence Pack Generator  (CSA assurance plan, characterization tests, PDF)
        │
        ▼
 Dashboard + Chat with the Twin + Human approval gates (audit trail)
```

**Three things nobody else combines:**
1. **GxP criticality** as a first‑class dimension of architecture analysis.
2. **Validation blast radius** as an optimization objective for microservice decomposition.
3. **The tool is itself Annex‑22‑style compliant** (fixed model versions, human‑in‑the‑loop, immutable audit log of AI recommendations).

---

## 4. Mapping to Hackathon Objectives & Outcomes

| Objective | Engine(s) | Concrete output |
|---|---|---|
| 1. Analyze existing architectures | 1 | Interactive dependency graph, auto‑generated C4 diagrams, "ask the twin" chat |
| 2. Evaluate cloud migration readiness | 3 | Readiness score 0–100 per component + blockers list |
| 3. Identify risks & opportunities | 2, 3, 5 | GxP heat map, tech‑debt hotspots, quick wins list |
| 4. Recommend target architecture patterns | 4, 5 | Service boundaries, 7R decision, pattern (Strangler Fig, CQRS, event‑driven, serverless) |
| 5. Generate migration roadmaps | 6 | Wave Gantt with P50/P80 completion, critical path |

| Expected outcome | How we prove it in the demo |
|---|---|
| Faster assessments | Timer on screen: full assessment of the demo app in minutes |
| Clear migration strategy | 7R table + roadmap exported as PDF |
| Reduced transformation risk | Re‑validation scope: naive split vs ModernRx split (% components needing full re‑validation) |
| Improved scalability & maintainability | Before/after coupling & modularity metrics |
| Accelerated cloud adoption | Wave 1 "quick wins" list of components safe to migrate first |

---

## 5. System Architecture

```
┌───────────────────────────── Frontend (Next.js / React) ─────────────────────────────┐
│ Upload │ Twin Graph (Cytoscape) │ GxP Heatmap │ Council Debate │ Roadmap Gantt │ Chat │
└───────────────▲──────────────────────────────────────────────────────▲───────────────┘
                │ REST (JSON)                                          │ WebSocket (live agent stream)
┌───────────────┴──────────────────── API Gateway (FastAPI) ───────────┴───────────────┐
│ Projects │ Jobs │ Approvals │ Audit log                                                │
└──────┬─────────────┬───────────────┬──────────────┬──────────────┬───────────────────┘
       │             │               │              │              │
  In-process background jobs — long jobs run async
       │             │               │              │              │
 ┌─────▼────┐ ┌──────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐ ┌─────▼───────┐
 │ Parser   │ │ GxP Scanner │ │ Decomposer  │ │ Council    │ │ Roadmap +   │
 │ (tree-   │ │ (rules +    │ │ (HDBSCAN +  │ │ (LangGraph │ │ Evidence    │
 │ sitter)  │ │  LLM)       │ │  GxP cost)  │ │  agents)   │ │ (OR-Tools,  │
 └────┬─────┘ └──────┬──────┘ └──────┬──────┘ └─────┬──────┘ │  NumPy, PDF)│
      │              │               │              │        └─────┬───────┘
 ┌────▼──────────────▼───────────────▼──────────────▼──────────────▼──────┐
 │  Neo4j (knowledge graph)  │  SQLite (metadata, embeddings,               │
 │                           │  audit log, approvals)  │  Local disk (files)│
 └────────────────────────────────────────────────────────────────────────┘
                        │
                 LLM provider (Gemini via Google Gemini API; model version pinned)
```

**Design principles**

- **Deterministic first, LLM second:** parsing, metrics, clustering and scheduling are deterministic code. LLMs explain, classify ambiguous items, and debate — every LLM claim must cite a graph node ID.
- **Everything is a job:** long tasks run as in-process background jobs (FastAPI `BackgroundTasks`) so the UI never blocks; progress streams over WebSocket.
- **Every AI output is versioned and approvable:** stored with model name, prompt hash, input hash, timestamp, approver.

---

## 6. Technology Stack (every package, and why)

> **Versions:** pin the latest stable release at the time you build (`pip freeze > requirements.lock`, `package-lock.json`). Minimums listed are safe floors.

### 6.1 Languages
| Language | Where | Why |
|---|---|---|
| **Python 3.11+** | Backend, analysis, ML, agents | Best ecosystem for graphs, ML, LLM orchestration |
| **TypeScript 5+** | Frontend | Type safety for complex graph UI |
| **Cypher** | Neo4j queries | Native graph traversal (blast radius, dependencies) |
| **SQL** | SQLite | Metadata, audit log |
| **Java 17** | Demo target app (mock LIMS) | Realistic legacy Spring monolith |
| **YAML** | GxP rules file, Docker Compose (Neo4j only) | Config |

### 6.2 Backend (Python) — `requirements.txt`
| Package | Purpose |
|---|---|
| `fastapi` | REST + WebSocket API |
| `uvicorn[standard]` | ASGI server |
| `pydantic` (v2), `pydantic-settings` | Schemas, config loading |
| `sqlalchemy` (2.x) | ORM over SQLite (tables created at startup) |
| `neo4j` | Official Neo4j Python driver |
| `httpx` | Async HTTP client |
| `GitPython` | Clone/scan repos, read git history (co‑change coupling) |
| `tree-sitter`, `tree-sitter-language-pack` | Multi‑language parsing (Java, C#, Python, JS, COBOL grammars where available) |
| `sqlglot` | Parse SQL / stored procedures, extract table read/write access |
| `lizard` | Cyclomatic complexity, function length (multi‑language) |
| `networkx` | In‑memory graph algorithms (centrality, communities) |
| `python-louvain` *(or `networkx` Louvain)* | Baseline community detection |
| `scikit-learn` | HDBSCAN (`sklearn.cluster.HDBSCAN`), metrics |
| `numpy`, `pandas`, `scipy` | Numerics, Monte Carlo |
| `sentence-transformers` | Semantic embeddings of class/method names & docs |
| `ortools` | Constraint‑programming wave scheduler (CP‑SAT) |
| `google-genai` | Gemini API client (official Google GenAI SDK) |
| `langgraph`, `langchain-core`, `langchain-google-genai` | Multi‑agent orchestration (state graph) |
| `google-genai` `count_tokens()` | Token budgeting/chunking (no extra package needed) |
| `jinja2` | Report & IaC templates |
| `weasyprint` *(or `reportlab`)* | Evidence Pack PDF |
| `opentelemetry-sdk`, `opentelemetry-exporter-otlp` | Ingest runtime traces |
| `structlog` | Structured JSON logging |
| `pytest`, `pytest-asyncio` | Tests |
| `ruff`, `black`, `mypy` | Lint, format, type‑check |

### 6.3 Frontend (TypeScript) — `package.json`
| Package | Purpose |
|---|---|
| `next` (14+ App Router), `react`, `react-dom` | Framework |
| `typescript` | Types |
| `tailwindcss`, `postcss`, `autoprefixer` | Styling |
| `shadcn/ui` (+ `@radix-ui/*`, `class-variance-authority`, `clsx`, `tailwind-merge`) | UI components |
| `lucide-react` | Icons |
| `cytoscape`, `react-cytoscapejs`, `cytoscape-fcose` | Interactive dependency / twin graph |
| `recharts` | Score charts, Monte Carlo histogram |
| `frappe-gantt` *(or `gantt-task-react`)* | Roadmap Gantt |
| `mermaid` | Render generated C4 / sequence diagrams |
| `@tanstack/react-query` | Server state & caching |
| `zustand` | Client state |
| `zod` | Runtime validation of API payloads |
| `axios` *(or fetch)* | HTTP |
| `react-markdown`, `remark-gfm` | Render agent messages |
| `framer-motion` | Smooth transitions (debate stream, heatmap reveal) |
| `eslint`, `prettier` | Lint & format |

### 6.4 Infrastructure
| Tool | Purpose |
|---|---|
| **Neo4j 5 Community** | Knowledge graph (+ APOC plugin), run as a single Docker container |
| **SQLite** | Metadata, audit log, approvals, embeddings (one local file, no server) |
| **Local disk** (`data/`) | Uploaded repos and generated PDFs |
| **OpenTelemetry Java agent** | Capture runtime traces from demo app |

### 6.5 Demo target app (Java)
| Package | Purpose |
|---|---|
| Spring Boot 2.x (intentionally old) | "Legacy" monolith feel |
| Spring Data JPA + Hibernate, H2 (file mode) | Persistence |
| Thymeleaf | Server‑rendered UI |
| Maven | Build |
| JUnit 4 | Old‑style tests (realistic debt) |

---

## 7. Repository / Folder Structure

```
modernrx/
├── README.md
├── docker-compose.yml             # Neo4j only
├── data/                          # SQLite file, uploads, generated PDFs (git-ignored)
├── .env.example
├── Makefile                       # make up / make seed / make demo / make test
├── backend/
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── app/
│       ├── main.py                # FastAPI app factory
│       ├── config.py              # pydantic-settings
│       ├── api/
│       │   ├── routes_projects.py
│       │   ├── routes_jobs.py
│       │   ├── routes_twin.py
│       │   ├── routes_council.py
│       │   ├── routes_roadmap.py
│       │   ├── routes_evidence.py
│       │   ├── routes_approvals.py
│       │   └── ws.py              # WebSocket streaming
│       ├── core/
│       │   ├── audit.py           # append-only hash-chained audit log
│       │   ├── llm.py             # pinned model client, prompt hashing
│       │   └── logging.py
│       ├── db/
│       │   ├── models.py          # SQLAlchemy models
│       │   ├── session.py
│       │   └── neo4j.py
│       ├── engines/
│       │   ├── twin/
│       │   │   ├── ingest.py      # clone, file walk, language detect
│       │   │   ├── parsers/       # java.py, csharp.py, python.py, sql.py, config.py
│       │   │   ├── runtime.py     # OTel trace ingestion
│       │   │   ├── gitmining.py   # co-change coupling
│       │   │   ├── graph_builder.py
│       │   │   └── c4.py          # generate Mermaid C4
│       │   ├── gxp/
│       │   │   ├── rules.yaml     # deterministic detection rules
│       │   │   ├── scanner.py
│       │   │   └── classifier.py  # LLM fallback classification
│       │   ├── readiness/
│       │   │   ├── checks.py      # 12-factor & cloud blockers
│       │   │   └── scorer.py
│       │   ├── decompose/
│       │   │   ├── features.py    # similarity matrices
│       │   │   ├── cluster.py     # HDBSCAN + GxP constraint
│       │   │   └── metrics.py     # modularity, coupling, blast radius
│       │   ├── council/
│       │   │   ├── state.py
│       │   │   ├── agents.py
│       │   │   ├── prompts/       # one .md prompt per agent
│       │   │   ├── tools.py       # graph query tools for agents
│       │   │   └── graph.py       # LangGraph wiring
│       │   ├── roadmap/
│       │   │   ├── scheduler.py   # OR-Tools CP-SAT
│       │   │   └── montecarlo.py
│       │   └── evidence/
│       │       ├── csa_plan.py
│       │       ├── testgen.py     # characterization tests
│       │       ├── templates/     # Jinja2 HTML → PDF
│       │       └── report.py
│       └── jobs.py                # in-process background job runner
├── frontend/
│   ├── package.json
│   ├── app/
│   │   ├── page.tsx               # project list
│   │   ├── projects/[id]/
│   │   │   ├── overview/page.tsx
│   │   │   ├── twin/page.tsx
│   │   │   ├── gxp/page.tsx
│   │   │   ├── readiness/page.tsx
│   │   │   ├── decomposition/page.tsx
│   │   │   ├── council/page.tsx
│   │   │   ├── roadmap/page.tsx
│   │   │   └── evidence/page.tsx
│   ├── components/
│   └── lib/ (api.ts, schemas.ts, store.ts)
├── demo-lims/                     # the legacy Java app to analyze
│   ├── pom.xml
│   └── src/main/java/com/acme/lims/...
├── eval/
│   ├── benchmark_apps.md          # list of OSS monoliths used
│   ├── run_eval.py
│   └── results/
└── docs/
    ├── architecture.md
    ├── prompts.md
    └── pitch/
```

---

## 8. Engine 1 — Living Architecture Twin

**Goal:** turn source + data + runtime into one knowledge graph.

### 8.1 Ingestion steps
1. **Clone / upload** (`GitPython`; zip upload unpacked to `data/uploads/`).
2. **Language detection** by extension + shebang; count LOC per language.
3. **Static parsing** with tree‑sitter:
   - Java/C#: packages, classes, interfaces, methods, annotations (`@Entity`, `@Transactional`, `@Controller`, `@Scheduled`), imports, method calls, field types.
   - SQL / stored procedures (`sqlglot`): tables, columns, which procedure **reads/writes** which table.
   - Config (`application.properties`, `web.xml`, `.config`, `.env`): DB URLs, file paths, hard‑coded hosts, ports, secrets patterns.
   - Build files (`pom.xml`, `*.csproj`, `requirements.txt`): third‑party libraries + versions → end‑of‑life check.
4. **Runtime traces** (optional but powerful): run demo use cases with the OpenTelemetry Java agent, export spans → map span → method → class. Gives **real call frequency** and **use‑case membership** (Mono2Micro idea).
5. **Git mining:** files changed together in the same commits → **co‑change coupling** weight.
6. **Metrics:** `lizard` for cyclomatic complexity, LOC, function count; fan‑in/fan‑out from the graph.
7. **Embeddings:** `sentence-transformers` on class name + method names + docstrings → semantic similarity; stored in SQLite, cosine similarity computed in NumPy.
8. **Write to Neo4j** (schema in §16).

### 8.2 Auto‑generated artefacts
- **C4 Level 1–3 diagrams** in Mermaid (containers = deployable units; components = clusters).
- **Tech inventory table:** languages, frameworks, versions, EOL flags.
- **"Ask the Twin" chat:** LLM with tools `cypher_query(template_id, params)` (only whitelisted query templates, no free Cypher → safe), `get_node(id)`, `semantic_search(text)`. Every answer lists node IDs used.

### 8.3 Example Cypher templates
```cypher
// Who writes to a regulated table?
MATCH (m:Method)-[:WRITES]->(t:Table {name:$table})
RETURN m.fqn, m.class, m.gxpTier ORDER BY m.fanIn DESC;

// Blast radius of changing a class (3 hops)
MATCH (c:Class {fqn:$fqn})<-[:CALLS|DEPENDS_ON*1..3]-(x)
RETURN DISTINCT x.fqn, x.gxpTier;
```

---

## 9. Engine 2 — GxP Criticality Scanner

**Goal:** tag every component with regulatory criticality. This is the pharma moat.

### 9.1 Dimensions tagged per class/method/table
| Tag | Meaning | Detection signals |
|---|---|---|
| `AUDIT_TRAIL` | Creates/changes audit records | table names like `*audit*`, `*history*`; triggers; classes `AuditService`; fields `changedBy`, `oldValue`, `newValue`, `reason` |
| `E_SIGNATURE` | Electronic signature flows | `sign`, `approve`, `release`, password re‑entry, `signatureMeaning` |
| `ACCESS_CONTROL` | Authentication/authorization | Spring Security config, `@PreAuthorize`, role tables |
| `DATA_INTEGRITY` | Creates/modifies GxP records (results, batches, specs, deviations, CAPA) | domain entity names: `Sample`, `Result`, `Batch`, `Specification`, `Deviation`, `Capa`, `Stability` |
| `PRODUCT_RELEASE` | Batch disposition / release decisions | `release`, `disposition`, `QP` |
| `TIME_SOURCE` | Timestamps on records | `new Date()`, `System.currentTimeMillis()`, DB `NOW()` (cloud time sync matters) |
| `REPORTING_ONLY` | Read‑only analytics | only `SELECT`, no writes |

### 9.2 Risk tier (aligned to CSA's risk‑based thinking)
```
gxp_tier =
  HIGH   if PRODUCT_RELEASE or (DATA_INTEGRITY and writes) or E_SIGNATURE or AUDIT_TRAIL
  MEDIUM if DATA_INTEGRITY read-only or ACCESS_CONTROL
  LOW    otherwise (UI helpers, reporting, utilities)
```
- **Step 1:** deterministic rules from `rules.yaml` (regex + AST patterns + table names).
- **Step 2:** for anything ambiguous (no rule fired but touches a domain entity) → LLM classifier using Gemini structured output (`response_mime_type="application/json"` + `response_schema`) for `{tags:[], tier, rationale, evidence_node_ids:[]}`.
- **Step 3:** **propagation** — if a LOW method calls into a HIGH write path, it inherits `MEDIUM (indirect)`. (The Annex 11 draft explicitly covers systems with indirect impact.)
- **Human review queue:** QA user can override any tier; override is audit‑logged.

### 9.3 `rules.yaml` sample
```yaml
- id: AUDIT_TABLE
  tag: AUDIT_TRAIL
  match: { node: Table, name_regex: "(?i)(audit|history|trail)" }
- id: ESIG_METHOD
  tag: E_SIGNATURE
  match: { node: Method, name_regex: "(?i)(sign|approve|release)", calls_any: ["PasswordEncoder.matches", "AuthenticationManager.authenticate"] }
- id: GXP_ENTITY_WRITE
  tag: DATA_INTEGRITY
  match: { node: Method, writes_table_regex: "(?i)(sample|result|batch|spec|deviation|capa|stability)" }
```

### 9.4 Output
- **GxP Heatmap:** graph nodes coloured red/amber/green.
- **Compliance gap list:** e.g. "audit trail table has no `reason` column", "timestamps from app server local time", "shared admin account in config".

---

## 10. Engine 3 — Cloud Readiness Scorer

Score each component 0–100. Weighted sum of checks (weights in config, explainable):

| Check | Weight | Signal |
|---|---|---|
| Statelessness | 15 | HTTP session usage, in‑memory caches, static mutable fields |
| Local file system dependence | 10 | `new File(`, hard‑coded paths, network shares |
| Hard‑coded config/hosts/secrets | 10 | IPs, `jdbc:` URLs in code, password patterns |
| Framework/runtime EOL | 15 | Java 8, .NET Framework, Spring Boot 1/2, unsupported libs |
| DB coupling (shared tables) | 15 | # of components writing same table |
| Complexity & size | 10 | avg cyclomatic complexity, LOC |
| Test coverage present | 5 | test files ratio |
| Scheduled/batch jobs | 5 | `@Scheduled`, cron, Quartz |
| Licensing/proprietary blockers | 5 | Oracle‑specific SQL, COM, vendor SDKs |
| Observability | 5 | logging framework, health endpoints |
| GxP tier penalty | 5 | HIGH tier reduces "move fast" readiness |

```
readiness = 100 - Σ (weight_i × severity_i)    # severity_i ∈ [0,1]
```
Each deduction stores **evidence node IDs** → clickable in UI.

**Opportunities detected:** dead code (no inbound calls & no runtime hits), duplicate logic (high embedding similarity), quick‑win rehost candidates (high readiness + LOW tier).

---

## 11. Engine 4 — Blast‑Radius‑Aware Decomposition

**Goal:** propose microservice / bounded‑context boundaries that are good architecture **and** minimize re‑validation.

### 11.1 Similarity matrix between classes i, j
```
S(i,j) = w1·Structural(i,j)   # static calls/deps, normalized
       + w2·Runtime(i,j)      # co-occurrence in traces of same use case
       + w3·Data(i,j)         # Jaccard of tables accessed
       + w4·CoChange(i,j)     # git co-change frequency
       + w5·Semantic(i,j)     # cosine of name/doc embeddings
default w = [0.30, 0.20, 0.25, 0.10, 0.15]
```

### 11.2 Clustering
- `sklearn.cluster.HDBSCAN(min_cluster_size=4, metric="precomputed")` on distance `D = 1 − S`.
- HDBSCAN noise points = **outlier classes** → flagged as refactor/remove candidates.

### 11.3 The GxP constraint (our novelty)
Define for a decomposition P:
```
BlastRadius(P) = Σ over clusters c that contain ≥1 HIGH-tier node:
                   |c| + Σ |clusters directly calling c|
RevalScope(P)  = (# components needing full re-validation) / (total components)
```
Post‑processing / constrained refinement:
1. **Must‑link** constraint: nodes on the same HIGH‑tier write path to the same regulated table stay in one cluster (keeps the validated core cohesive).
2. **Cannot‑link** constraint: avoid mixing LOW‑tier utilities into HIGH clusters (keeps HIGH clusters small).
3. Local search (move single nodes between clusters) to minimize:
```
Objective = α·Coupling(P) − β·Cohesion(P) + γ·BlastRadius(P)
default α=1.0, β=1.0, γ=1.5
```
### 11.4 Metrics reported (see §23)
Modularity (Newman), inter‑cluster call ratio (ICP), structural modularity, number of services, BlastRadius, RevalScope — **always compared against: (a) Louvain baseline, (b) plain HDBSCAN without GxP constraint.**

---

## 12. Engine 5 — AI Architecture Council (Multi‑Agent)

### 12.1 Agents
| Agent | Cares about | Typical vote |
|---|---|---|
| **Cloud Architect** | Scalability, managed services, patterns | Refactor to event‑driven / containerize |
| **Validation & QA Lead** | Re‑validation effort, data integrity, CSA | Retain or minimal replatform for HIGH tier |
| **Security Officer** | Zero‑trust, IAM, secrets, audit trail integrity | Add identity provider, encryption, WORM logs |
| **FinOps Analyst** | Cost, licensing, run vs build cost | Rehost quick wins, retire dead code |
| **Regulatory Affairs** | Part 11 / Annex 11 / supplier (cloud) oversight | Requires supplier assessment, data residency |
| **Moderator (Chair)** | Synthesizes, forces evidence, records dissent | Final decision + confidence |

### 12.2 Orchestration (LangGraph state machine)
```
START → load_context(cluster) → parallel_opinions(5 agents)
      → rebuttal_round (each sees others' opinions, 1 round)
      → moderator_synthesis → validate_output(JSON schema + evidence IDs exist in graph)
      → (if invalid) retry_once → human_review_queue → END
```
- **Tools available to agents:** `get_cluster_summary`, `get_node`, `run_template_query`, `get_readiness`, `get_gxp_tags`, `estimate_effort`.
- **No tool can write** to the graph — read‑only.

### 12.3 Output schema (Pydantic)
```python
class CouncilDecision(BaseModel):
    cluster_id: str
    strategy: Literal["Retire","Retain","Rehost","Relocate","Replatform","Repurchase","Refactor"]
    target_pattern: list[Literal["StranglerFig","EventDriven","CQRS","Serverless",
                                 "Containerized","ManagedDB","APIGateway","SaaS"]]
    target_services: list[str]          # e.g. "Kubernetes", "managed Postgres", "message queue"
    confidence: float                   # 0..1
    rationale: str
    risks: list[str]
    dissent: list[dict]                 # {agent, position, reason}
    evidence_node_ids: list[str]        # must exist in Neo4j
    effort_weeks: tuple[float,float,float]  # (optimistic, likely, pessimistic)
```
This model is handed straight to Gemini as `response_schema`, so the API returns conforming JSON; we still re‑validate with Pydantic and check every evidence ID exists in Neo4j before accepting a decision.

### 12.4 Prompting rules (each agent prompt file)
- Role, priorities, and **forbidden behaviours** (no claim without evidence ID).
- Cloud‑agnostic by default; target cloud chosen in project settings (AWS / Azure / GCP) → map to that cloud's managed services.
- Temperature low (0–0.3) for reproducibility; model version pinned; prompt + input hashed and stored.

### 12.5 Effort estimation input
`effort = f(LOC, complexity, #tables, gxp_tier, strategy)` with a simple lookup table (weeks per KLOC per strategy) multiplied by GxP multiplier (HIGH ×1.8, MEDIUM ×1.3, LOW ×1.0). Council can adjust ±30% with justification. The triple feeds Monte Carlo.

---

## 13. Engine 6 — Roadmap Optimizer & Monte Carlo Simulator

### 13.1 Scheduling with OR‑Tools CP‑SAT
- **Tasks:** one per cluster decision (+ shared foundation tasks: landing zone, IAM, CI/CD, observability, supplier qualification).
- **Constraints:**
  - Dependencies: if A calls B heavily and both migrate, B's interface (API facade) before A (strangler order).
  - **GxP freeze windows** (e.g., annual audit month, batch campaigns) → no HIGH‑tier cutover in those weeks.
  - Team capacity per week (squads).
  - Max 1 HIGH‑tier cutover per wave (risk cap).
  - Foundation tasks before any workload.
- **Objective:** minimize makespan + λ·(sum of risk‑weighted start times) → risky items later, after the team has learned on quick wins.
- **Output:** waves (Wave 0 foundation, Wave 1 quick wins, Wave 2 …), Gantt, critical path.

### 13.2 Monte Carlo
- Each task duration ~ **PERT/Beta** distribution from (optimistic, likely, pessimistic).
- 10,000 runs (`numpy`), propagate through the schedule order.
- **Outputs:** P50 / P80 / P95 completion date, probability of finishing by a target date, tornado chart of tasks driving variance.
- **What‑if sliders** in UI: add a squad, move freeze window, change strategy of one cluster → re‑simulate in seconds.

---

## 14. Engine 7 — Evidence Pack Generator

Generates an audit‑oriented PDF per wave (Jinja2 → HTML → WeasyPrint):

1. **System description** (from the twin; C4 diagrams).
2. **Intended use & GxP impact** per component (from Engine 2).
3. **Risk‑based assurance plan (CSA‑style):**
   - HIGH tier → scripted testing of critical functions + independent review.
   - MEDIUM → unscripted / exploratory testing with recorded results.
   - LOW → vendor/automated evidence, ad‑hoc testing.
4. **Characterization tests:** auto‑generated tests that record *current* behaviour of key endpoints/methods (inputs → outputs captured from runtime traces) to check the modernized version behaves the same.
5. **Shadow/differential testing plan:** route copies of real requests to new service, compare responses, report mismatches.
6. **Data migration checks:** row counts, checksums per regulated table, audit‑trail continuity checks.
7. **Traceability matrix:** requirement → component → test → evidence.
8. **Rollback plan** per cutover.
9. **Cloud supplier oversight checklist** (responsibility split, data residency, backup, access).

> **Disclaimer in every pack:** "Draft generated by ModernRx to support — not replace — the organization's validation process. Requires QA review and approval."

---

## 15. Self‑Compliance Layer (Annex 22 for the tool itself)

| Control | Implementation |
|---|---|
| Fixed (static) model version | Model ID pinned in config; recorded with every output |
| Human oversight | Every Council decision is "Proposed" until a named user approves/rejects |
| Audit trail | Append‑only table; each row stores `prev_hash` and `hash = SHA256(prev_hash + payload)` → tamper‑evident chain |
| Reproducibility | Prompt template version, prompt hash, input hash, temperature, seed (where supported) |
| Explainability | Evidence node IDs + rationale required; outputs without valid evidence are rejected |
| Performance monitoring | Track override rate (how often humans reject AI) per agent → shown on admin page |
| Data minimization | Option to send only summaries/metadata to LLM, never raw patient/product data; secrets found in code are masked before storage or LLM calls |

---

## 16. Data Models & Graph Schema

### 16.1 Neo4j nodes
| Label | Key properties |
|---|---|
| `Project` | id, name, targetCloud |
| `Module` | id, name, path, language |
| `Class` | fqn, loc, complexity, fanIn, fanOut, gxpTier, gxpTags[], readiness, clusterId |
| `Method` | fqn, class, loc, complexity, gxpTier, runtimeHits |
| `Table` | name, schema, regulated(bool), rowCountEstimate |
| `Column` | name, type |
| `Endpoint` | httpMethod, path |
| `Library` | name, version, eol(bool) |
| `ConfigItem` | key, valueMasked, kind (host/path/secret/port) |
| `UseCase` | name (from traces) |
| `Cluster` | id, name, size, gxpMax, readinessAvg |
| `Decision` | id, strategy, confidence, status |

### 16.2 Relationships
`CONTAINS`, `CALLS {count}`, `DEPENDS_ON`, `READS`, `WRITES`, `EXPOSES`, `USES_LIB`, `CONFIGURED_BY`, `PART_OF_USECASE {hits}`, `CO_CHANGES {weight}`, `IN_CLUSTER`, `DECIDED_FOR`, `EVIDENCED_BY`.

### 16.3 SQLite tables
```sql
users(id, name, role, created_at)   -- seeded demo users, no login
projects(id, name, repo_url, target_cloud, created_by, created_at)
jobs(id, project_id, type, status, progress, error, started_at, finished_at)
gxp_overrides(id, project_id, node_id, old_tier, new_tier, reason, user_id, ts)
decisions(id, project_id, cluster_id, payload_json, status, model_id, prompt_hash, input_hash, created_at)
approvals(id, decision_id, user_id, action, comment, ts)
roadmaps(id, project_id, schedule_json, montecarlo_json, created_at)
evidence_packs(id, project_id, wave, file_path, created_at)
audit_log(id, ts, actor, action, entity, entity_id, payload_json, prev_hash, hash)
embeddings(id, project_id, node_id, vector BLOB)   -- 384-dim float32
```

---

## 17. REST / WebSocket API Specification

| Method | Path | Body / Params | Returns |
|---|---|---|---|
| POST | `/projects` | name, repo_url \| upload, target_cloud | project |
| GET | `/projects/{id}` | — | project + status |
| POST | `/projects/{id}/analyze` | options (runtime traces on/off) | job_id |
| GET | `/jobs/{job_id}` | — | status, progress |
| GET | `/projects/{id}/twin/graph` | level=module\|class, filter | nodes, edges |
| POST | `/projects/{id}/twin/ask` | question | answer, evidence_ids |
| GET | `/projects/{id}/gxp` | — | tags, tiers, gaps |
| PATCH | `/projects/{id}/gxp/{node_id}` | new_tier, reason | override (audit‑logged) |
| GET | `/projects/{id}/readiness` | — | scores + deductions |
| POST | `/projects/{id}/decompose` | weights, gamma | job_id |
| GET | `/projects/{id}/decomposition` | variant=baseline\|hdbscan\|modernrx | clusters + metrics |
| POST | `/projects/{id}/council/run` | cluster_ids[] | job_id |
| GET | `/projects/{id}/council/decisions` | — | decisions[] |
| POST | `/decisions/{id}/approve` / `/reject` | comment | approval |
| POST | `/projects/{id}/roadmap` | squads, freeze_windows, target_date | job_id |
| POST | `/projects/{id}/roadmap/whatif` | changes | quick re‑simulation |
| POST | `/projects/{id}/evidence/{wave}` | — | PDF download URL |
| GET | `/audit` | filters | audit rows + chain verification result |
| WS | `/ws/jobs/{job_id}` | — | progress events + live agent messages |

---

## 18. Frontend — Screens & Components

1. **Projects** — list, "New assessment" wizard (repo URL / zip, target cloud, runtime traces toggle).
2. **Overview** — KPI cards: LOC, languages, # components, avg readiness, % HIGH GxP, est. duration P80; timer showing assessment duration.
3. **Twin Graph** — Cytoscape (fcose layout); zoom module→class; click node → side panel (metrics, GxP tags, evidence, code snippet); search box; "Ask the Twin" chat drawer.
4. **GxP Heatmap** — same graph coloured by tier; gap list; override button (requires reason).
5. **Readiness** — bar chart per component, deduction breakdown, quick‑win list.
6. **Decomposition** — three tabs: Louvain / HDBSCAN / ModernRx; metrics table side by side; **"Re‑validation scope" big number** comparison (the money shot).
7. **Council** — live streaming debate (chat bubbles per agent avatar), final decision card, dissent shown, Approve/Reject buttons.
8. **Roadmap** — Gantt by wave; Monte Carlo histogram with P50/P80/P95 lines; what‑if sliders.
9. **Evidence** — list of packs per wave, preview + download PDF.
10. **Audit** — table of all actions with "Verify chain ✓" button.

UI notes: dark/light mode, accessible colours (red/amber/green also with icons/labels, not colour alone), responsive.

No login screen: a user switcher in the header picks one of the seeded demo users (architect / QA approver); that name is recorded on approvals, overrides and audit rows.

---

## 19. Demo Target Application (Mock LIMS)

Build a deliberately "legacy" Spring Boot 2 monolith (~5–8k LOC is enough) named **AcmeLIMS** with realistic smells:

| Module | Content | Planted issues |
|---|---|---|
| `sample` | Sample registration, chain of custody | Writes `SAMPLE` table; uses `new Date()` timestamps |
| `result` | Test results entry, OOS flagging | HIGH tier; shares `RESULT` table with reporting |
| `review` | Review & approve results with e‑signature | password re‑entry; audit insert |
| `batch` | Batch disposition / release | PRODUCT_RELEASE |
| `audit` | Audit trail service + `AUDIT_TRAIL` table | missing `reason` column (gap to detect) |
| `instrument` | Instrument file import from `C:\\instrument\\` share | local file system dependency |
| `reporting` | CoA and trend reports | read‑only, LOW tier, quick win |
| `admin` | Users/roles | hard‑coded admin password in properties (security finding) |
| `scheduler` | Nightly stability pull job | `@Scheduled` |
| `util` | String/date helpers, dead code class | outliers/dead code |

Plus scripted use cases (`demo-lims/usecases/*.http` or a small Python script) to generate OpenTelemetry traces: *Register sample → Enter result → Review & sign → Release batch → Print CoA*.

**Second benchmark (credibility):** run ModernRx also on 1–2 well‑known open‑source Java monoliths used in decomposition research (check `eval/benchmark_apps.md`; e.g., a sample "pet clinic"–style app or a larger open‑source healthcare system) to show it generalizes.

---

## 20. Environment Setup & Running Locally

### 20.1 Prerequisites
- Docker Desktop / Docker Engine (only used to run Neo4j)
- Python 3.11+, Node.js 20 LTS, Java 17 + Maven (for demo app)
- A Google Gemini API key (from Google AI Studio)

### 20.2 `docker-compose.yml` (Neo4j only — backend and frontend run directly on the host)
```yaml
services:
  neo4j:    { image: neo4j:5, ports: ["7474:7474","7687:7687"],
              environment: { NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD}", NEO4J_PLUGINS: '["apoc"]' } }
```

### 20.3 Commands
```bash
git clone <your-repo> modernrx && cd modernrx
cp .env.example .env           # fill API key + Neo4j password
make up                        # start Neo4j, backend (uvicorn) and frontend (npm run dev)
make seed                      # create demo users + sample project
make demo-traces               # run AcmeLIMS with OTel agent + use-case script
open http://localhost:3000
```

---

## 21. Configuration & Environment Variables

```
# LLM
GEMINI_API_KEY=...
LLM_MODEL=gemini-2.5-pro             # pinned; recorded in every decision
LLM_TEMPERATURE=0.2
LLM_MAX_OUTPUT_TOKENS=4000
LLM_SEND_RAW_CODE=false              # true = send snippets; false = summaries only

# Datastores
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
DATABASE_URL=sqlite:///data/modernrx.db
DATA_DIR=./data                      # uploads + generated PDFs

# Engines
DECOMP_WEIGHTS=0.30,0.20,0.25,0.10,0.15
DECOMP_GAMMA=1.5
HDBSCAN_MIN_CLUSTER_SIZE=4
MONTECARLO_RUNS=10000
GXP_MULTIPLIER_HIGH=1.8
GXP_MULTIPLIER_MEDIUM=1.3
```

---

## 22. Testing Strategy

| Layer | Tool | What |
|---|---|---|
| Unit | `pytest` | parsers on fixture files, GxP rules, readiness scoring math, blast radius formula, audit hash chain; scheduler never violates dependency/freeze constraints; Monte Carlo P50 ≤ P80 ≤ P95 |
| Integration | `pytest` + Neo4j | full pipeline on AcmeLIMS → expected planted findings detected |
| LLM evals | custom `eval/` scripts | Council output always valid JSON, evidence IDs exist, decisions stable across 3 reruns |
| End‑to‑end | manual run of the demo script (§25) | upload → analyze → approve → download PDF |
| **Golden findings test** | pytest | AcmeLIMS must surface: missing audit `reason` column, local file share, hard‑coded admin password, `new Date()` timestamps, dead code class, shared `RESULT` table |

---

## 23. Evaluation Metrics (your "proof" slide)

| Metric | Definition | Compare against |
|---|---|---|
| **Assessment time** | Wall‑clock from upload to full report | Team's own manual estimate for reviewing same app (state assumption honestly) |
| **Planted‑finding recall** | # planted issues found / # planted | target 100% on AcmeLIMS |
| **Modularity (Q)** | Newman modularity of cluster partition on call graph | Louvain, plain HDBSCAN |
| **Inter‑cluster call ratio** | calls crossing clusters / total calls (lower = better) | baselines |
| **BlastRadius** | formula in §11.3 | plain HDBSCAN |
| **RevalScope %** | components needing full re‑validation / total | plain HDBSCAN (headline number) |
| **Decision stability** | % clusters with same strategy across 3 Council reruns | target ≥ 80% |
| **Evidence validity** | % Council claims with valid node IDs | target 100% (enforced) |
| **Human override rate** | % decisions rejected by reviewer | shown live |

Present as one table + one bar chart. **Only report numbers you actually measured.**

---

## 24. Hackathon Build Plan & Team Split

Assuming 4 people, ~36–48 hours.

| Person | Role | Deliverables |
|---|---|---|
| P1 | Backend & Twin | FastAPI, Neo4j schema, tree‑sitter/sqlglot parsers, OTel ingest |
| P2 | ML & Algorithms | similarity matrix, HDBSCAN + GxP constraint, metrics, OR‑Tools scheduler, Monte Carlo |
| P3 | AI Agents | GxP LLM classifier, Council LangGraph, prompts, evidence pack generator |
| P4 | Frontend & Demo | Next.js screens, Cytoscape graph, Gantt, AcmeLIMS demo app, pitch deck |

| Time block | Milestone |
|---|---|
| H0–H4 | Repo skeleton, Neo4j up, AcmeLIMS skeleton, schemas agreed |
| H4–H12 | Parsing → graph in Neo4j; graph visible in UI |
| H12–H20 | GxP scanner + readiness + heatmap |
| H20–H28 | Decomposition (3 variants) + metrics table; Council v1 |
| H28–H36 | Roadmap + Monte Carlo + evidence PDF; approvals + audit chain |
| H36–H42 | Polish UI, eval numbers, golden‑findings test green |
| H42–H48 | Rehearse demo ×3, record backup video, finalize slides |

**MVP cut line (if time runs out):** keep Engines 1, 2, 4, 5, 6. Git mining and what‑if sliders are stretch goals. Always keep the RevalScope comparison — it's the winning moment.

---

## 25. Live Demo Script (5 minutes)

1. **0:00 — Hook (20s):** "Most modernization projects fail. In pharma it's worse: every change risks re‑validation."
2. **0:20 — Upload AcmeLIMS (20s):** timer starts.
3. **0:40 — Twin graph forms (40s):** click `ReviewService` → see calls, tables, runtime hits. Ask the twin: "Which code writes batch release data?"
4. **1:20 — GxP heatmap (40s):** red core appears; show detected gaps (missing audit reason, local timestamps, hard‑coded admin password).
5. **2:00 — Decomposition (50s):** toggle naive vs ModernRx → **RevalScope drops** (show your measured number). "Same architecture quality, far less re‑validation."
6. **2:50 — Council debate (50s):** live stream; Validation Lead pushes back on refactoring `batch`; Moderator decides Strangler Fig + keep core; dissent recorded; click **Approve** → audit row appears.
7. **3:40 — Roadmap (40s):** waves; P80 date; drag a freeze window → re‑simulate.
8. **4:20 — Evidence pack (25s):** download PDF; show assurance plan + traceability matrix.
9. **4:45 — Close (15s):** "ModernRx: modernize pharma apps faster, and prove nothing broke."

Backup: pre‑recorded video + pre‑computed results cached in DB in case Wi‑Fi/LLM fails.

---

## 26. Pitch Deck Outline

1. Title + one‑liner
2. Problem (failure stats + validation burden)
3. Why now (CSA 2025, Annex 11/22 drafts, agentic AI)
4. Gap (generic tools vs GxP need)
5. Solution — 7 engines diagram
6. Novelty — blast‑radius‑aware decomposition + self‑compliant AI
7. Live demo
8. Proof — metrics table
9. Architecture & stack
10. Team

---

## 27. Risks, Limitations & Honest Answers to Judge Questions

| Question | Answer |
|---|---|
| "Does this replace validation?" | No. It drafts a risk‑based plan and evidence; QA reviews and approves. Human gate is built in. |
| "LLMs hallucinate." | Deterministic engines do the analysis; LLM claims must cite graph node IDs and are schema‑validated; invalid outputs are rejected. |
| "What about COBOL / mainframe / vendor COTS?" | Parser layer is pluggable (tree‑sitter grammars); for COTS without source we analyze DB schema, config, interfaces and logs only, with lower confidence shown. |
| "Is GxP tiering accurate?" | Rules + LLM + propagation + mandatory human override queue; we report override rate openly. |
| "Why not just use AWS Transform?" | Complementary: it transforms code; we decide *what/when/how safely* in a GxP context, and we're cloud‑agnostic. Our roadmap can hand off to such tools. |
| "Data privacy?" | Summary‑only mode; secrets masked; runs entirely on your own machine. |
| "Effort estimates?" | PERT ranges + Monte Carlo, not single numbers; calibrate with customer history over time. |

Known limitations: small demo scale; effort model is heuristic; runtime traces require running the app; regulatory texts referenced (Annex 11/22) were drafts at time of writing — check current status.

---

## 28. Glossary

- **GxP** — "Good x Practice" regulations (GMP, GLP, GCP…).
- **CSA** — Computer Software Assurance; FDA risk‑based approach to software assurance.
- **CSV** — Computer System Validation (traditional, documentation‑heavy).
- **21 CFR Part 11** — US rules for electronic records & signatures.
- **EU GMP Annex 11** — EU rules for computerised systems; **Annex 22** — draft EU rules for AI in GMP.
- **ALCOA++** — data integrity principles (Attributable, Legible, Contemporaneous, Original, Accurate, + Complete, Consistent, Enduring, Available, Traceable).
- **7R** — Retire, Retain, Rehost, Relocate, Replatform, Repurchase, Refactor.
- **Strangler Fig** — gradually route functionality from legacy to new services behind a facade.
- **CQRS** — separate read and write models (useful for audit‑heavy domains).
- **HDBSCAN** — hierarchical density‑based clustering, finds clusters + outliers.
- **CP‑SAT** — Google OR‑Tools constraint solver.
- **PERT** — three‑point estimate (optimistic, likely, pessimistic).
- **P80** — date by which 80% of simulations finish.
- **LIMS / MES / QMS / eBR** — lab, manufacturing, quality, electronic batch record systems.

---

## 29. References

- vFunction / Wakefield Research — "Why App Modernization Projects Fail" survey: https://vfunction.com/blog/survey-why-application-modernization-projects-fail/ ; summary: https://devops.com/?p=153455
- FDA — Computer Software Assurance for Production and Quality System Software (Sept 2025): https://www.hhs.gov/guidance/sites/default/files/hhs-guidance-documents/FDA/guidance-computer-software-assurance-production-quality-system.pdf
- NSF — FDA Final Guidance CSA (incl. Feb 2026 update note): https://www.nsf.org/life-science-regulatory-news/fda-final-guidance-computer-software-assurance-csa
- GMP Publishing — CSA guidance summary: https://www.gmp-publishing.com/blog/fda-guidance-on-computer-software-assurance-csa
- ECA / GMP Compliance — Drafts of Annex 11, Annex 22, Chapter 4: https://www.gmp-compliance.org/gmp-news/drafts-of-eu-gmp-guideline-annex-11-annex-22-and-chapter-4-released-for-comment
- GMP Insiders — 2025 EU GMP draft updates: https://gmpinsiders.com/2025-eu-gmp-draft-chapter-4-annex-11-annex-22/
- Regask — Annex 22 overview: https://regask.com/eu-gmp-guidelines-2025-ai-computerized-systems-documentation-update/
- AWS — AWS Transform GA announcement: https://aws.amazon.com/blogs/migration-and-modernization/aws-transform-generally-available/
- Kalia et al. — Mono2Micro (arXiv 2107.09698): https://arxiv.org/abs/2107.09698v2
- From Monolith to Microservices: A Comparative Evaluation of Decomposition Frameworks (arXiv 2601.23141): https://arxiv.org/pdf/2601.23141
- A Hierarchical DBSCAN Method for Extracting Microservices (arXiv 2206.07010): https://ar5iv.labs.arxiv.org/html/2206.07010
- VAPU: System for Autonomous Legacy Code Modernization (arXiv 2510.18509): https://arxiv.org/abs/2510.18509v1
- LegacyTranslate: LLM‑based Multi‑Agent Method for Legacy Code Translation (arXiv 2603.14054): https://arxiv.org/html/2603.14054
