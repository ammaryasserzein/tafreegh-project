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


from dataclasses import dataclass

@dataclass
class CueResult:
    inserted: list[CueCandidate]
    removed: list[CueCandidate]

def _collect_cues(
    normalized_lines: list[str], raw_text: str, start_idx: int, end_idx: int
) -> list[CueCandidate]:
    """Helper to collect cues from a range of normalized lines."""
    candidates = []
    for idx in range(start_idx, end_idx):
        line = normalized_lines[idx]
        if _is_full_inaudible_student_line(line):
            cue = _find_preceding_sentence(normalized_lines, idx)
            if cue:
                raw_lines = raw_text.splitlines()
                line_number = 0
                normalized_count = 0
                for raw_idx, raw_line in enumerate(raw_lines):
                    if raw_line.strip():
                        if normalized_count == idx:
                            line_number = raw_idx + 1
                            break
                        normalized_count += 1
                candidates.append(CueCandidate(
                    cue_sentence=cue, student_line=line, line_number=line_number
                ))
    return candidates

def detect_new_student_cues(
    ai_text: str, corrected_text: str
) -> CueResult:
    """Detect user-inserted and user-removed 'طالب: صوت غير مسموع.' lines.

    Args:
        ai_text: The AI-generated markdown baseline.
        corrected_text: The user-corrected markdown from Word review.

    Returns:
        CueResult containing inserted and removed candidates.
    """
    ai_lines = _normalize_lines(ai_text)
    corrected_lines = _normalize_lines(corrected_text)

    matcher = SequenceMatcher(None, ai_lines, corrected_lines)
    inserted_candidates: list[CueCandidate] = []
    removed_candidates: list[CueCandidate] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            inserted_candidates.extend(_collect_cues(corrected_lines, corrected_text, j1, j2))
        
        if tag in ("delete", "replace"):
            removed_candidates.extend(_collect_cues(ai_lines, ai_text, i1, i2))

    return CueResult(inserted=inserted_candidates, removed=removed_candidates)

def _format_section(title: str, cues: list[CueCandidate], file_label: str, hint: str) -> list[str]:
    lines = [title, "=" * 60]
    for i, c in enumerate(cues, 1):
        lines.append(f"  {i}. عبارة الشيخ السابقة: \"{c['cue_sentence']}\"")
        lines.append(f"     (سطر {c['line_number']} في {file_label})")
        lines.append("")
    lines.append(hint)
    lines.append("")
    return lines

def format_cue_report(result: CueResult) -> str:
    """Format candidate cues as a human-readable report for the learning summary."""
    if not result.inserted and not result.removed:
        return ""

    lines = []
    if result.inserted:
        lines.extend(_format_section(
            "📋 مرشحات تنبيهات محادثة جديدة (تتطلب تأكيد المستخدم):",
            result.inserted,
            "الملف المصحح",
            "💡 لإضافة تنبيه جديد إلى القائمة المعتمدة في SKILL.md، يرجى تأكيد العبارات أعلاه."
        ))
        
    if result.removed:
        lines.extend(_format_section(
            "❌ تنبيهات محذوفة من قبل المستخدم (False Positives):",
            result.removed,
            "ملف الذكاء الاصطناعي",
            "💡 يرجى مراجعة هذه الحالات لتحسين فهم النظام للأسئلة البلاغية (Rhetorical vs Genuine)."
        ))
        
    return "\n".join(lines).strip()


if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    if len(sys.argv) < 3:
        print("Usage: py diff_cues.py <ai_file> <user_file>")
        sys.exit(1)
        
    ai_text = Path(sys.argv[1]).read_text(encoding="utf-8")
    user_text = Path(sys.argv[2]).read_text(encoding="utf-8")
    
    result = detect_new_student_cues(ai_text, user_text)
    report = format_cue_report(result)
    if report:
        print(report)
