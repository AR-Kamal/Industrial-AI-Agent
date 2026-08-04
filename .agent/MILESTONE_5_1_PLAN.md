# Add Gemini without changing grounded retrieval

Status: Complete
Owner: single developer
Last updated: 2026-08-03

## Purpose

Extend the Milestone 5 provider-neutral gateway with a stateless Google Gemini
generation option and comparable usage diagnostics while preserving grounded
retrieval, citations, and safety behavior.

## Scope and non-goals

In scope: official `google-genai` Interactions adapter, explicit provider
selection, safe error mapping, usage reporting, tests, commands, and docs.
Out of scope: Milestone 6, vision, tools/web grounding, retrieval/index changes,
automatic fallback, provider selection, and committing runtime reports.

## Relevant requirements and decisions

This plan follows `PROJECT_SPEC.md`, `docs/architecture.md`, repository safety
rules, and the Gemini provider decision recorded in `docs/decisions.md`.

## Current repository state

Milestone 5 is merged. Preflight found a clean `main`, created
`feature/milestone-5-1-gemini-provider`, confirmed 101/101 healthy vectors,
20 approved cases, applied migrations, and a 189-test passing baseline.

## Milestones

### M1 — Provider boundary supports Gemini

- Work: add dependency, configuration, adapter, factory selection, error mapping.
- Acceptance: mocked Interactions requests are stateless, structured, tool-free,
  omit deprecated sampling settings, and clean up resources.
- Validation: targeted provider tests and lint.
- Recovery: remove the explicit Gemini factory branch; Ollama remains unchanged.

### M2 — Diagnostics and evaluation remain provider-neutral

- Work: propagate optional token usage into answer and evaluation diagnostics.
- Acceptance: missing usage does not fail answers; retries and latency remain
  application-controlled and comparable.
- Validation: grounded-service and evaluator regression tests.
- Recovery: optional fields can be removed without data migration.

### M3 — Documentation and full validation

- Work: document selection, privacy, live commands, and comparison review.
- Acceptance: complete automated quality suite passes; no migration or index
  mutation; live calls run only when a user-supplied key exists.
- Validation: Django checks, complete pytest, Ruff, mypy, Bandit, diff check.
- Recovery: all changes are ordinary uncommitted source edits.

## Risks and mitigations

- Cloud disclosure: send only the current grounded prompt/evidence; `store=False`;
  no files, tools, hashes, vector IDs, or interaction persistence.
- Provider retries: configure one SDK attempt; retain exactly one explicit
  application structured-output retry.
- Model quality: do not select a permanent provider from structural metrics;
  require human review.
- Secrets: environment-only key and empty example placeholder.

## Decisions and discoveries

- The installed SDK supports `client.interactions.create`, `response_format`,
  `store=False`, deterministic `close()`, usage fields, and retry attempts.
- Gemini accepts a conservative schema subset; semantic rules stay in the
  existing application validator.

## Progress log

- 2026-08-03: Preflight and 189-test baseline passed; index and cases healthy.
- 2026-08-03: Added official SDK, adapter, explicit selection, token diagnostics,
  and initial mocked tests; targeted regression tests passed.

## Completion evidence

Automated completion on 2026-08-03: Django check and migration dry-run passed;
204 tests passed; Ruff lint and formatting, mypy, Bandit, and diff checks passed.
The approved-case dry run reported 20 approved and zero pending/invalid/skipped.
Live provider and A/B evaluation remain a manual human-review step because no
user-provided `GEMINI_API_KEY` was present.
