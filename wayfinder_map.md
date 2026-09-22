## Destination

Overhaul Tafreegh Skill: Advanced Formatting & Extraction Rules

## Notes

- **Domain**: Automated transcription formatting, plain-text extraction from Word (`.docx`), Diff Loop automation.
- **Rules**: Preserve the human's exact workflow (editing in OneDrive) while translating their edits into a plain-text (`.md`) format that the AI can learn from seamlessly.

## Decisions so far

- Folder names translated to English (`01_Matn_Sources`, `02_Raw_Inputs`, `03_AI_Outputs`, `04_Training_Data`) for better AI processing.
- The Diff Loop will operate entirely on `.md` files to eliminate XML noise.
- The AI will automatically fetch finished `.docx` files from the OneDrive `(تم التسليم)` folder and dynamically determine their project name.
- **Poetry Formatting**: 
  - Both halves spoken: Separate line, spaced ` ... ` between them.
  - Interrupted: First half starts on a new line, but text continues inline normally.
  - If Matn: Formatted as `**(الشطر الأول ... الشطر الثاني)**`.

- **Paragraph Rules**:
  - Target 4-6 lines for readability, but do not break up a single coherent thought even if it's a page long (rely on Diff Loop).
  - Explicit topic changes force a new line (often triggered by the word `طيب`).
  - Rhetorical questions: If short, keep inline. If followed by a long 2-3+ line explanation, force a new line.
  - Connecting words (`ثم`, `ولذلك`) act as glue to keep the current line going.

- **Matn Formatting Extraction**: `read_docx.py` was upgraded to parse `<w:b/>` and `<w:bCs/>` (Arabic complex script) tags into Markdown `**`, flawlessly preserving bolding across whitespace boundaries.

- **Student Dialogue Merging (Proactive Known-Cue Insertion)**:
  - Known cues (`نعم؟`, `بتقول إيه؟`, `يا فلان` + pause) at end-of-thought with topic shift trigger automatic `طالب: صوت غير مسموع.` insertion.
  - Rhetorical `نعم؟` (mid-paragraph, Sheikh continues immediately) is ignored.
  - Zero Hallucination still applies for unknown situations (no cue present).
  - Diff Loop auto-proposes new cues from user Word edits, requiring confirmation before addition.

- **Punctuation & Edge Cases**:
  - Quran: AI relies on internal knowledge for Uthmani script (no external tool for now).
  - Hadith: Only verbatim/near-verbatim quotes get `" "`. Paraphrases stay unquoted. Refinable via Diff Loop.
  - Environmental sounds: Ignored entirely. Only student speech gets attribution.

## Not yet specified
- *(All items resolved — frontier empty.)*

## Out of scope
- **Poetry Formatting**: Rules for using ... between hemistichs, and when to isolate vs merge.
