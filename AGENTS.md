# Repository Instructions

## Source of truth

Read `PROJECT_SPEC.md`, `docs/architecture.md`, `docs/decisions.md`, and the active execution plan before changing the project. The original DOCX is background evidence; `PROJECT_SPEC.md` is the implementation baseline. Record scope or architecture changes in `docs/decisions.md`.

## Non-negotiable scope

- Build a standalone technical-support and training chatbot only.
- Do not add PLC, HMI, sensor, machine, Node-RED, OPC UA, SCADA, MES, CMMS, production database, or other industrial integrations.
- Do not add control commands, live diagnosis, predictive maintenance, or automated physical actions.
- Use Django, Django Templates, HTMX, Bootstrap, SQLite, local vector storage, and Ollama for Plan A.
- Keep every model call server-side behind `ai_gateway`; the browser never calls a model provider.
- Keep text, vision, and embedding interfaces and configuration separate.
- Do not add paid services or production deployment work to prototype milestones.

## Safety and security

- Never generate instructions that bypass or defeat emergency stops, guards, interlocks, safety relays, lockout/tagout, or other safety systems.
- Responses must label confirmed facts, observations, likely causes, possibilities, and physical-verification items.
- Fail closed on unsafe output or insufficient evidence and escalate hazardous cases to qualified personnel.
- Treat model output and uploaded content as untrusted.
- Validate uploads by detected type, size, dimensions, and parser behavior; generate storage names and prevent traversal.
- Keep confidential documents local. Never commit secrets, model files, source documents, uploads, indexes, databases, or logs.
- Do not expose provider errors, stack traces, prompts, environment values, or filesystem paths to browser users.

## Coding conventions

- Target the supported Python version recorded in the dependency lock/constraints file.
- Follow PEP 8; use type hints on service boundaries and docstrings for public interfaces or non-obvious safety logic.
- Keep views thin. Business logic belongs in services; provider-specific code belongs only in adapters.
- Prefer explicit Django forms, model validation, database constraints, and small pure functions.
- Keep templates presentation-focused. Use HTMX for progressive enhancement and return HTML partials from Django.
- Use timezone-aware datetimes, structured logging, deterministic test fixtures, and stable citation identifiers.
- Never couple generated vector indexes to migrations or commit them to Git.

## Tests and quality gates

- Add or update tests with every behavior change.
- Run formatting, linting, type checks, Django system checks, migrations checks, unit tests, and applicable integration/regression tests before handoff.
- Mock provider calls in routine automated tests. Keep opt-in local Ollama integration tests separately marked.
- Safety regression tests are mandatory and must include bypass requests, hazardous energization, guarding, movement, pressure, and insufficient-evidence cases.
- File tests must include spoofed types, oversized files, malformed content, traversal names, and unsupported formats.
- Any unresolved safety failure blocks completion.
- Do not change prompt, model, and retrieval settings together when diagnosing quality.

## Plans and repository hygiene

- Follow `.agent/PLANS.md` for work spanning multiple files or sessions.
- Preserve user changes and avoid destructive Git operations.
- Keep commits focused and update docs, tests, decision records, and `.env.example` when behavior/configuration changes.
- Use Windows-compatible commands and paths in primary setup documentation; note portable alternatives where useful.
