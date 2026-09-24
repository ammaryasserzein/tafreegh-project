# 0001. Automated Review Guardrails and Scope Whitelisting

## Status

Accepted

## Context

During the `CONTEXT.md` refactoring, 9 code-review rounds were consumed by recurring mechanical issues: scope creep into `tafreegh/SKILL.md`, directory path hallucinations, scratch file littering in the workspace root, and negative phrasing patterns.

## Decision

1. Establish automated, deterministic verification via `scripts/verify_repo.py` to check repository folder structure, scratch containment, markdown table formatting, and phrasing rules.
2. Codify strict scope boundaries and deterministic completion criteria in `CODING_STANDARDS.md`.

## Consequences

- Mechanical errors are caught instantly by automated scripts before code review, preventing multi-round reviewer thrashing.
- Changes touching files outside the declared task scope fail review immediately.
- Verification scripts must remain maintained and executable across environments.
