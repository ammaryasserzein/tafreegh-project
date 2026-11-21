"""Pass 5: Unbolded Classical Arabic Sharh/Matn fallback trigger audit."""

from __future__ import annotations

import re

from ._qa_models import HEADER_LINE_COUNT, STUDENT_PREFIX, ParagraphRecord, ValidationReport
from .arabic_normalizer import normalize_arabic, strip_tashkeel

FALLBACK_MATN_TRIGGERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("قالوا", re.compile(r"(?:^|[،.؟!:)»\"\s])(قالوا(?!\w)(?:\s+له)?\s*:\s*[^.؟!\n]+)")),
    ("فإن قلت", re.compile(r"(?:^|[،.؟!:)»\"\s])(فإن\s+قلت(?!\w)\s*:?\s*[^.؟!\n]+)")),
    ("قلت", re.compile(r"(?:^|[،.؟!:)»\"\s])(?<!فإن\s)(قلت(?!\w)\s*:\s*[^.؟!\n]+)")),
    ("وأيضا", re.compile(r"(?:^|[،.؟!:)»\"\s])(وأيضا(?!\w)\s*:?\s*[^.؟!\n]+)")),
    ("فصل في", re.compile(r"(?:^|[،.؟!:)»\"\s])(فصل\s+في\s+[\u0600-\u06FF\s]{4,40}?)(?=[،.؟!]|$)")),
    ("قال الشاعر", re.compile(r"(?:^|[،.؟!:)»\"])\s*([^،.؟!\n]+[،:]\s*قال\s+الشاعر(?!\w)\s*:?)")),
    ("مسألة", re.compile(r"(?:^|[،.؟!:)»\"\s])(مسألة(?!\w)\s*:\s*[^.؟!\n]+)")),
    ("فائدة", re.compile(r"(?:^|[،.؟!:)»\"\s])(فائدة(?!\w)\s*:\s*[^.؟!\n]+)")),
    ("الشرح", re.compile(r"(?:^|[،.؟!:)»\"\s])(الشرح(?!\w)\s*:\s*[^.؟!\n]+)")),
    (
        "قال العالم",
        re.compile(
            r"(?:^|[،.؟!:)»\"\s])([وف]?(?:قال|يقول)\s+"
            r"(?:الشيخ|الإمام|المصنف|ابن|أبو|القاضي|الحافظ)\s+"
            r"(?!فلان(?!\w))[\u0621-\u064A\u064B-\u065F\u0670\u0671]+(?:\s+[\u0621-\u064A\u064B-\u065F\u0670\u0671]+){0,2}\s*:\s*[^.؟!\n]+)"
        ),
    ),
    ("قال", re.compile(r"(?:^|[،.؟!:)»\"\s])(قال(?!\w)(?!\s+(?:تعالى|الله|النبي|رسول))\s*:\s*[^.؟!\n]+)")),
)

_ARABIC_WORD_RE = re.compile(r"[\u0621-\u064A\u064B-\u065F\u0670\u0671]+")
_HO_WALA_RE = re.compile(r"(?<!\w)هو\s+[\u0621-\u064A\u064B-\u065F\u0670\u0671\s]+\s+ولا\s+")
_MA_VERB_SH_RE = re.compile(r"(?<!\w)ما\s+[\u0621-\u064A]{2,}ش(?!\w)")
_MA_PRON_RE = re.compile(r"(?<!\w)ما\s+(?:هو|هي|هم)(?!\w)")
_SUBCLAUSE_DELIM_RE = re.compile(r"[،.؟!:\n]")
_SENTENCE_DELIM_RE = re.compile(r"[.\n]")
_CLAUSE_SPLIT_RE = re.compile(r"https?://|\s*-\s*يعني\s+|[،]")
_ANECDOTE_DIALOGUE_LABELS: frozenset[str] = frozenset({"قال", "قالوا", "قلت"})

_PAREN_SPAN_RE = re.compile(r"\([^()]*\)")
_QUOTE_SPAN_RE = re.compile(r'"[^"]*"')
_MUSHAF_SPAN_RE = re.compile(r"﴿[^﴾]*﴾")
_GUILLEMET_SPAN_RE = re.compile(r"«[^»]*»")
_LEADING_MASKED_CITATION_RE = re.compile(
    r"^(?:قال|قالوا|قلت)(?:\s+له)?\s*:\s*(?:\(\)|\"\"|﴿﴾|«»)"
)
_QULTU_OBJ_EXEMPT_RE = re.compile(r"^قلت\s+(?:له|لها|لكم|لك|لهم)(?!\w)")
_SUBJECT_EXEMPT_RE = re.compile(
    r"(?:^|[\s،.؟!:)»\"])(?:ما\s+)?(?:انت|انا|هو|هم|[وف]?النبي(?:\s+(?:صلى\s+الله\s+عليه\s+وسلم|ﷺ))?)$"
)


def _mask_citations(text: str) -> str:
    """Replace parenthesized, quoted, and bracketed citations with neutral placeholders."""
    masked = _PAREN_SPAN_RE.sub("()", text)
    masked = _PAREN_SPAN_RE.sub("()", masked)
    masked = _QUOTE_SPAN_RE.sub('""', masked)
    masked = _MUSHAF_SPAN_RE.sub("﴿﴾", masked)
    return _GUILLEMET_SPAN_RE.sub("«»", masked)


def _has_colloquial_marker(
    text: str,
    normalized_markers: frozenset[str] | set[str],
) -> bool:
    """Return True if text contains Egyptian colloquial words or verbal negation/future patterns."""
    plain = strip_tashkeel(text)
    if _HO_WALA_RE.search(plain) or _MA_VERB_SH_RE.search(plain) or _MA_PRON_RE.search(plain):
        return True
    for word in _ARABIC_WORD_RE.findall(plain):
        word_norm = normalize_arabic(word)
        if word in normalized_markers or word_norm in normalized_markers:
            return True
        if len(word_norm) >= 3 and word_norm[0] in ("و", "ف") and word_norm[1:] in normalized_markers:
            return True
        if word.startswith(("هت", "هي", "بي", "بت", "ما")) and word.endswith("ش") and len(word) >= 4:
            return True
    return False


def _extract_leading_classical_clause(
    candidate: str,
    normalized_markers: frozenset[str] | set[str],
) -> str:
    """Extract consecutive leading Classical Arabic sub-clauses before any colloquial shift."""
    classical_parts: list[str] = []
    for sub in _CLAUSE_SPLIT_RE.split(candidate):
        sub_clean = sub.strip(" .؟!:-")
        if not sub_clean:
            continue
        if _has_colloquial_marker(sub_clean, normalized_markers):
            break
        classical_parts.append(sub_clean)
    return "، ".join(classical_parts)


def check_unbolded_fallback_matn(
    para_records: list[ParagraphRecord],
    report: ValidationReport,
    dialect_markers: frozenset[str] | set[str],
) -> None:
    """Detect unbolded Classical Arabic Sharh/Matn clauses inside explanation paragraphs."""
    normalized_markers = {
        normalize_arabic(strip_tashkeel(marker)) for marker in dialect_markers
    } | set(dialect_markers)

    for rec in para_records:
        if rec.index < HEADER_LINE_COUNT or rec.is_matn:
            continue
        stripped = rec.text.strip()
        if not stripped or stripped.startswith(STUDENT_PREFIX):
            continue

        masked = _mask_citations(stripped)
        matches: list[tuple[int, int, str, re.Match[str]]] = []
        for label, pat in FALLBACK_MATN_TRIGGERS:
            for m in pat.finditer(masked):
                matches.append((m.start(1), -(m.end(1) - m.start(1)), label, m))
        matches.sort(key=lambda item: (item[0], item[1]))

        anecdote_dialogue = False
        for _, _, label, m in matches:
            before_match = masked[: m.start(1)]
            cand = m.group(1).strip()
            if _QULTU_OBJ_EXEMPT_RE.match(cand) or _LEADING_MASKED_CITATION_RE.match(cand):
                continue

            if label in _ANECDOTE_DIALOGUE_LABELS:
                anecdote_prefix = _SENTENCE_DELIM_RE.split(before_match)[-1]
                if anecdote_dialogue or _has_colloquial_marker(anecdote_prefix, normalized_markers):
                    anecdote_dialogue = True
                    continue
                if (
                    before_match
                    and before_match[-1].isspace()
                    and _SUBJECT_EXEMPT_RE.search(normalize_arabic(strip_tashkeel(before_match)))
                ):
                    continue
            else:
                prefix = _SUBCLAUSE_DELIM_RE.split(before_match)[-1]
                if _has_colloquial_marker(prefix, normalized_markers):
                    continue

            core_clause = _extract_leading_classical_clause(cand, normalized_markers)
            words = [
                w
                for w in _ARABIC_WORD_RE.findall(core_clause)
                if normalize_arabic(strip_tashkeel(w)) != "مثلا"
            ]
            if len(words) >= 4:
                report.flag(
                    "UNBOLDED_FALLBACK_MATN",
                    rec.index,
                    (
                        f"Paragraph P{rec.index} contains an unbolded Classical Arabic Sharh/Matn segment "
                        f"triggered by '{label}': isolate as '**(...)**'."
                    ),
                    core_clause[:100],
                )
