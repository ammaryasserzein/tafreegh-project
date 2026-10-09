# Coding & Review Standards

## 1. Scope & Blast Radius

- **Strict Scope Boundary**: Edits must modify exclusively the files declared in the task prompt.

## 2. Verifiable Completion Criteria

- **Deterministic Verification**: Every completion criterion and milestone boundary must be an observable check: a file's existence in a specific directory or an automated command exiting with code 0.

## 3. Single Source of Truth

- **Domain vs. Mechanics**: `CONTEXT.md` maintains high-level domain terminology, routing tables, and lean pointers. Operational mechanics belong strictly in designated skill files (e.g. `.agents/skills/tafreegh/SKILL.md`).
- **Single Definition**: State flags, options, and heuristics in their authoritative file. Ancillary documents point to that single definition.

## 4. Scratch & Tool Economy

- **Scratch Containment**: Store all temporary logs, diff dumps, and test outputs in `.scratch/` or `$env:TEMP`. Root-level scratch dumps require relocation before review sign-off.
- **Clean Tree**: Working tree must remain clean of untracked scratch artifacts before completing a phase.

## 5. Automated Verification

- **Pre-Review Script Execution**: Run `scripts/verify_repo.py` using the Python launcher (`py scripts/verify_repo.py`). The verification script must exit with code 0 before review sign-off.

## 6. Domain Purity & Boundary Seams

- **Model Immutability & Non-Destructive Operations**: Domain models and dataclasses maintain pure state operations. Methods such as `merge()` preserve unspecified fields from the target instance without destructive nullification.
- **Seam Separation**: Presentation, formatting precedence, and document layout heuristics reside strictly in export and resolution seams (such as `resolve_document_identity()`), keeping core domain entities decoupled from delivery mechanics.
