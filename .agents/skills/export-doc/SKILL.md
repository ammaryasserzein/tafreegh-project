---
name: export-doc
description: Export Product-Owner Markdown PRDs/BRDs into executive Word (.docx) deliverables (English and Arabic hybrid) saved directly to OneDrive.
---

# Export Product-Owner Documents

Export any Markdown document (`.md`) from a `Product-Owner` project repository into executive-ready Microsoft Word (`.docx`) deliverables engineered for 1:1 import into Google Docs.

## Non-Negotiable Storage Rules

- **Destination (Strict)**: Output `.docx` files **ONLY** to OneDrive:
  `C:\Users\L\OneDrive\3. Product-Owner\<Project-Name>\`
- **Repo Quarantine**: **NEVER** save `.docx` files into the Git repository (`C:\Users\L\Documents\Product-Owner\`). Markdown remains the sole format in the repo to prevent token bloat and AI indexing confusion.

## Output Specifications

Every exported document produces a dual-copy pair:
1. **English Version (`<Name>-EN.docx`)**:
   - Direction: LTR.
   - Typography: Aptos / Arial, executive color palette (`#17365D`, `#1F4E78`, `#2F5597`).
   - Centered LTR `PAGE / NUMPAGES` footer without `w:updateFields=1`.
2. **Modern Executive Arabic Hybrid Version (`<Name>-AR.docx`)**:
   - Translation: Provide an accurate, high-quality translation of the main markdown body into full Arabic prose.
   - Direction: Explicit RTL base (`w:bidi=1`, logical `w:jc="start"`).
   - Typography: Strict mirroring of English typography (Aptos / Arial) and executive color palette (`#17365D`, `#1F4E78`, `#2F5597`) for identical layout fidelity.
   - Embedded Terms: English code, URLs, and terms wrapped in directional LTR spans (`w:rtl=0`).
   - Bilingual Glossary Table: Placed immediately after the title block with exactly two columns:
     `المصطلح العربي | English System Term`
   - Visual Table Direction: Explicit `w:bidiVisual=1`.

## Pipeline Execution

### Setup Variables
```powershell
$SCRIPTS = "C:/Users/L/.gemini/config/skills/arabic-word-production/scripts"
$OUT_DIR = "C:/Users/L/OneDrive/3. Product-Owner/<Project-Name>"
$TEMP_DIR = [System.IO.Path]::GetTempPath()
```

### Fast Path (Deterministic Build & Audit)

1. **Verify Environment**:
   ```powershell
   py -3 "$SCRIPTS/check_environment.py"
   ```

2. **Construct JSON Document Model**:
   Model must satisfy `validate_model()` in `$SCRIPTS/doc_model.py`.
   - **Crucial Rule:** Save the generated JSON models ONLY to `$TEMP_DIR` or memory, never to the local repository.
   - Required root keys: `title` (string), `blocks` (list).
   - Supported block types: `heading` (level 1 or 2), `paragraph`, `list`, `table`, `callout` (`note` or `warning`), `page_break`, `image`.

3. **Compile and Audit Documents (Batch Process)**:
   ```powershell
   $DOC_NAMES = @("BRD-Name", "PRD-Name") # Replace with actual document base names
   foreach ($doc in $DOC_NAMES) {
       foreach ($lang in @("EN", "AR")) {
           $model = "$TEMP_DIR/${doc}-${lang}.json"
           $target = "$OUT_DIR/${doc}-${lang}.docx"
           py -3 "$SCRIPTS/build_docx.py" $model $target
           py -3 "$SCRIPTS/audit_docx.py" $target
       }
   }
   ```

### Completion Criteria

A build is complete **only** when:
- Both files exist in `C:\Users\L\OneDrive\3. Product-Owner\<Project-Name>\`.
- `audit_docx.py` returns `"passed": true` with zero findings for both files.
- Zero `.docx` or binary artifacts were committed or written to `C:\Users\L\Documents\Product-Owner\`.
