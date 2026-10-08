"""Classify differences in Matn segments between AI baseline and User review.

Implements ADR 0002 & Handoff Task 4:
- Identifies user edits on fallback segments as `fallback_correction`.
- Detects user-tagged oral quotes not present in the canonical source as `oral_citation` (متن شفهي عارض / نقل مستقل).
- Distinguishes canonical transcription/alignment errors as `matn_copy_error`.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Try importing normalize_arabic_search from matn_matcher if available
try:
    from matn_matcher import normalize_arabic_search, strip_tashkeel
except ImportError:
    def strip_tashkeel(text: str) -> str:
        return re.sub(r'[\u064B-\u065F\u0670\u0640]', '', text)

    def normalize_arabic_search(text: str) -> str:
        t = strip_tashkeel(text)
        t = re.sub(r'[أإآٱ]', 'ا', t)
        t = re.sub(r'ة', 'ه', t)
        t = re.sub(r'ى', 'ي', t)
        t = re.sub(r'[^\w\s]', ' ', t)
        return re.sub(r'\s+', ' ', t).strip()


class MatnDiffCategory(str, Enum):
    FALLBACK_CORRECTION = "fallback_correction"
    ORAL_CITATION = "oral_citation"
    MATN_COPY_ERROR = "matn_copy_error"
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
    """
    ai_segments = extract_matn_segments(ai_markdown)
    user_segments = extract_matn_segments(user_markdown)

    diff_items: list[MatnDiffItem] = []
    norm_source = normalize_arabic_search(matn_source) if matn_source else ""

    # Index AI segments by normalized query
    ai_by_norm = {}
    for seg in ai_segments:
        key = normalize_arabic_search(seg.text)
        if key:
            ai_by_norm[key] = seg

    for u_seg in user_segments:
        u_norm = normalize_arabic_search(u_seg.text)
        if not u_norm:
            continue

        # Check exact or partial match in AI segments
        matched_ai = None
        for a_norm, a_seg in ai_by_norm.items():
            if u_norm in a_norm or a_norm in u_norm or u_norm == a_norm:
                matched_ai = a_seg
                break

        if matched_ai:
            # Segment was present in AI output
            if matched_ai.is_fallback:
                # User revised a fallback segment
                if matched_ai.text.strip() != u_seg.text.strip():
                    diff_items.append(MatnDiffItem(
                        line_number=u_seg.line_number,
                        category=MatnDiffCategory.FALLBACK_CORRECTION,
                        user_text=u_seg.text,
                        ai_text=matched_ai.text,
                        context=u_seg.context,
                        description="تعديل المستخدم على مقطع تمت معالجته في وضع Fallback (إضافة تشكيل أو ضبط ألفاظ)"
                    ))
            elif matched_ai.text.strip() != u_seg.text.strip():
                # Primary segment discrepancy
                diff_items.append(MatnDiffItem(
                    line_number=u_seg.line_number,
                    category=MatnDiffCategory.MATN_COPY_ERROR,
                    user_text=u_seg.text,
                    ai_text=matched_ai.text,
                    context=u_seg.context,
                    description="تصحيح المستخدم على متن معتمد (اختلاف في التشكيل أو اللفظ عن الأصل)"
                ))
        else:
            # Segment was newly tagged by user (not present in AI matn segments)
            in_source = bool(norm_source and u_norm in norm_source)
            if in_source:
                diff_items.append(MatnDiffItem(
                    line_number=u_seg.line_number,
                    category=MatnDiffCategory.MATN_COPY_ERROR,
                    user_text=u_seg.text,
                    ai_text=None,
                    context=u_seg.context,
                    description="مقطع من المتن الأصلي سقط من مطابق الذكاء الاصطناعي وأضفاه المراجع"
                ))
            else:
                diff_items.append(MatnDiffItem(
                    line_number=u_seg.line_number,
                    category=MatnDiffCategory.ORAL_CITATION,
                    user_text=u_seg.text,
                    ai_text=None,
                    context=u_seg.context,
                    description="متن شفهي عارض / نقل مستقل (حديث أو اقتباس لم يرد في ملف المتن الأصلي)"
                ))

    return diff_items


def format_matn_diff_report(diffs: list[MatnDiffItem]) -> str:
    """Formats classified diffs into an executive report."""
    if not diffs:
        return "✓ لا توجد فروقات في المتون المضمنة بين المسودتين."

    lines = [
        "### تقرير تصنيف فروقات المتن (Matn Diff Classification Report)",
        f"- إجمالي الفروقات المرصودة: {len(diffs)}",
    ]

    fallback_diffs = [d for d in diffs if d.category == MatnDiffCategory.FALLBACK_CORRECTION]
    oral_diffs = [d for d in diffs if d.category == MatnDiffCategory.ORAL_CITATION]
    copy_diffs = [d for d in diffs if d.category == MatnDiffCategory.MATN_COPY_ERROR]

    if fallback_diffs:
        lines.append(f"\n#### 1. تصحيحات Fallback ({len(fallback_diffs)}):")
        for i, d in enumerate(fallback_diffs, 1):
            lines.append(f"  {i}. سطر {d.line_number}: \"{d.user_text}\"")
            if d.ai_text:
                lines.append(f"     الأصل المعالج: \"{d.ai_text}\"")
            lines.append(f"     السياق: {d.context}")

    if oral_diffs:
        lines.append(f"\n#### 2. متون شفهية عارضة / نقولات مستقلة ({len(oral_diffs)}):")
        for i, d in enumerate(oral_diffs, 1):
            lines.append(f"  {i}. سطر {d.line_number}: \"{d.user_text}\"")
            lines.append(f"     السياق: {d.context}")

    if copy_diffs:
        lines.append(f"\n#### 3. أخطاء نسخ المتن الأصلي ({len(copy_diffs)}):")
        for i, d in enumerate(copy_diffs, 1):
            lines.append(f"  {i}. سطر {d.line_number}: \"{d.user_text}\"")
            if d.ai_text:
                lines.append(f"     الأصل المعالج: \"{d.ai_text}\"")
            lines.append(f"     السياق: {d.context}")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: py diff_inline_matn.py <ai_file> <user_file> [matn_source_file]")
        sys.exit(1)

    ai_p = Path(sys.argv[1])
    user_p = Path(sys.argv[2])
    matn_p = Path(sys.argv[3]) if len(sys.argv) > 3 else None

    if not ai_p.exists() or not user_p.exists():
        print("Error: Files not found.")
        sys.exit(1)

    ai_c = ai_p.read_text(encoding='utf-8')
    user_c = user_p.read_text(encoding='utf-8')
    matn_c = matn_p.read_text(encoding='utf-8') if matn_p and matn_p.exists() else None

    diff_list = classify_matn_diffs(ai_c, user_c, matn_source=matn_c)
    print(format_matn_diff_report(diff_list))
