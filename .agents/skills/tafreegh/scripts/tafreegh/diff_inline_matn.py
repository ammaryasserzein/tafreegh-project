"""Classify differences in Matn segments between AI baseline and User review.

Implements ADR 0002 & Handoff Task 4:
- Identifies user edits on fallback segments as `fallback_correction`.
- Detects user-tagged oral quotes not present in the canonical source as `oral_citation` (متن شفهي عارض / نقل مستقل).
- Distinguishes canonical transcription/alignment errors as `matn_copy_error`.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .arabic_normalizer import normalize_arabic_search
from .word_gateway import DocxArchiveError, read_matn_source_content


class MatnDiffCategory(str, Enum):
    FALLBACK_CORRECTION = "fallback_correction"
    ORAL_CITATION = "oral_citation"
    MATN_COPY_ERROR = "matn_copy_error"
    ANCHOR_EXPIRY_REREAD = "anchor_expiry_reread"
    UNCLASSIFIED = "unclassified"


@dataclass
class MatnDiffItem:
    line_number: int
    category: MatnDiffCategory
    user_text: str
    ai_text: str | None
    context: str
    description: str


@dataclass
class ExtractedMatn:
    text: str
    line_number: int
    context: str
    is_fallback: bool = False


def extract_matn_segments(markdown_text: str) -> list[ExtractedMatn]:
    """Extracts all standalone and inline matn segments with fallback metadata."""
    results: list[ExtractedMatn] = []
    lines = markdown_text.splitlines()

    pending_fallback = False
    for i, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line:
            continue

        if "<!-- fallback -->" in line:
            pending_fallback = True
            continue

        # Standalone line matn: **(...)** or **...**
        standalone_match = re.match(r'^\*\*(.+)\*\*$', line)
        if standalone_match:
            content = standalone_match.group(1).strip('() ')
            results.append(ExtractedMatn(
                text=content,
                line_number=i,
                context=line,
                is_fallback=pending_fallback
            ))
            pending_fallback = False
            continue

        # Inline matn: **(...)**
        inline_matches = list(re.finditer(r'\*\*\((.+?)\)\*\*', line))
        for m in inline_matches:
            results.append(ExtractedMatn(
                text=m.group(1).strip(),
                line_number=i,
                context=line,
                is_fallback=pending_fallback
            ))
            pending_fallback = False

    return results


_FUZZY_CONTAINMENT_THRESHOLD = 0.70
_FUZZY_JACCARD_THRESHOLD = 0.40


def _token_overlap_similarity(a_norm: str, u_norm: str) -> tuple[float, float]:
    """Return (containment, jaccard) token overlap, allowing sub-token inflection variants."""
    a_tokens = a_norm.split()
    u_tokens = u_norm.split()
    if not a_tokens or not u_tokens:
        return 0.0, 0.0

    u_used = [False] * len(u_tokens)
    a_unmatched: list[str] = []
    matched_weight = 0.0

    for a_tok in a_tokens:
        match_j = next(
            (j for j, u_tok in enumerate(u_tokens) if not u_used[j] and u_tok == a_tok),
            None,
        )
        if match_j is not None:
            u_used[match_j] = True
            matched_weight += 1.0
        else:
            a_unmatched.append(a_tok)

    for a_tok in a_unmatched:
        best_j: int | None = None
        best_w = 0.0
        for j, u_tok in enumerate(u_tokens):
            if u_used[j]:
                continue
            shorter_len = min(len(a_tok), len(u_tok))
            if shorter_len >= 3 and (a_tok in u_tok or u_tok in a_tok):
                weight = shorter_len / max(len(a_tok), len(u_tok))
                if weight > best_w:
                    best_w = weight
                    best_j = j
        if best_j is not None:
            u_used[best_j] = True
            matched_weight += best_w

    min_len = min(len(a_tokens), len(u_tokens))
    union_len = len(a_tokens) + len(u_tokens) - matched_weight
    containment = matched_weight / min_len
    jaccard = matched_weight / union_len if union_len > 0 else 0.0
    return containment, jaccard


def _build_text_edit_diff(
    user_seg: ExtractedMatn,
    matched_ai: ExtractedMatn,
    *,
    is_fallback: bool,
) -> MatnDiffItem | None:
    """Builds a MatnDiffItem when user_seg modifies matched_ai's text, or None if identical."""
    if matched_ai.text.strip() == user_seg.text.strip():
        return None
    category = (
        MatnDiffCategory.FALLBACK_CORRECTION
        if is_fallback
        else MatnDiffCategory.MATN_COPY_ERROR
    )
    description = (
        "تعديل المستخدم على مقطع تمت معالجته في وضع Fallback (إضافة تشكيل أو ضبط ألفاظ)"
        if is_fallback
        else "تصحيح المستخدم على متن معتمد (اختلاف في التشكيل أو اللفظ عن الأصل)"
    )
    return MatnDiffItem(
        line_number=user_seg.line_number,
        category=category,
        user_text=user_seg.text,
        ai_text=matched_ai.text,
        context=user_seg.context,
        description=description,
    )


def classify_matn_diffs(
    ai_markdown: str,
    user_markdown: str,
    matn_source: str | None = None
) -> list[MatnDiffItem]:
    """
    Compares AI baseline against user-reviewed text, classifying differences into:
    - fallback_correction: User edited a segment previously marked as fallback
    - oral_citation: User tagged text as matn that is not in the canonical source
    - matn_copy_error: User corrected a segment against canonical source text
    - anchor_expiry_reread: User restored standalone bold anchor on an additional clause repeat (Anchor Expiry)
    """
    ai_segments = extract_matn_segments(ai_markdown)
    user_segments = extract_matn_segments(user_markdown)

    diff_items: list[MatnDiffItem] = []
    norm_source = normalize_arabic_search(matn_source) if matn_source else ""

    ai_entries: list[tuple[str, ExtractedMatn]] = []
    ai_by_norm: dict[str, list[int]] = {}
    for seg in ai_segments:
        key = normalize_arabic_search(seg.text)
        if key:
            idx = len(ai_entries)
            ai_entries.append((key, seg))
            ai_by_norm.setdefault(key, []).append(idx)

    consumed_ai: set[int] = set()
    unmatched_user: list[tuple[str, ExtractedMatn]] = []

    # Pass 1: Exact normalized match (consumes matched AI occurrences in order)
    last_user_by_norm: dict[str, ExtractedMatn] = {}
    for u_seg in user_segments:
        u_norm = normalize_arabic_search(u_seg.text)
        if not u_norm:
            continue

        prev_u = last_user_by_norm.get(u_norm)
        last_user_by_norm[u_norm] = u_seg

        if u_norm in ai_by_norm:
            avail_idx = next((idx for idx in ai_by_norm[u_norm] if idx not in consumed_ai), None)
            if avail_idx is not None:
                consumed_ai.add(avail_idx)
                matched_ai = ai_entries[avail_idx][1]
                edit_diff = _build_text_edit_diff(u_seg, matched_ai, is_fallback=matched_ai.is_fallback)
                if edit_diff is not None:
                    diff_items.append(edit_diff)
            else:
                prev_ai = ai_entries[ai_by_norm[u_norm][-1]][1]
                edit_diff = _build_text_edit_diff(u_seg, prev_ai, is_fallback=prev_ai.is_fallback)
                if edit_diff is not None:
                    diff_items.append(edit_diff)

                is_distant_from_ai = (
                    u_seg.line_number > prev_ai.line_number + 1
                    or (u_seg.context != prev_ai.context and u_seg.line_number != prev_ai.line_number)
                )
                is_distant_from_user = (
                    prev_u is None
                    or u_seg.line_number > prev_u.line_number + 1
                    or (u_seg.context != prev_u.context and u_seg.line_number != prev_u.line_number)
                )
                if is_distant_from_ai and is_distant_from_user:
                    diff_items.append(MatnDiffItem(
                        line_number=u_seg.line_number,
                        category=MatnDiffCategory.ANCHOR_EXPIRY_REREAD,
                        user_text=u_seg.text,
                        ai_text=prev_ai.text,
                        context=u_seg.context,
                        description="إعادة إبراز مقطع متن كمرساة مستقلة بعد انقضاء المرساة السابقة (Anchor Expiry)",
                    ))
        else:
            unmatched_user.append((u_norm, u_seg))

    # Pass 2a: Unconsumed substring boundary match
    still_unmatched: list[tuple[str, ExtractedMatn]] = []
    for u_norm, u_seg in unmatched_user:
        overlapping = [
            idx
            for idx, (a_norm, _) in enumerate(ai_entries)
            if idx not in consumed_ai and (u_norm in a_norm or a_norm in u_norm)
        ]
        if overlapping:
            contained = [idx for idx in overlapping if ai_entries[idx][0] in u_norm]
            consumed_here = contained if len(contained) > 1 else [overlapping[0]]
            for idx in consumed_here:
                consumed_ai.add(idx)

            any_fallback = any(ai_entries[idx][1].is_fallback for idx in consumed_here)
            matched_a_norm, matched_ai = ai_entries[consumed_here[0]]
            has_non_source_wrapper = bool(
                norm_source
                and matched_a_norm in u_norm
                and u_norm not in norm_source
            )
            edit_diff = _build_text_edit_diff(
                u_seg,
                matched_ai,
                is_fallback=any_fallback or has_non_source_wrapper,
            )
            if edit_diff is not None:
                diff_items.append(edit_diff)
        else:
            still_unmatched.append((u_norm, u_seg))

    # Pass 2b: Token-overlap similarity against remaining unconsumed AI segments
    for u_norm, u_seg in still_unmatched:
        best_idx: int | None = None
        best_score: tuple[float, float] = (0.0, 0.0)
        for idx, (a_norm, _) in enumerate(ai_entries):
            if idx in consumed_ai:
                continue
            containment, jaccard = _token_overlap_similarity(a_norm, u_norm)
            if containment >= _FUZZY_CONTAINMENT_THRESHOLD and jaccard >= _FUZZY_JACCARD_THRESHOLD:
                score = (jaccard, containment)
                if score > best_score:
                    best_score = score
                    best_idx = idx

        if best_idx is not None:
            consumed_ai.add(best_idx)
            matched_ai = ai_entries[best_idx][1]
            edit_diff = _build_text_edit_diff(
                u_seg,
                matched_ai,
                is_fallback=matched_ai.is_fallback,
            )
            if edit_diff is not None:
                diff_items.append(edit_diff)
        else:
            in_source = bool(norm_source and u_norm in norm_source)
            if in_source:
                diff_items.append(MatnDiffItem(
                    line_number=u_seg.line_number,
                    category=MatnDiffCategory.MATN_COPY_ERROR,
                    user_text=u_seg.text,
                    ai_text=None,
                    context=u_seg.context,
                    description="مقطع من المتن الأصلي سقط من مطابق الذكاء الاصطناعي وأضافه المراجع",
                ))
            else:
                diff_items.append(MatnDiffItem(
                    line_number=u_seg.line_number,
                    category=MatnDiffCategory.ORAL_CITATION,
                    user_text=u_seg.text,
                    ai_text=None,
                    context=u_seg.context,
                    description="متن شفهي عارض / نقل مستقل (حديث أو اقتباس لم يرد في ملف المتن الأصلي)",
                ))

    diff_items.sort(key=lambda d: d.line_number)
    return diff_items


REPORT_SECTIONS: tuple[tuple[MatnDiffCategory, str, bool], ...] = (
    (MatnDiffCategory.FALLBACK_CORRECTION, "تصحيحات Fallback", True),
    (MatnDiffCategory.ORAL_CITATION, "متون شفهية عارضة / نقولات مستقلة", False),
    (MatnDiffCategory.MATN_COPY_ERROR, "أخطاء نسخ المتن الأصلي", True),
    (MatnDiffCategory.ANCHOR_EXPIRY_REREAD, "استعادة مرساة المتن بعد تباعد الشرح (Anchor Expiry)", False),
)


def _render_category_section(
    section_num: int,
    title: str,
    items: list[MatnDiffItem],
    *,
    include_ai_text: bool,
) -> list[str]:
    """Render one categorized section of MatnDiffItem entries."""
    lines = [f"\n#### {section_num}. {title} ({len(items)}):"]
    for idx, item in enumerate(items, 1):
        lines.append(f"  {idx}. سطر {item.line_number}: \"{item.user_text}\"")
        if include_ai_text and item.ai_text:
            lines.append(f"     الأصل المعالج: \"{item.ai_text}\"")
        lines.append(f"     السياق: {item.context}")
    return lines


def format_matn_diff_report(diffs: list[MatnDiffItem]) -> str:
    """Formats classified diffs into an executive report."""
    if not diffs:
        return "✓ لا توجد فروقات في المتون المضمنة بين المسودتين."

    lines = [
        "### تقرير تصنيف فروقات المتن (Matn Diff Classification Report)",
        f"- إجمالي الفروقات المرصودة: {len(diffs)}",
    ]

    for section_num, (category, title, include_ai_text) in enumerate(REPORT_SECTIONS, 1):
        items = [d for d in diffs if d.category == category]
        if items:
            lines.extend(
                _render_category_section(
                    section_num,
                    title,
                    items,
                    include_ai_text=include_ai_text,
                )
            )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for inline matn diff reporting."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print("Usage: py diff_inline_matn.py <ai_file> <user_file> [matn_source_file]")
        return 1

    ai_p = Path(args[0])
    user_p = Path(args[1])
    matn_p = Path(args[2]) if len(args) > 2 else None

    if not ai_p.exists() or not user_p.exists():
        print("Error: Files not found.")
        return 1

    ai_c = ai_p.read_text(encoding='utf-8')
    user_c = user_p.read_text(encoding='utf-8')
    matn_c: str | None = None
    if matn_p and matn_p.exists():
        try:
            matn_c = read_matn_source_content(matn_p)
        except DocxArchiveError as exc:
            print(f"Error: Failed to read matn source {matn_p}: {exc}")
            return 1

    diff_list = classify_matn_diffs(ai_c, user_c, matn_source=matn_c)
    print(format_matn_diff_report(diff_list))
    return 0


if __name__ == "__main__":
    sys.exit(main())
