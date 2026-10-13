# ModernRx — System Architecture & Technical Specifications

> **One-liner:** Generic AI tools rewrite code. ModernRx tells a pharma company *what* to modernize, *in which order*, and *how to prove to FDA/EMA that nothing broke*.

---

## 1. High-Level Pipeline Architecture

ModernRx is composed of **seven cooperating engines** connected by a streaming in-process job hub and unified knowledge graph:

```
 Upload Repo / ZIP / Git
            │
            ▼
 [1] Living Architecture Twin  (AST Parsers, OTel Runtime Traces, Git Mining, C4 Level 1-3 Diagrams)
            │
            ├──► [2] GxP Criticality Scanner   (21 CFR Part 11 / EU Annex 11 / CSA Risk Tagging)
            ├──► [3] Cloud Readiness Scorer    (12-Factor, Tech Debt, Deductions, Dead Code Finder)
            │
            ▼
 [4] Blast-Radius-Aware Decomposition  (HDBSCAN + GxP Must-Link / Cannot-Link Constraints)
            │
            ▼
 [5] AI Architecture Council  (5 Specialist Agents: Cloud Architect, Validation Lead, Security, FinOps, Regulatory)
            │
            ▼
 [6] Roadmap Optimizer + Monte Carlo  (CP-SAT Solver, GxP Freeze Windows, 10,000 PERT Runs)
            │
            ▼
 [7] Evidence Pack Generator  (CSA Assurance Plan, Traceability Matrix, Characterization Tests, PDF Export)
            │
            ▼
 Interactive Cytoscape Twin + Annex 22 Immutable Audit Trail + Human Approval Gates
```

---

## 2. The 7 Engines

### Engine 1: Living Architecture Twin
- **Static Parsing:** Multi-language parsing (Java, SQL, XML, Config) extracting packages, classes, methods, annotations, field types, and DDL table reads/writes.
- **Dynamic Ingestion:** OpenTelemetry span ingestion mapping real runtime calls to classes and execution frequencies.
- **Git Mining:** Commit co-change coupling weights for files frequently modified together.
- **Embedded Graph Store:** High-performance NetworkX graph store persisted to SQLite with optional mirroring to Neo4j.
- **Mermaid C4 Generation:** C4 Level 1 (System Context), Level 2 (Container), and Level 3 (Component) diagrams.
- **"Ask the Twin" Chat:** Natural language query agent restricted to whitelisted Cypher query templates, returning verified node IDs.

### Engine 2: GxP Criticality Scanner
- Tags every class, method, and table across 7 dimensions:
  - `AUDIT_TRAIL`
  - `E_SIGNATURE`
  - `ACCESS_CONTROL`
  - `DATA_INTEGRITY`
  - `PRODUCT_RELEASE`
  - `TIME_SOURCE`
  - `REPORTING_ONLY`
- Propagates risk tiers: if low-tier code writes to a high-tier path, it inherits `MEDIUM (indirect)` criticality.
- Flags compliance gaps (missing audit reason column, local timestamps, hardcoded credentials, local file shares).
- Provides human override queue with mandatory reason and SHA-256 audit logging.

### Engine 3: Cloud Readiness Scorer
- Evaluates 11 cloud readiness factors:
  1. Statelessness (HTTP session, in-memory caches)
  2. Local file system dependence
  3. Hardcoded configs, hosts, and secrets
  4. Framework/runtime EOL
  5. DB coupling (shared tables across services)
  6. Complexity & size (cyclomatic complexity)
  7. Test coverage present
  8. Scheduled / batch jobs
  9. Proprietary / vendor blockers
  10. Observability & health checks
  11. GxP tier penalty
- Automated opportunity finder: identifies dead code classes, duplicate logic, and quick-win rehost candidates.

### Engine 4: Blast-Radius-Aware Decomposition
- Builds a 5-dimensional similarity matrix between all classes:
  - Structural calls & dependencies (30%)
  - Runtime co-occurrence in trace use cases (20%)
  - Data table access Jaccard overlap (25%)
  - Git co-change frequency (10%)
  - Semantic name/doc embedding cosine similarity (15%)
- Clusters with HDBSCAN on distance $D = 1 - S$.
- Applies pharma-specific GxP constraints:
  - **Must-Link:** Components on the same regulated write path stay together.
  - **Cannot-Link:** Prevents low-tier utilities from polluting high-tier regulated clusters.
- Optimizes:
  $$\text{Objective} = \alpha \cdot \text{Coupling} - \beta \cdot \text{Cohesion} + \gamma \cdot \text{BlastRadius}$$
- Produces comparative metrics across Louvain, Plain HDBSCAN, and ModernRx with the headline **RevalScope% reduction**.

### Engine 5: AI Architecture Council
- Five specialized agents debate modernizing each cluster:
  - **Cloud Architect:** Scalability, managed services, containerization.
  - **Validation & QA Lead:** Re-validation effort, Part 11/Annex 11 audit trails, data integrity.
  - **Security Officer:** Zero-trust, secrets, IAM, encryption.
  - **FinOps Analyst:** Build vs. run cost, licensing, ROI.
  - **Regulatory Affairs:** Cloud service provider oversight, data residency.
- Moderated by a Council Chair synthesizing opinions and recording dissenting votes.
- Every claim must cite valid graph node IDs.
- Outputs conforming to 7R migration strategies: Retire, Retain, Rehost, Relocate, Replatform, Repurchase, Refactor.

### Engine 6: Roadmap Optimizer & Monte Carlo Simulator
- **OR-Tools CP-SAT Constraint Programming:**
  - Enforces dependency precedence constraints (APIs before callers).
  - Respects GxP Freeze Windows (annual audit months, batch campaigns).
  - Caps maximum 1 HIGH-tier cutover per wave to limit regulatory blast radius.
- **Monte Carlo Simulator:**
  - 10,000 PERT/Beta distribution runs from optimistic, likely, and pessimistic estimates.
  - Generates P50, P80, and P95 delivery milestones.
  - Tornado sensitivity analysis showing top variance drivers.
- **Interactive What-If Sliders:** Immediate re-simulation when squad count or freeze windows are tweaked.

### Engine 7: Evidence Pack Generator
- Generates 9-part audit-ready validation reports (HTML and PDF):
  1. System Description (C4 container and component diagrams)
  2. Intended Use & GxP Impact per component
  3. Risk-Based Testing Strategy (CSA guidance)
  4. Auto-Generated Characterization Tests
  5. Shadow / Differential Testing Strategy
  6. Regulated Data Migration Checksums & Row Counts
  7. Traceability Matrix (Requirements → Code → Evidence)
  8. Cutover & Rollback Contingency Procedures
  9. Cloud Supplier Oversight Checklist

---

## 3. Self-Compliance Layer (EU Annex 22 / 21 CFR Part 11)

ModernRx models compliance within its own software architecture:
- **Pinned Model Versions:** Static model ID (`gemini-2.5-pro` or fallback deterministic) recorded with every decision.
- **Prompt & Input Hashes:** Cryptographic hashing of prompts, inputs, and seeds for full audit reproducibility.
- **Cryptographic Audit Trail:** Append-only SQLite table where each row contains `prev_hash` and `hash = SHA256(prev_hash + canonical_payload)`. Any tampering breaks the chain and is detected by `POST /audit/verify`.
- **Human-in-the-Loop:** All AI recommendations remain in `Proposed` state until a named user explicitly Approves or Rejects them with a reason.
