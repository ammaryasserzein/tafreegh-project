# 0009. Retire Legacy CONTEXT.md into Pure-Domain Glossary and Course Routing Reference

Status: Accepted (supersedes [ADR 0005](0005-lecture-identity-and-dynamic-routing-ssot.md) Decision § 2)

## Context

Root `CONTEXT.md` accumulated two competing responsibilities: high-level domain vocabulary (now canonically owned by `GLOSSARY.md` per `AGENTS.md` and `docs/agents/domain.md`) and operational pipeline metadata (the 3-column course-routing table, lecturer scholarly disambiguation notes, and 4-folder pipeline descriptions). Over time, `CONTEXT.md` drifted into four direct contradictions against `GLOSSARY.md` and the active pipeline (`استدراك السقط` vs. **Blind Literalism**, claiming `03_AI_Outputs` stores `.docx` files when `.docx` routes exclusively to OneDrive, requiring `<matn_source>` as a mandatory preparatory gate despite **Fallback Mode**, and claiming `04_Training_Data` stores extracted diffs rather than human-reviewed transcripts).

## Decision

We retired and deleted `CONTEXT.md` and split its live concerns cleanly along domain vs. operational boundaries:

1. **Pure-Domain Vocabulary (`GLOSSARY.md`)**: Consolidated all domain terms — including **The Curriculum** (without a hardcoded course count), **Diff Loop**, **Conservative Doubt**, **Sandwiched Context**, and **Oral Citation** — into root `GLOSSARY.md`, purified of file paths, script names, Python field names, and all four contradicted legacy claims.
2. **Dedicated Course Routing SSOT (`.agents/skills/tafreegh/references/course-routing.md`)**: Relocated the complete 3-column Course Routing Map (keyword tokens, canonical subject names, and source book/author metadata) to `.agents/skills/tafreegh/references/course-routing.md`, formatted with positive phrasing and zero Arabic inside inline backticks (ADR 0003). `workspace_catalog.py` (`WorkspaceConfig.course_routing_path`, `TAFREEGH_COURSE_ROUTING_PATH`, and `RuleCatalog.load()`) now parses this file dynamically at runtime and anchors repository root discovery on `GLOSSARY.md`. This explicitly supersedes **ADR 0005 Decision § 2** (which designated `CONTEXT.md` § 3 as the dynamic routing location) while preserving ADR 0005's `LectureIdentity` entity, dynamic runtime routing, and single-gap Matn paragraphs.
3. **Lecturer & Scholarly Disambiguation Context (`.agents/skills/tafreegh/SKILL.md` § 1)**: Relocated the lecturer identity note (Sheikh Osama rarely stating his own name) and Salafi scholarly citation context (Ibn Taymiyyah and Ibn al-Qayyim) into `SKILL.md` § 1 where agents apply it directly during ASR disambiguation.
4. **Repository Guardrails (`scripts/verify_repo.py`)**: Removed `CONTEXT.md` from `ALLOWED_ROOT_FILES` (preventing re-introduction) while keeping `AGENTS.md` whitelisted, added `references/course-routing.md` to `STEERING_DOCS` and `SKILL_DOCS`, and migrated integrity validation to `check_course_routing_integrity()` enforcing 3-column table syntax, escaped pipes, and standard folder references.

## Considered Options

- **Embedding the course-routing table inside `GLOSSARY.md`**: Rejected because `GLOSSARY.md` is strictly pure domain language (`GLOSSARY-FORMAT.md`); embedding a runtime-parsed markdown table and delivery routing config would violate domain purity and re-create the exact mixed-concern sediment `CONTEXT.md` suffered from.
- **Keeping `CONTEXT.md` as a routing-only file at repo root**: Rejected because it left a confusing legacy root file alongside `GLOSSARY.md` and `AGENTS.md` and kept operational skill routing outside `.agents/skills/tafreegh/references/`, where sibling `dialect-rules.md` and `formatting-rules.md` already live.

## Consequences

- `GLOSSARY.md` is the sole pure-domain vocabulary source, enforced by `tests/test_verify_repo.py::test_glossary_domain_language_purity`.
- `.agents/skills/tafreegh/references/course-routing.md` sits alongside `dialect-rules.md` and `formatting-rules.md` and is automatically governed by ADR 0003 (zero Arabic inside inline backticks), positive-phrasing checks, hardcoded-path checks, and 3-column table parity checks in `scripts/verify_repo.py`.
- Re-creating `CONTEXT.md` at the repository root fails `py scripts/verify_repo.py` as a retired root file.
- `verify_docx.py` introduces `--routing` as its primary CLI flag while retaining `--context` as a backwards-compatible alias so existing CLI invocations remain unbroken.
