# Deliver text-only grounded RAG answers

Status: Active
Owner: single developer
Last updated: 2026-08-01

## Purpose

Connect approved Milestone 4 retrieval evidence to the existing Milestone 2
text gateway and chatbot, producing validated answers and deterministic
citations without expanding into troubleshooting state or vision.

## Scope and non-goals

In scope: provider-neutral structured text generation, grounded prompting,
evidence budgeting, citations, abstention, safety/injection controls, chat UI,
compact persistence, staff diagnostics, commands, tests, and pending review
candidates. Out of scope: images, vision, OCR, industrial integration,
deployment, ingestion/index changes, new models, and Milestone 6.

## Relevant requirements and decisions

Implements `PROJECT_SPEC.md` sections 3.1, 3.4, 3.5, 4, 5, and 6; follows
ADR-022 and ADR-023 plus the gateway/retrieval flow in `Docs/architecture.md`.

## Current repository state

Milestone 4 merge `738629a` is the baseline. The active local index contains
101 eligible/validated vectors. `gemma3:4b` and `qwen3-embedding:0.6b` are
installed. The pre-change suite contained 146 passing tests.

## Milestones

### M1 — Grounded service and provider contract (Complete)

- Extend the existing gateway with structured output and model identity.
- Revalidate and budget evidence; validate model-selected labels.
- Build citations and fail-closed statuses.

### M2 — Chat, audit, commands, and review candidates (Complete)

- Persist compact answer/citation diagnostics and render safe source cards.
- Add provider health, one-shot answer, and candidate dry-run commands.
- Keep all 20 answer candidates pending human review.

### M3 — Automated and local validation (Active)

- Run Django/migration checks, full pytest, Ruff, mypy, Bandit, and diff checks.
- Check the installed generation provider without downloading a model.
- Provide exact optional live-answer commands for human review.

## Risks and mitigations

- Hallucinated provenance: citations are application-owned and label-validated.
- Prompt injection: system rules treat questions and evidence as untrusted.
- Unsafe output: deterministic input/output controls fail closed.
- Stale evidence: eligibility, source hash, and active index are revalidated.
- Confidentiality: prompts/evidence are not persisted or logged.

## Decisions and discoveries

The existing `Message` schema lacked citation and grounded-status auditability;
migration `chatbot.0003` adds compact JSON metadata without storing evidence or
hidden prompts. The existing generation gateway and retrieval service were
reused unchanged in responsibility.

## Progress log

- 2026-08-01: Preflight passed on the owner-approved canonical branch; 146
  baseline tests passed, index consistency was 101/101, and both local models
  were installed.
- 2026-08-01: Implemented grounded generation, deterministic citations,
  abstention, chat rendering, commands, migration, and 20 pending candidates.

## Completion evidence

Pending final repository-wide quality gates and optional local live generation.
