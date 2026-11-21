# Coding & Review Standards

## 1. Scope & Blast Radius

- **Strict Scope Boundary**: Edits must modify exclusively the files declared in the task prompt.

## 2. Verifiable Completion Criteria

- **Deterministic Verification**: Every completion criterion and milestone boundary must be an observable check: a file's existence in a specific directory or an automated command exiting with code 0.

## 3. Single Source of Truth

- **Domain vs. Mechanics**: `GLOSSARY.md` maintains pure domain vocabulary, `.agents/skills/tafreegh/references/course-routing.md` maintains the canonical course routing table, and operational mechanics belong strictly in designated skill files (e.g. `.agents/skills/tafreegh/SKILL.md`).
- **Single Definition**: State flags, options, and heuristics in their authoritative file. Ancillary documents point to that single definition.
- **Programmatic SSOT**: Import shared Arabic normalization, sequential Matn alignment, identity resolution, header patterns, workspace configuration, rule catalog loading, and Word OOXML styling/rendering/extraction/inspection from `.agents/skills/tafreegh/scripts/tafreegh/arabic_normalizer.py`, `.agents/skills/tafreegh/scripts/tafreegh/matn_matcher.py`, `.agents/skills/tafreegh/scripts/tafreegh/lecture_identity.py`, `.agents/skills/tafreegh/scripts/tafreegh/workspace_catalog.py`, `.agents/skills/tafreegh/scripts/tafreegh/word_gateway.py`, `.agents/skills/tafreegh/references/course-routing.md`, and `.agents/skills/tafreegh/references/dialect-rules.md` across validator, exporter, and diff scripts.

## 4. Scratch & Tool Economy

- **Scratch Containment**: Store all temporary logs, diff dumps, and test outputs in `.scratch/` or `$env:TEMP`. Root-level scratch dumps require relocation before review sign-off.
- **Clean Tree**: Working tree must remain clean of untracked scratch artifacts before completing a phase.

## 5. Automated Verification

- **Pre-Review Script Execution**: Run `scripts/verify_repo.py` using the Python launcher (`py scripts/verify_repo.py`). The verification script must exit with code 0 before review sign-off.

## 6. Domain Purity & Boundary Seams

- **Model Immutability & Non-Destructive Operations**: Domain models and dataclasses maintain pure state operations. Methods such as `merge()` preserve unspecified fields from the target instance without destructive nullification.
- **Seam Separation**: Presentation, formatting precedence, and document layout heuristics reside strictly in export and resolution seams (such as `resolve_document_identity()`), keeping core domain entities decoupled from delivery mechanics.

## 7. Deferred Review Backlog

- **Deferred Review Gate**: Before editing any file listed in `docs/agents/deferred-reviews.md`, read it and ask the user, per open item for that file: fix now, keep deferred, or drop.
