# Compound Sharh-Matn Alignment

Continuous readings where an unvowelized commentator transition (`بقوله` / `في قوله` / `قوله`) flows directly into a canonical Matn clause are preserved as a single bold block `**(ثم بين وجه ذلك بقوله، وَذَلِكَ)**` via prefix/tail seam splitting across `matn_matcher.py` and `verify_docx.py`.

Forcing a paragraph break between a commentator's `بقوله،` lead-in and the quoted canonical token broke natural reading continuity and caused false `MATN_SOURCE_MISMATCH` failures when reviewed deliverables merged them.

## Amendment (2026-11-21)

Compound Sharh-Matn continuity extends via `COMPOUND_SHARH_SPLIT_RE` in `matn_matcher.py` to additional uninterrupted commentator and narrator transitions (`لقوله` / `قال <عالم>:` / `ثم أنشد قائلًا:`), and `_qa_matn_alignment.py` (`MatnAlignmentValidator._verify_mixed_or_long_jump()`) validates continuous merged Primary+Fallback blocks by checking vowelized Primary sub-spans against `<matn_source>` while leaving unvowelized Fallback transitions unflagged.
