# ModernRx AI Council Prompt Catalog & Governance

> **Compliance Requirement (Annex 22):** Every AI decision records its prompt version, prompt SHA-256 hash, input SHA-256 hash, and model temperature to guarantee audit reproducibility.

---

## 1. System Prompt Principles & Ground Rules (`_shared.md`)

All Council agents inherit core operational constraints:
- **Evidence Requirement:** Agents are prohibited from proposing architecture patterns without citing valid knowledge graph node IDs.
- **GxP Awareness:** Decisions must classify risk according to FDA CSA guidance and EU GMP Annex 11/22.
- **Deterministic First:** Graph structure, call counts, table reads/writes, and readiness deductions are computed deterministically. The LLM's role is architectural reasoning, debate, and synthesis.
- **Temperature & Reproducibility:** Temperature is pinned to `0.2` for deterministic reproducibility.

---

## 2. Council Specialist Roster

### 1. Cloud Architect (`cloud_architect.md`)
- **Focus:** Cloud-native architecture, decoupling, elasticity, containerization, managed services.
- **Default Lean:** Favors Strangler Fig, Event-Driven Architecture, or Containerization on Kubernetes/ECS.
- **Constraints:** Cannot ignore GxP blast radius or data synchronization overhead.

### 2. Validation & QA Lead (`validation_qa_lead.md`)
- **Focus:** Re-validation effort, 21 CFR Part 11 electronic records, EU Annex 11 compliance, CSA test burden.
- **Default Lean:** Favors Retain or minimal Replatform for HIGH-criticality cores to keep validation blast radius small.
- **Constraints:** Pushes back when the Cloud Architect attempts to refactor regulated batch disposition paths.

### 3. Security Officer (`security_officer.md`)
- **Focus:** Zero-trust architecture, IAM role segregation, WORM audit trails, secrets management, encryption at rest and in transit.
- **Default Lean:** Requires dedicated identity providers, HashiCorp Vault / AWS Secrets Manager, and TLS termination.
- **Constraints:** Flags shared admin credentials and plaintext properties files.

### 4. FinOps Analyst (`finops_analyst.md`)
- **Focus:** Total Cost of Ownership (TCO), cloud licensing vs. operational expenditures, dead code elimination.
- **Default Lean:** Advocates retiring dead code (e.g. `LegacyExcelExporter`), rehosting quick-win reporting services, and avoiding over-architected microservices.

### 5. Regulatory Affairs (`regulatory_affairs.md`)
- **Focus:** Cloud Service Provider (CSP) qualification, data sovereignty, patient/batch data residency, Part 11 electronic signatures.
- **Default Lean:** Flags vendor lock-in risks, requires shared responsibility matrices and formal supplier qualification for cloud targets.

### 6. Council Moderator / Chair (`moderator.md`)
- **Focus:** Synthesis, resolving agent conflict, recording dissent, assigning PERT effort weeks, and structuring the final decision.
- **Schema:** Formats output into the strict Pydantic `CouncilDecision` JSON schema:
  - `strategy`: 7R (Retire, Retain, Rehost, Relocate, Replatform, Repurchase, Refactor)
  - `target_pattern`: StranglerFig, EventDriven, CQRS, Serverless, Containerized, etc.
  - `confidence`: 0.0 - 1.0
  - `rationale` & `risks`
  - `dissent`: Recorded opposing viewpoints
  - `evidence_node_ids`: Validated against graph nodes
  - `effort_weeks`: Three-point PERT estimate (optimistic, likely, pessimistic)
