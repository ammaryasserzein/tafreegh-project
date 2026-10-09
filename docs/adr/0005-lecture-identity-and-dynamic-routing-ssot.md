# 0005. Lecture Identity and Dynamic Routing Single Source of Truth

Status: Accepted

## Context

Prior iterations of the transcription pipeline accumulated architectural friction across two primary dimensions:

1. **Data Clumps & Shotgun Surgery**: Multiple decoupled primitives (`date`, `keyword`, `subject_name`, `stem`, `lecture_number`, `audio_file`) were repeatedly passed together through function signatures in `export_docx.py` and `fetch_training_data.py`. Any addition or adjustment to identity attributes necessitated shotgun surgery across multiple call sites and scripts.
2. **Hardcoded Routing Duplication**: `export_docx.py` hardcoded a large `CANONICAL_SUBJECT_NAMES` dictionary, violating `CODING_STANDARDS.md` § 3 which mandates that `CONTEXT.md` serves as the sole authoritative source of truth for high-level domain routing.
3. **Word Export Formatting Inconsistency**: `create_docx()` manually injected empty paragraphs (`doc.add_paragraph()`) before and after standalone Matn passages, generating double paragraph gaps (`^p^p`) in Word documents despite prompt engineering rules enforcing single newlines (`\n`) for single-gap navigation.

## Decision

1. **LectureIdentity Domain Entity**:
   - Introduced `LectureIdentity` in `lecture_identity.py` to bundle all lecture identity primitives into a cohesive, domain-driven structure.
   - Encapsulated core behaviors directly onto the entity:
     - `header_line_3`: Deterministic resolution of Header Line 3 across date-based, numbered, and fallback lectures.
     - `resolved_stem`: Deterministic canonical stem generation.
     - `matches()`: Encapsulated cross-directory stem matching (exact stem, date-based, and mirrored numbered stems).
     - `merge()`: Functional composition of partial identities across transcript headers and file paths.
   - Maintained full mapping / dict subscripting compatibility (`ident["date"]`, `ident.get()`, `items()`) to preserve non-breaking interoperability with legacy interfaces.

2. **Dynamic Routing Map from CONTEXT.md**:
   - Implemented `load_canonical_routing()` to parse Section 3 (`## 3. توجيه المتون (Routing Map)`) of `CONTEXT.md` dynamically at runtime.
   - `export_docx.py` and `lecture_identity.py` now reference `CONTEXT.md` directly as the authoritative single source of truth, eliminating hardcoded subject mappings and allowing new courses to be registered strictly by editing `CONTEXT.md`.

3. **Elimination of Matn Double Gaps**:
   - Deleted manual `p_before` and `p_after` empty paragraph injections in `create_docx()`.
   - Standalone Matn passages are rendered as a single Word paragraph (`^p`), perfectly synchronizing the Python Word export pipeline with prompt rules.

4. **Integration into Training Data Pipeline**:
   - Refactored `fetch_training_data.py` to utilize `LectureIdentity.from_filename()` and `_find_ai_baseline()`, unifying baseline discovery for both date-stamped and numbered lectures.

## Consequences

- Full alignment between prompt specifications and Python export output (clean single-gap Matn paragraphs in Word).
- Zero duplication between domain steering documents and executable Python routing tables.
- Drastic reduction of parameter bloat and elimination of data clumps across export and training scripts.
- High testability: All identity logic and dynamic parsing are independently unit-tested with 100% test pass rate.
