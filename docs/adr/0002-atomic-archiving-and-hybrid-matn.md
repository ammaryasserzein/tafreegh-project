# 0002. Atomic Archiving and Dynamic Fallback Interleaving for Matn Matching

Status: Accepted

## Atomic Archiving

After a lecture is successfully exported (OneDrive `.docx` + `03_AI_Outputs/_AI.md` both confirmed written), the consumed input files are moved into `processed/` subdirectories within their respective folders. Both `01_Matn_Sources/processed/` and `02_Raw_Inputs/processed/` receive files, since matn sources are lecture-specific extractions (not canonical book-level files shared across lectures).

The move is stem-specific: only the raw input and matn source matching the exported lecture's `(date, keyword)` tuple are moved. Files are matched by normalizing filenames to `(date, keyword)` tuples, ignoring delimiter style (spaces, underscores), extension quirks (`.md.md`), and suffixes (`_AI`, `_processed`). This isolation prevents multi-tab collisions where parallel sessions could interfere with each other's files.

Chunk subdirectories (`_مقاطع/`) created by `chunk_transcript.py` are deleted during archiving — they are deterministically reproducible from the parent file.

`03_AI_Outputs/` remains flat with no archiving. AI baselines are lightweight `.md` files that serve as a permanent audit trail and diff-loop reference.

### Considered Options

- **`completed/`** as the folder name: rejected because files aren't truly "completed" at move time — the diff loop still references `03_AI_Outputs`. "Processed" accurately describes that the pipeline consumed the input.
- **Archiving only `02_Raw_Inputs/`**: rejected because matn source files are also lecture-specific consumable inputs, not permanent reference material.
- **Separate `scripts/archive.py` module**: rejected because archiving is tightly coupled to the export step. Adding it as `archive_processed_inputs()` within `export_docx.py` keeps the pipeline cohesive.

## Dynamic Fallback Interleaving (Hybrid Matn)

When a `<matn_source>` file is provided but is incomplete (missing paragraphs the sheikh reads), the system dynamically switches between Primary Mode (Blind Literalism with full tashkeel from source) and Fallback Mode (linguistic boundary detection without tashkeel) on a per-segment basis.

Matching uses a sequential cursor that tracks position in the matn source file. On each read segment:

1. **Forward search**: cursor → cursor + generous look-ahead (~2000 chars) to handle paragraph skips.
2. **On forward miss**: search the **entire previously-read range** (position 0 → cursor). This handles the common pattern where the sheikh reads a full matn block, then backs up and re-reads it sentence by sentence with interleaved explanations.
3. **On both miss**: declare Fallback Mode for this segment.

The Conservative Doubt Rule is context-dependent in hybrid mode: relaxed when the unmatched segment is sandwiched between two verified matches from the same matn source (strong positional evidence it's from the same book), strict otherwise (the sheikh may be quoting a hadith or Quran mid-explanation).

Fallback segments are marked with `<!-- fallback -->` HTML comments in the `.md` intermediate but rendered identically to primary-mode matn in the Word output. A summary block listing all fallback segments with approximate positions is emitted at the end of processing.

### Consequences

- The diff loop classifies corrections to fallback segments separately as `fallback_correction` in training data, distinguishing them from matn copy errors (which indicate matching bugs). This preserves training signal fidelity.
- `verify_repo.py` must recognize `processed/` as a valid subdirectory under `01_Matn_Sources/` and `02_Raw_Inputs/`.
