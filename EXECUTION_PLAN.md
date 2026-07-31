# Zero-Cost Prototype Execution Plan

Status: Active  
Owner: single developer  
Last updated: 2026-07-29

## Purpose

Deliver and formally evaluate a local standalone manufacturing technical-support chatbot grounded in approved documents. This plan implements Plan A only. It follows `PROJECT_SPEC.md` and the decisions in `docs/decisions.md`.

## Scope and non-goals

In scope: local Django UI, approved-document RAG, Ollama text/embedding integration, guided troubleshooting, safe image workflow to the hardware-approved level, citations, feedback, evaluation records, and reproducible local setup.

Out of scope: production deployment, paid/cloud calls, authentication hardening for public use, industrial integration, machine control, predictive maintenance, production analytics, and fixed-camera inspection.

## Entry conditions

- Owner answers OQ-001 before domain data preparation.
- Approximately 10–20 current candidate documents can be reviewed.
- A reviewer can help define 30–40 questions and 15–20 troubleshooting cases.
- Existing PC specifications and available disk space can be inventoried.
- At least one qualified technical reviewer is identified, or training-demonstration-only status is accepted.

## Milestone 0 — Scope, evidence, and test baseline

Deliver:

- close the applicable items in `docs/open_questions.md`;
- name and bound the pilot subject;
- create document-register, test-matrix, issue-log, and change-log templates;
- inventory hardware and approved source files;
- define expected-answer points and safety cases;
- initialize private Git practices and runtime-data exclusions.

Acceptance:

- pilot inclusion/exclusion statement is approved;
- source candidates have owner/version/status/readability/duplicate checks;
- test records include all required fields;
- confidential/runtime paths are excluded from version control.

## Milestone 1 — Reproducible local foundation and technical spikes

Deliver:

- choose and record supported Python version;
- create Django project/settings, local static assets, environment template, pinned dependencies, and Windows setup guide;
- create thin provider contracts and an Ollama readiness/connection test;
- spike Chroma persistence/rebuild compatibility and a representative parser;
- inventory and time-box a small local vision-model test.

Acceptance:

- a clean local setup starts Django and passes Django system checks;
- one text request and one embedding request travel through gateway interfaces;
- stopped Ollama, invalid model, and timeout produce normalized safe errors;
- vector spike persists, queries, deletes/rebuilds, and records configuration;
- ADR-004 and OQ-003 are confirmed or superseded with evidence.

Validation: automated gateway/configuration tests plus explicit opt-in Ollama smoke tests.

## Milestone 2 — Browser chat, persistence, and feedback

Deliver:

- conversation/message/feedback models and migrations;
- server-rendered chat page, HTMX message partials, pending/error states, and Bootstrap layout;
- text chat orchestration through the gateway;
- feedback choices: correct, incorrect, unsafe, incomplete, plus comment;
- local sanitized logs.

Acceptance:

- reviewer completes chat and feedback in the browser;
- browser network requests go only to Django;
- provider/configuration errors reveal no stack trace or secret;
- conversation and feedback records persist in SQLite.

## Milestone 3 — Controlled document ingestion and retrieval

Deliver:

- approved document register and lifecycle;
- safe PDF, DOCX, XLSX, and TXT validation/extraction as justified by actual pilot sources;
- deterministic chunking, embedding, index generation, rebuild, and removal;
- retrieval service with metadata/status filters and stable citation identifiers;
- ingestion quality/error reporting.

Acceptance:

- only approved active sources are retrievable;
- unsupported, malformed, oversized, duplicate, and traversal-style uploads fail safely;
- index rebuild from registered sources is reproducible;
- a retrieval-only baseline measures the fixed set and exposes failures for correction.

## Milestone 4 — Grounded answers and citations

Deliver:

- bounded evidence packaging;
- grounded response schema and prompt versioning;
- citation rendering linked to registered source locators;
- insufficient-evidence and out-of-scope behavior;
- persistence of retrieval/model/configuration fingerprints for evaluation.

Acceptance:

- citations correspond only to passages actually retrieved;
- no-source cases state insufficiency;
- fixed retrieval cases reach at least 85% correct document/relevant-section retrieval after documented corrections;
- prompt-injection text inside sources cannot override application safety policy.

## Milestone 5 — Guided troubleshooting and safety controls

Deliver:

- multi-turn symptom/follow-up state;
- explicit response labels for facts, observations, likely/possible causes, physical verification, checks, and escalation;
- deterministic preflight and output safety policy;
- safe refusal/escalation templates;
- comprehensive safety regression suite.

Acceptance:

- troubleshooting cases follow logical, safe sequences without false confirmation;
- missing evidence triggers questions or insufficiency;
- bypass, unsafe energization, safety circuit, guard, movement, pressure, and damage cases stop/escalate correctly;
- zero unresolved safety failures.

## Milestone 6 — Image and screenshot workflow

Deliver:

- validated private image upload, normalization, limits, and cleanup;
- server-side vision adapter and structured observation result;
- grounding of visible alarm text/observations against approved sources;
- visible limitations and controlled unavailable/error behavior.

Acceptance:

- browser never contacts Ollama;
- spoofed, malformed, oversized, and excessive-dimension files fail safely;
- when hardware supports vision, fixed clear/unclear cases describe visible evidence and never confirm hidden faults;
- when an owner-approved hardware deferral applies, upload validation and truthful unavailable behavior pass and the limitation is recorded.

## Milestone 7 — Formal evaluation, correction, and release candidate

Deliver:

- run fixed technical, retrieval, troubleshooting, image, safety, provider, and usability tests;
- record actual answers, sources, scores, issues, corrections, and retests;
- regression-test after controlled single-variable changes;
- freeze/tag the formal local test candidate;
- complete installation, index rebuild, demonstration, results, and limitations documentation.

Acceptance:

- retrieval ≥85%;
- reviewer-acceptable technical usefulness ≥80%;
- zero unresolved safety failures;
- scope boundary and uncertainty behavior pass;
- reviewer operates the prototype without development tools;
- clean documented installation and index rebuild succeed;
- supervisor records the Plan A go/no-go outcome.

## Risks and mitigations

| Risk | Mitigation / decision gate |
|---|---|
| Existing PC cannot run useful local models | Inventory first; select smaller quantized text model; constrain context; record latency/quality |
| Local vision is impractical | Time-box feasibility; apply OQ-003; never use a paid fallback in Plan A |
| Insufficient/outdated source material | Do not ingest until reviewed; narrow subject; block quality claims |
| No qualified safety reviewer | Restrict to training demonstration; do not approve operational troubleshooting |
| Parser/vector dependency incompatibility on Windows | Prove representative files and rebuild in Milestone 1; supersede ADR if needed |
| Poor retrieval from drawings/scans | Flag unreadable sources; do not claim OCR/drawing understanding; curate text references |
| Hallucinated or unsafe guidance | Grounded schema, deterministic safety layers, citations, fixed regression tests, fail closed |
| Confidential data leakage | Local-only data, private paths, sanitized logs, no public CDN/cloud/API |
| Single-developer schedule pressure | One active milestone, narrow pilot, small releases, written deferrals |

## Progress log

- 2026-07-28: Plan created from source draft v1.1 and approved owner constraints. No application code or dependencies created.
- 2026-07-28: Owner authorized a narrowed Milestone 1 foundation: Django setup, authentication, empty chat UI, conversation/message persistence, provider/retriever protocols, safety boundary, and tests. Ollama, RAG, image analysis, cloud APIs, and the earlier technical spikes are explicitly deferred.
- 2026-07-28: Narrowed Milestone 1 completed. Django 5.2 LTS foundation, six requested apps, local assets, SQLite migrations, authentication, empty protected chat page, models/admin, placeholder protocols, structured logging, error templates, setup documentation, and automated tests are in place.
- 2026-07-29: Owner authorized Milestone 2 as local text-gateway integration only. Implemented the provider-neutral text gateway, loopback-only Ollama adapter, environment controls, health command, HTMX message workflow, persistence metadata, manufacturing prompt, deterministic safety checks, normalized failures, and mocked tests. RAG, documents, embeddings, images, cloud providers, and feedback remain deferred.
- 2026-07-29: Owner authorized Milestone 3 as the document-management and
  ingestion foundation only. Implemented approval-controlled source/version
  records, format validation and checksums, PDF/DOCX/TXT/Markdown extraction,
  conservative cleaning, structure-aware chunks, staff preview/review,
  ingestion commands, and future indexing protocols. No embedding, vector
  store, retrieval, OCR, or chatbot grounding was introduced.
- 2026-07-30: Document review was paused for a Milestone 3 correction
  increment. Added a staff-only, preview-first split workflow, immutable source
  preservation, correction children, audit recipes, safety-boundary
  confirmation, retrieval fail-closed controls, and hash-gated correction
  reapplication. Chunk merging, embeddings, vector search, and RAG remain
  deferred.
- 2026-07-30: Extended Milestone 3 with controlled bulk chunk review. Added
  XLSX/CSV/JSON export, neutral row validation, digest-bound dry runs,
  staff-attributed atomic apply, metadata correction audits, and delegation of
  split rows to the existing split service. Direct database editing and
  automatic AI review decisions remain prohibited.
- 2026-07-31: Added a minimal controlled correction-child replacement layer.
  Original children remain auditable and superseded; deterministic replacement
  children, reviewer audits, source-hash validation, and fail-closed
  reprocessing are implemented. Direct content editing remains prohibited.
- 2026-07-31: Accepted the terminal LF on replacement
  `CHK-R-dc0bd8a616b4bf71705f8eb93f535f` as non-substantive using `rstrip()`-style
  ending validation. Recorded that correction recipes remain local-database
  state and require a future versioned reconstruction mechanism for portability.

## Completion evidence

- `manage.py makemigrations --check --dry-run`: no changes detected.
- `manage.py migrate --noinput`: all migrations applied.
- `manage.py check`: no issues.
- `pytest`: 9 passed.
- Ruff lint and format checks: passed.
- mypy: passed with no issues in 48 source files.
- Bandit: passed with no reported findings.
- Local development-server smoke test: HTTP 200 and expected home-page marker.
- Milestone 2 local text gateway: 42 mocked/unit/integration tests passed; Django checks, migration checks, Ruff, mypy, Bandit, and a real local Ollama health check also passed.
- Milestone 3 split-correction increment: 71 automated tests passed; migration
  `knowledge_base.0002` applied; Django checks, migration consistency, Ruff,
  mypy, and Bandit passed.
- Milestone 3 bulk-review increment: 83 automated tests passed; migration
  `knowledge_base.0003` applied; a real 71-row FANUC XLSX export and no-change
  dry-run passed; Django checks, migration consistency, Ruff, mypy, and Bandit
  passed.
- Milestone 3 correction-child replacement increment: 105 automated tests
  passed; migration `knowledge_base.0004` applied; Django checks, migration
  consistency, Ruff, mypy, and Bandit passed.
- Retrieval, embeddings, image analysis, cloud providers, and industrial
  integrations remain unimplemented.
