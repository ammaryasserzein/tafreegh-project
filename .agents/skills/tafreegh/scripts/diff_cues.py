"""Detect new student cue candidates by diffing AI output against user-corrected text.

When the user manually inserts 'طالب: صوت غير مسموع.' in their Word review,
this module detects the insertion, extracts the Sheikh's preceding sentence,
and proposes it as a candidate cue for the Known Cue List in SKILL.md.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TypedDict


class CueCandidate(TypedDict):
    """A proposed new conversational cue discovered via the Diff Loop."""
    cue_sentence: str
    student_line: str
    line_number: int


# Matches exactly 'طالب: صوت غير مسموع.' as a complete line (not partial inaudible).
_FULL_INAUDIBLE_RE = re.compile(
    r"^طالب:\s*صوت غير مسموع\.\s*$"
)

# Matches partial inaudible like 'طالب: كلمة (صوت غير مسموع).'
# These are NOT missing student turns — they're partial transcriptions.
_PARTIAL_INAUDIBLE_RE = re.compile(
    r"^طالب:.*\(صوت غير مسموع\)"
)


def _is_full_inaudible_student_line(line: str) -> bool:
    """Return True only for complete inaudible lines, not partial ones."""
    stripped = line.strip()
    if _PARTIAL_INAUDIBLE_RE.match(stripped):
        return False
    return bool(_FULL_INAUDIBLE_RE.match(stripped))


def _normalize_lines(text: str) -> list[str]:
    """Split text into non-empty lines for comparison."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _find_preceding_sentence(lines: list[str], target_index: int) -> str:
    """Find the Sheikh's sentence immediately before the target line index."""
    for i in range(target_index - 1, -1, -1):
        line = lines[i].strip()
        # Skip empty lines and other student lines
        if line and not line.startswith("طالب:"):
            return line
    return ""


def detect_new_student_cues(
    ai_text: str, corrected_text: str
) -> list[CueCandidate]:
    """Detect user-inserted 'طالب: صوت غير مسموع.' lines not present in AI output.

    Args:
        ai_text: The AI-generated markdown baseline.
        corrected_text: The user-corrected markdown from Word review.

    Returns:
        List of CueCandidate dicts, each containing the preceding Sheikh
        sentence (cue_sentence), the matched student line, and line number.
    """
    ai_lines = _normalize_lines(ai_text)
    corrected_lines = _normalize_lines(corrected_text)

    # Use SequenceMatcher to find insertions in the corrected text
    matcher = SequenceMatcher(None, ai_lines, corrected_lines)
    candidates: list[CueCandidate] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            # These are lines in corrected_text that are new/changed
            for j in range(j1, j2):
                line = corrected_lines[j]
                if _is_full_inaudible_student_line(line):
                    # Find the preceding Sheikh sentence
                    cue = _find_preceding_sentence(corrected_lines, j)
                    if cue:
                        # Calculate 1-based line number in original text
                        # by finding this line's position in the raw text
                        raw_lines = corrected_text.splitlines()
                        line_number = 0
                        normalized_count = 0
                        for raw_idx, raw_line in enumerate(raw_lines):
                            if raw_line.strip():
                                if normalized_count == j:
                                    line_number = raw_idx + 1
                                    break
                                normalized_count += 1

                        candidates.append(CueCandidate(
                            cue_sentence=cue,
                            student_line=line,
                            line_number=line_number,
                        ))

    return candidates


def format_cue_report(candidates: list[CueCandidate]) -> str:
    """Format candidate cues as a human-readable report for the learning summary."""
    if not candidates:
        return ""

    lines = ["📋 مرشحات تنبيهات محادثة جديدة (تتطلب تأكيد المستخدم):"]
    lines.append("=" * 60)

    for i, c in enumerate(candidates, 1):
        lines.append(f"  {i}. عبارة الشيخ السابقة: \"{c['cue_sentence']}\"")
        lines.append(f"     (سطر {c['line_number']} في الملف المصحح)")
        lines.append("")

    lines.append(
        "💡 لإضافة تنبيه جديد إلى القائمة المعتمدة في SKILL.md، "
        "يرجى تأكيد العبارات أعلاه."
    )
    return "\n".join(lines)
