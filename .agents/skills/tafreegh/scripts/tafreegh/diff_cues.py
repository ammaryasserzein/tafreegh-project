"""Detect new student cue candidates by diffing AI output against user-corrected text.

When the user manually inserts 'طالب: صوت غير مسموع.' in their Word review,
this module detects the insertion, extracts the Sheikh's preceding sentence,
and proposes it as a candidate cue for the Known Cue List in SKILL.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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

# Rhetorical suffixes that should never be nominated as student cues.
# Sentences ending in these are teaching devices, not student prompts.
_RHETORICAL_SUFFIX_RE = re.compile(
    r"(?:ها|إيه)؟\s*$"
)


def _is_rhetorical_cue(sentence: str) -> bool:
    """Return True if the sentence ends with a known rhetorical suffix."""
    return bool(_RHETORICAL_SUFFIX_RE.search(sentence.strip()))


def _is_full_inaudible_student_line(line: str) -> bool:
    """Return True only for complete inaudible lines, not partial ones."""
    stripped = line.strip()
    if _PARTIAL_INAUDIBLE_RE.match(stripped):
        return False
    return bool(_FULL_INAUDIBLE_RE.match(stripped))


def _normalize_lines(text: str) -> list[str]:
    """Split text into non-empty lines for comparison."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_student_line(line: str) -> bool:
    """Return True if the line is attributed to a student speaker."""
    return line.strip().startswith("طالب:")


def _find_preceding_sentence(lines: list[str], target_index: int) -> str:
    """Find the Sheikh's sentence immediately before the target line index."""
    for i in range(target_index - 1, -1, -1):
        line = lines[i].strip()
        # Skip empty lines and other student lines
        if line and not _is_student_line(line):
            return line
    return ""


def _prose_similarity(ai_line: str, corr_line: str) -> tuple[float, float]:
    """Return (ratio, containment) similarity metrics between two non-student lines."""
    if not ai_line or not corr_line:
        return 0.0, 0.0
    matcher = SequenceMatcher(None, ai_line, corr_line)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    ratio = (2.0 * matched) / (len(ai_line) + len(corr_line))
    containment = matched / min(len(ai_line), len(corr_line))
    return ratio, containment


def _build_alignment_scores(
    ai_slice: list[str], corr_slice: list[str]
) -> tuple[list[bool], list[bool], list[list[float]], list[list[float]]]:
    """Compute pairwise match and split-continuation scores for a replace hunk."""
    m, n = len(ai_slice), len(corr_slice)
    ai_is_stu = [_is_student_line(line) for line in ai_slice]
    corr_is_stu = [_is_student_line(line) for line in corr_slice]
    match_score: list[list[float]] = [[0.0] * n for _ in range(m)]
    cont_score: list[list[float]] = [[0.0] * n for _ in range(m)]

    for i in range(m):
        for j in range(n):
            if ai_is_stu[i] and corr_is_stu[j]:
                ratio = SequenceMatcher(None, ai_slice[i], corr_slice[j]).ratio()
                match_score[i][j] = 1.0 + 0.5 * ratio
                continue
            if ai_is_stu[i] or corr_is_stu[j]:
                continue
            ratio, containment = _prose_similarity(ai_slice[i], corr_slice[j])
            if containment >= 0.6 or ratio >= 0.4:
                match_score[i][j] = 3.0 * max(ratio, 0.7 * containment)
                if containment >= 0.85 and len(corr_slice[j]) < len(ai_slice[i]):
                    cont_score[i][j] = 1.5 * containment

    return ai_is_stu, corr_is_stu, match_score, cont_score


def _aligned_student_indices(ai_slice: list[str], corr_slice: list[str]) -> set[int]:
    """Return local corr_slice indices whose student turns align to existing AI turns."""
    m, n = len(ai_slice), len(corr_slice)
    if m == 0 or n == 0 or not any(_is_student_line(line) for line in ai_slice):
        return set()
    if m * n > 25000:
        ai_students = [idx for idx, line in enumerate(ai_slice) if _is_student_line(line)]
        corr_students = [idx for idx, line in enumerate(corr_slice) if _is_student_line(line)]
        return set(corr_students[: len(ai_students)])

    ai_is_stu, corr_is_stu, match_score, cont_score = _build_alignment_scores(ai_slice, corr_slice)

    # dp[i][j][active]: best score aligning ai_slice[:i] with corr_slice[:j];
    # active=1 means ai_slice[i-1] was matched as a split prefix and can absorb trailing fragments.
    neg_inf = float("-inf")
    dp = [[[0.0, neg_inf] for _ in range(n + 1)] for _ in range(m + 1)]
    back: list[list[list[tuple[int, int, int, int] | None]]] = [
        [[None, None] for _ in range(n + 1)] for _ in range(m + 1)
    ]

    for i in range(m + 1):
        for j in range(n + 1):
            for active in (0, 1):
                cur = dp[i][j][active]
                if cur == neg_inf:
                    continue
                if i < m and cur > dp[i + 1][j][0]:
                    dp[i + 1][j][0] = cur
                    back[i + 1][j][0] = (i, j, active, -1)
                if j < n and cur > dp[i][j + 1][active]:
                    dp[i][j + 1][active] = cur
                    back[i][j + 1][active] = (i, j, active, -1)
                if i < m and j < n and match_score[i][j] > 0.0:
                    is_split_prefix = (not ai_is_stu[i]) and (len(corr_slice[j]) < len(ai_slice[i]))
                    next_active = 1 if is_split_prefix else 0
                    cand = cur + match_score[i][j]
                    if cand > dp[i + 1][j + 1][next_active]:
                        dp[i + 1][j + 1][next_active] = cand
                        aligned_stu = j if (ai_is_stu[i] and corr_is_stu[j]) else -1
                        back[i + 1][j + 1][next_active] = (i, j, active, aligned_stu)
                if active == 1 and i > 0 and j < n and cont_score[i - 1][j] > 0.0:
                    cand = cur + cont_score[i - 1][j]
                    if cand > dp[i][j + 1][1]:
                        dp[i][j + 1][1] = cand
                        back[i][j + 1][1] = (i, j, active, -1)

    state = 1 if dp[m][n][1] > dp[m][n][0] else 0
    aligned: set[int] = set()
    ci, cj = m, n
    while ci > 0 or cj > 0:
        prev = back[ci][cj][state]
        if prev is None:
            break
        pi, pj, pstate, stu_idx = prev
        if stu_idx >= 0:
            aligned.add(stu_idx)
        ci, cj, state = pi, pj, pstate
    return aligned


@dataclass
class CueResult:
    """Domain container for inserted and removed student cue candidates."""

    inserted: list[CueCandidate] = field(default_factory=list)
    removed: list[CueCandidate] = field(default_factory=list)

def _collect_cues(
    normalized_lines: list[str],
    raw_text: str,
    start_idx: int,
    end_idx: int,
    skip_indices: set[int] | None = None,
) -> list[CueCandidate]:
    """Helper to collect cues from a range of normalized lines."""
    candidates = []
    for idx in range(start_idx, end_idx):
        if skip_indices and idx in skip_indices:
            continue
        line = normalized_lines[idx]
        if _is_full_inaudible_student_line(line):
            cue = _find_preceding_sentence(normalized_lines, idx)
            if cue and not _is_rhetorical_cue(cue):
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
        if tag == "insert":
            inserted_candidates.extend(_collect_cues(corrected_lines, corrected_text, j1, j2))
        elif tag == "replace":
            aligned_local = _aligned_student_indices(ai_lines[i1:i2], corrected_lines[j1:j2])
            skip_global = {j1 + local_idx for local_idx in aligned_local}
            inserted_candidates.extend(
                _collect_cues(corrected_lines, corrected_text, j1, j2, skip_indices=skip_global)
            )

        if tag in ("delete", "replace"):
            removed_candidates.extend(_collect_cues(ai_lines, ai_text, i1, i2))

    return CueResult(inserted=inserted_candidates, removed=removed_candidates)

def _format_section(title: str, cues: list[CueCandidate], file_label: str, hint: str) -> list[str]:
    """Render one labeled section of inserted or removed cue candidates."""
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


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for student cue candidate detection."""
    import sys
    from pathlib import Path

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print("Usage: py .agents/skills/tafreegh/scripts/diff_cues.py <ai_file> <user_file>")
        return 1

    ai_text = Path(args[0]).read_text(encoding="utf-8")
    user_text = Path(args[1]).read_text(encoding="utf-8")

    result = detect_new_student_cues(ai_text, user_text)
    report = format_cue_report(result)
    if report:
        print(report)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
