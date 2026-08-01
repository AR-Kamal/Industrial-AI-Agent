# Architecture Decision Log

This log records accepted decisions. New or changed decisions receive a new ADR; do not silently rewrite history. “Provisional” decisions may be reversed before their implementation milestone with a documented superseding ADR.

## ADR-001 — Standalone system boundary

- Status: Accepted
- Date: 2026-07-28
- Decision: Build a standalone technical-support/training chatbot with no connection to machines, PLCs, HMIs, sensors, industrial software, or production data.
- Consequences: All machine facts come from approved documents and user-entered evidence. No live diagnosis, control, predictive maintenance, or integration scaffolding is built in Plan A.

## ADR-002 — Server-rendered Django web stack

- Status: Accepted
- Date: 2026-07-28
- Decision: Use Django, Django Templates, HTMX, and Bootstrap.
- Consequences: There is no separate SPA. Django owns validation, rendering, persistence, uploads, and orchestration. HTMX provides progressive partial updates.

## ADR-003 — Local zero-cost Plan A

- Status: Accepted
- Date: 2026-07-28
- Decision: Use the existing Windows computer, SQLite, Ollama, and local disk. Do not use paid APIs, hosting, domains, databases, or cloud storage.
- Consequences: Performance and vision capability depend on existing hardware. Localhost is the default exposure.

## ADR-004 — Chroma behind a repository interface

- Status: Provisional
- Date: 2026-07-28
- Decision: Use embedded persistent Chroma for the first local vector store, isolated behind `knowledge_base` repository interfaces.
- Rationale: It provides persistence, metadata filtering, and a straightforward local Python workflow. FAISS alone would require additional metadata/persistence design.
- Consequences: Chroma is a runtime dependency and generated indexes are never committed. A spike in Milestone 1 must confirm Windows/Python compatibility and deterministic rebuilds; otherwise supersede this ADR with FAISS plus explicit metadata storage.

## ADR-005 — Separate model-function interfaces

- Status: Accepted
- Date: 2026-07-28
- Decision: Define independent interfaces/configuration for text generation, vision analysis, and embeddings.
- Consequences: A single model is never assumed to support all tasks. Each function has its own readiness and acceptance tests.

## ADR-006 — Provider-neutral server-side gateway

- Status: Accepted
- Date: 2026-07-28
- Decision: All model access passes through `ai_gateway` adapters on the Django server.
- Consequences: Browser-to-Ollama/cloud calls are prohibited. Provider-specific code and error translation stay inside adapters. Future cloud provider changes must not require view or RAG rewrites.

## ADR-007 — Direct RAG services before a framework

- Status: Provisional
- Date: 2026-07-28
- Decision: Implement ingestion, retrieval, and orchestration with focused Python services instead of initially adopting LangChain or LlamaIndex.
- Rationale: The pilot needs a small, inspectable workflow with stable citations and limited dependency surface.
- Consequences: The project owns its service contracts and evaluation logic. A framework may be introduced only by a later ADR based on demonstrated complexity.

## ADR-008 — Layered, fail-closed safety enforcement

- Status: Accepted
- Date: 2026-07-28
- Decision: Enforce safety before generation and validate model output afterward, in addition to safety prompt rules.
- Consequences: Unsafe output is withheld and replaced by an escalation response. Safety tests are release blockers; source documents and user prompts cannot override policy.

## ADR-009 — Approved sources and immutable citation identity

- Status: Accepted
- Date: 2026-07-28
- Decision: Retrieval uses only active approved source versions, and citations are application-generated from retrieved chunk records.
- Consequences: Ad-hoc uploads do not automatically enter the knowledge base. Index builds capture source checksums and processing/model configuration.

## ADR-010 — Private, rebuildable local data

- Status: Accepted
- Date: 2026-07-28
- Decision: Keep sources/uploads under private runtime paths and keep generated indexes separate and disposable.
- Consequences: Runtime data, SQLite files, indexes, logs, and model files are Git-ignored. A clean index rebuild is part of acceptance.

## ADR-011 — Local static assets

- Status: Provisional
- Date: 2026-07-28
- Decision: Vendor HTMX and Bootstrap assets in the repository rather than require public CDNs.
- Rationale: Plan A must work locally without external service availability or information leakage.
- Consequences: Asset versions must be recorded and updated deliberately.

## ADR-012 — Production remains an architectural seam

- Status: Accepted
- Date: 2026-07-28
- Decision: Allow future PostgreSQL/pgvector and approved cloud-provider adapters in interfaces and configuration, but perform no production deployment work in Plan A.
- Consequences: No paid provider is selected. Authentication hardening, hosted storage, monitoring, backups, rate/cost controls, and cloud retention are future implementation work.

## ADR-013 — Direct HTTPX Ollama adapter

- Status: Accepted
- Date: 2026-07-29
- Decision: Implement the local text provider with HTTPX against Ollama's OpenAI-compatible `/v1/chat/completions` and `/v1/models` endpoints.
- Rationale: A small provider-specific adapter avoids coupling application services to an OpenAI SDK while preserving the replaceable gateway contract.
- Consequences: Ollama response parsing and error translation remain inside `ai_gateway.providers.ollama`. Only loopback HTTP endpoints are accepted during Plan A. Cloud adapters, embeddings, vision, RAG, and streaming remain unimplemented.

## ADR-014 — Deterministic safety enforcement around local generation

- Status: Accepted
- Date: 2026-07-29
- Decision: Apply a versioned manufacturing system prompt, block explicit safety-system bypass requests before generation, validate generated output, and inject the no-live-connection disclaimer when required.
- Consequences: Unsafe model text is never stored or displayed as the assistant answer. Safety fallbacks are application-authored and testable independently of the selected model.

## ADR-015 — Human approval before ingestion

- Status: Accepted
- Date: 2026-07-29
- Decision: Registration and metadata import never imply approval. Only an
  authenticated staff reviewer may approve a document, and ingestion enforces
  approval again at the service boundary.
- Consequences: Commands cannot accidentally index newly supplied material.
  Rejected and archived documents cannot be processed.

## ADR-016 — Structured extraction with explicit uncertainty

- Status: Accepted
- Date: 2026-07-29
- Decision: Extract PDF, DOCX, TXT, and Markdown into typed blocks carrying
  section and page provenance. Preserve safety statements and procedures; flag
  tables, diagrams, empty/scanned pages, and weak structure for manual review.
  Do not perform OCR.
- Consequences: Extraction is inspectable and conservative. Complex tables and
  diagrams remain human-review items, and scanned documents cannot enter the
  future index silently.

## ADR-017 — Deterministic, reviewable chunks before vectors

- Status: Accepted
- Date: 2026-07-29
- Decision: Use heading- and procedure-aware deterministic chunking, stable
  source/version/content-derived identifiers, and per-chunk review status.
  Embedding, vector storage, and indexing remain protocols only.
- Consequences: Reprocessing is reproducible and chunks can be corrected or
  excluded before retrieval. PyMuPDF is the current PDF parser; its AGPL or
  commercial licensing must be reviewed before distribution.

## ADR-018 — Immutable generated chunks with reproducible split corrections

- Status: Accepted
- Date: 2026-07-30
- Decision: Do not edit or delete a generated chunk when correcting its
  boundaries. Store a `ChunkSplitCorrection` recipe and materialize ordered
  child chunks with inherited provenance. Supersede and retrieval-disable the
  source while retaining it for audit.
- Rationale: Human review must improve extraction without destroying evidence
  or creating corrections that disappear silently during reprocessing.
- Consequences: Reprocessing reapplies a correction only on one exact source
  content-hash match. Changed or ambiguous source content makes the correction
  stale and disables its children until reviewed. Split children use decimal
  sequence positions and deterministic correction IDs. Chunk merging and
  unrestricted editing remain out of scope.

## ADR-019 — Offline review files are validated instructions, not data imports

- Status: Accepted
- Date: 2026-07-30
- Decision: Export current chunks to XLSX, CSV, or JSON, but interpret returned
  rows only as proposed actions. Parse all formats into one neutral schema,
  validate the complete batch, and apply through audited domain services in one
  transaction.
- Rationale: Spreadsheet review is efficient but must not become direct
  database editing or bypass hash, provenance, safety, or split controls.
- Consequences: Apply requires an authorized reviewer plus either a matching
  digest-bound dry-run report or explicit confirmation. Any invalid row blocks
  the batch. Metadata changes receive their own audit record; split changes use
  the existing correction service. No AI generates review decisions.

## ADR-020 — Correction children are replaced, never edited

- Status: Accepted
- Date: 2026-07-31
- Decision: Correct incomplete content in a correction child by superseding it
  and creating one deterministic replacement child. Preserve the original
  content, hash, split parent and provenance permanently.
- Rationale: Direct edits would destroy reviewed evidence and make split
  correction reapplication non-reproducible.
- Consequences: Replacement requires an exact source hash, reviewer, reason,
  notes, and safety confirmation where applicable. Reprocessing reapplies the
  recipe only after the source split child is reconstructed exactly; otherwise
  it becomes stale and fails closed.

## ADR-021 — Accept trailing whitespace; defer correction portability

- Status: Accepted
- Date: 2026-07-31
- Decision: Accept trailing whitespace after the required final sentence of
  `CHK-R-dc0bd8a616b4bf71705f8eb93f535f` as non-substantive. Validate the
  sentence with `rstrip()` or equivalent without modifying stored content.
- Decision: Keep reviewed correction recipes database-resident for Milestone 3.
  A fresh database created from committed files does not recreate the reviewed
  correction dataset.
- Consequences: A future milestone must define a versioned correction manifest
  or controlled dataset-reconstruction mechanism before corrected datasets can
  be reproduced across computers or deployment environments.

## ADR-022 — Qdrant Local Mode and versioned retrieval indexes

- Status: Accepted
- Date: 2026-07-31
- Decision: Supersede ADR-004's proposed Chroma backend with pinned
  `qdrant-client` Local Mode. Django remains authoritative; each immutable
  collection has a `VectorIndexVersion`, per-chunk hash records, and is exposed
  only after count validation and atomic activation.
- Rationale: The approved Milestone 4 brief requires Qdrant Local Mode and
  provider-neutral adapters. Versioned collections allow failed builds and
  model/corpus changes without replacing the last valid active index.
- Consequences: Runtime collections live under Git-ignored
  `var/vector_store/`. Retrieval revalidates eligibility and source hashes in
  Django. Thresholds are embedding-model-specific and remain provisional until
  the candidate evaluation cases receive human approval.
