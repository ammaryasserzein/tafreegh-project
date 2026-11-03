# Compound Sharh-Matn Alignment

Continuous readings where an unvowelized commentator transition (`بقوله` / `في قوله` / `قوله`) flows directly into a canonical Matn clause are preserved as a single bold block `**(ثم بين وجه ذلك بقوله، وَذَلِكَ)**` via prefix/tail seam splitting across `matn_matcher.py` and `verify_docx.py`.

Forcing a paragraph break between a commentator's `بقوله،` lead-in and the quoted canonical token broke natural reading continuity and caused false `MATN_SOURCE_MISMATCH` failures when reviewed deliverables merged them.
