# Intra-Citation Ayah Asterisks

Continuous recitations of consecutive Quranic verses are formatted inside a single parenthesized citation separated by a spaced asterisk `(آية * آية)`, and `verify_docx.py` permits literal `*` exclusively when spaced inside parentheses between vowelized Arabic clauses while keeping `FORBIDDEN_CHAR_ASTERISK` active everywhere else.

Blanket asterisk rejection previously blocked Mushaf-style multi-ayah separators, whereas relaxing `*` globally or allowing unspaced `*` would re-open Markdown bold/italic leakage (`**`) and unvowelized poetry hemistich asterisks `(شطر أول * شطر ثاني)`.
