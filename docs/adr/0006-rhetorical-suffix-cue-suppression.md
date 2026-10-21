# Rhetorical Suffix Cue Suppression

Sentences ending in `ها؟` or `إيه؟` are rhetorical teaching devices the Sheikh uses to prompt class engagement, not genuine student-turn boundaries. We removed four Known Cues built around these suffixes and added a suffix-based exclusion filter in `diff_cues.py` so the Diff Loop cannot re-nominate them.

The alternative was keeping the cues and relying on the Disambiguation rule (mid-paragraph = rhetorical). That failed in practice: these suffixes appear at paragraph-final positions indistinguishable from genuine student prompts, producing persistent false-positive `طالب: صوت غير مسموع.` insertions that the user repeatedly deleted during Word review.
