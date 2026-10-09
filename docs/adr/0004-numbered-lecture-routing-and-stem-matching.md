# 0004. Numbered Lecture Routing and Stem Matching

Status: Accepted

## Context

The initial transcription architecture assumed that all lectures carry a Gregorian date (`YYYY-MM-DD`) in their filename and header block (Header Line 3). File isolation, matn source matching, and atomic archiving depended entirely on the `(date, keyword)` tuple.

Certain courses, such as **فقه البيوع (سعد الخثلان)**, are recorded and distributed with sequential lecture numbers rather than recording dates. Their raw audio and transcript files adhere to a mirrored numbered stem pattern: `[N]-فقه_البيوع_[N]` (e.g. `17-فقه_البيوع_17.md`).

To support this course without breaking backwards compatibility with existing date-based courses (Zad, Seerah, Riyadh, etc.), the pipeline must dynamically recognize both date-based and numbered lecture stems across header generation, metadata extraction, matn alignment, export, and atomic archiving.

## Decision

1. **Routing and Subject Mappings**:
   - Added keyword tokens: `بيوع`, `البيوع`, `فقه البيوع`, `فقه_البيوع`, `خثلان` mapping to canonical subject name `فقه البيوع (سعد الخثلان)`.
   - OneDrive course folder resolved to `C:\Users\L\OneDrive\1. دوري\فقه البيوع (سعد الخثلان)`.

2. **Metadata and Dynamic Header Line 3**:
   - `parse_metadata()` extended to extract `lecture_number` from mirrored stem patterns (e.g., `(\d+)[-_]([^\s]+?)[-_](\d+)`) and explicit lecture labels (e.g., `المحاضرة: \d+`).
   - When a `YYYY-MM-DD` date is absent, `standardize_transcript_header()` and `create_docx()` format Header Line 3 dynamically as `المحاضرة: {lecture_number}` instead of a date.

3. **Dual-Mode Stem Matching and Archiving**:
   - `is_matching_stem()` refactored to support both date matching and mirrored numbered stem matching.
   - For numbered lectures without dates, matching validates mirrored lecture numbers and subject keyword variants across `01_Matn_Sources/` and `02_Raw_Inputs/`.
   - `archive_processed_inputs()` and `find_matching_matn_source()` accept `stem` and `lecture_number` parameters to atomically archive consumed numbered files to `processed/` subdirectories.

4. **Deterministic Export Naming**:
   - In `export_documents()`, when a date is absent, the exported OneDrive document is named `{input_stem}.docx` (e.g., `17-فقه_البيوع_17.docx`), and the project baseline is named `{input_stem}_AI.md` (e.g., `17-فقه_البيوع_17_AI.md`).

## Consequences

- Full interoperability between date-stamped lectures and numbered curriculum courses without branching or code duplication.
- Multi-tab isolation and collision protection (ADR 0002) are preserved for numbered lectures via specific mirrored number matching.
- Downstream Diff Loop and training data scripts seamlessly trace numbered baselines in `03_AI_Outputs/`.
