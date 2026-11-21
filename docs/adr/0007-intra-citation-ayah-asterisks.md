# Intra-Citation Ayah Asterisks

Continuous recitations of consecutive Quranic verses are formatted inside a single parenthesized citation separated by a spaced asterisk `(آية * آية)`, and `verify_docx.py` permits literal `*` exclusively when spaced inside parentheses between vowelized Arabic clauses while keeping `FORBIDDEN_CHAR_ASTERISK` active everywhere else.

Blanket asterisk rejection previously blocked Mushaf-style multi-ayah separators, whereas relaxing `*` globally or allowing unspaced `*` would re-open Markdown bold/italic leakage (`**`) and unvowelized poetry hemistich asterisks `(شطر أول * شطر ثاني)`.

## Amendment (2026-11-21)

The spaced vowelized `*` exemption extends symmetrically to ornate Mushaf brackets ﴿آية * آية﴾ alongside `(آية * آية)` (`_QURAN_ASTERISK_CONTAINER_RE` in `_qa_headers_conclusion.py`), preserving `FORBIDDEN_CHAR_ASTERISK` enforcement for unspaced asterisks, double asterisks (`**`), and unvowelized or bare prose occurrences.
