# Execution Plan Standard

Use an execution plan for any milestone, cross-cutting change, risky change, or task likely to span more than one work session. Small isolated documentation or typo fixes do not need a separate plan.

## Required qualities

Plans are living, self-contained documents for a single developer. A reader with only the repository and the plan must understand the goal, constraints, current state, next action, validation method, and recovery path.

Each plan must:

- cite the applicable `PROJECT_SPEC.md` requirements and architecture decisions;
- state what is in scope and explicitly out of scope;
- use observable acceptance criteria;
- split work into small, ordered milestones that leave the repository runnable;
- identify safety, security, privacy, data-loss, hardware, and model-quality risks;
- distinguish automated checks from manual/reviewer checks;
- avoid paid services and production deployment during Plan A;
- record assumptions rather than silently expanding scope.

## Required structure

```markdown
# <Outcome-oriented title>

Status: Proposed | Active | Blocked | Complete
Owner: single developer
Last updated: YYYY-MM-DD

## Purpose
## Scope and non-goals
## Relevant requirements and decisions
## Current repository state
## Milestones
### M1 — <observable result>
- Work
- Acceptance
- Validation commands/manual checks
- Rollback or recovery
## Risks and mitigations
## Decisions and discoveries
## Progress log
## Completion evidence
```

## Maintenance rules

1. Mark exactly one milestone active at a time.
2. Update the plan before materially changing its scope or sequence.
3. Add dated progress entries after meaningful work, including failed approaches and unexpected findings.
4. Record decisions in `docs/decisions.md`; link them from the plan instead of duplicating rationale.
5. Put owner-blocking choices in `docs/open_questions.md`. Continue independent work where safe.
6. Include exact validation commands once tooling exists. Never claim a check passed without running it.
7. If a milestone is incomplete, state precisely what remains and why.
8. On completion, summarize evidence, known limitations, deferred work, and any follow-up plan.

Plans must not become informal wish lists. Every milestone needs a concrete artifact and a pass/fail test.
