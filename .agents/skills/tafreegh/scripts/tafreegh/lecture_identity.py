from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace

from .arabic_normalizer import normalize_arabic, normalize_arabic_token

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

AUDIO_FILENAME_EXT_RE = re.compile(r"\.(?:mp3|m4a|wav|aac|ogg|opus)\b", re.IGNORECASE)
NOTEBOOKLM_TAG_RE = re.compile(
    r"(?:button[\\_]*magic|source\s*guide|دليل\s*المصادر|دليل\s*المصدر)",
    re.IGNORECASE,
)

NOTEBOOKLM_HEADER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'^(?:المصادر|مصادر|المصدر|دليل المصدر|دليل مصادر)$', re.IGNORECASE),
    re.compile(r'^(?:source\s*guide|sources)$', re.IGNORECASE),
    re.compile(r'^\d{4}-\d{2}-\d{2}[ _]+.*\.(?:mp3|m4a|wav|aac|ogg|opus)$', re.IGNORECASE),
    re.compile(r'^.*\.(?:mp3|m4a|wav|aac|ogg|opus)$', re.IGNORECASE),
)

_FULL_DATE_LINE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_FULL_LECTURE_LABEL_LINE_RE = re.compile(r'^(?:المحاضرة|محاضرة|الدرس|درس)\s*:\s*\d+$')
_FULL_NUMBERED_STEM_LINE_RE = re.compile(r'^\d+[-_][^\s\n\r]+?[-_]\d+$')
_UNSAFE_FILENAME_CHARS_RE = re.compile(r'[\\/*?:"<>|()]')


def sanitize_filename_token(value: str) -> str:
    """Sanitize a subject or title string into a filesystem-safe underscore token."""
    return _UNSAFE_FILENAME_CHARS_RE.sub("", value).strip().replace(" ", "_")


def is_header_line(line: str) -> bool:
    """Checks if a given line belongs to the standard header block or NotebookLM tags."""
    stripped = line.strip()
    if not stripped:
        return True
    if stripped in ("بسم الله الرحمن الرحيم", "بسم الله الرحمن الرحيم."):
        return True
    if stripped.startswith("المادة:") or stripped.startswith("اسم المادة:"):
        return True
    if _FULL_DATE_LINE_RE.match(stripped):
        return True
    if _FULL_LECTURE_LABEL_LINE_RE.match(stripped):
        return True
    if _FULL_NUMBERED_STEM_LINE_RE.match(stripped):
        return True
    return any(pat.match(stripped) for pat in NOTEBOOKLM_HEADER_PATTERNS)


def normalize_stem(candidate_name: str) -> str:
    """
    Strips double extensions (.md.md), trailing extensions (.docx, .md),
    and suffixes (_AI, _processed, _full, _مقاطع, #AI) per ADR 0002 § 9 and ADR 0004.
    """
    s = candidate_name
    prev = None
    while s != prev:
        prev = s
        # Strip trailing known suffixes
        s = re.sub(r'(?:[ _]+(?:AI|processed|full|مقاطع)|#[a-zA-Z0-9]+)+$', '', s, flags=re.IGNORECASE)
        # Strip trailing extensions (supports single/double extensions)
        s = re.sub(r'(\.[a-zA-Z0-9_]+)+$', '', s)
    return s.strip()


def match_canonical_subject(
    text: str,
    routing_map: Mapping[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Matches text against canonical routing in descending length order."""
    if not text:
        return None, None
    rm = routing_map if routing_map is not None else {}
    norm_text = normalize_arabic(text)
    for key in sorted(rm.keys(), key=len, reverse=True):
        if normalize_arabic(key) in norm_text:
            return key, rm[key]
    return None, None


@dataclass(frozen=True)
class LectureIdentity:
    """
    Immutable domain value object representing a lecture's identity.
    Encapsulates date, lecture_number, keyword, subject_name, audio_file, and stem,
    eliminating data clump and shotgun surgery smells across export and training pipelines.
    """
    date: str | None = None
    lecture_number: str | None = None
    keyword: str | None = None
    subject_name: str | None = None
    audio_file: str | None = None
    stem: str | None = None

    # --- Domain Properties ---
    @property
    def header_line_3(self) -> str:
        """Resolves Header Line 3 deterministically: date, lecture number, or fallback."""
        if self.date:
            return str(self.date)
        if self.lecture_number:
            return f"المحاضرة: {self.lecture_number}"
        return "تاريخ_غير_محدد"

    @property
    def header_lines(self) -> tuple[str, str, str]:
        """Returns the canonical 3-line lecture header tuple."""
        return (
            "بسم الله الرحمن الرحيم",
            f"المادة: {self.resolved_subject}",
            self.header_line_3,
        )

    @property
    def resolved_stem(self) -> str:
        """Derives a normalized canonical stem identifier."""
        if self.stem:
            return normalize_stem(self.stem)
        if self.lecture_number:
            subj = self.subject_name or self.keyword or "مادة"
            subj_token = sanitize_filename_token(subj)
            return f"{self.lecture_number}-{subj_token}_{self.lecture_number}"
        if self.date:
            return str(self.date)
        return "تاريخ_غير_محدد"

    @property
    def resolved_subject(self) -> str:
        """Returns subject_name, keyword, or generic fallback."""
        return self.subject_name or self.keyword or "المادة"

    def merge(self, other: LectureIdentity | None) -> LectureIdentity:
        """
        Returns a new LectureIdentity where non-empty fields from other override self,
        while fields not specified in other are preserved from self.
        """
        if other is None:
            return self

        def _pick(field: str) -> str | None:
            val_other = getattr(other, field, None)
            if val_other is not None and str(val_other).strip() != "":
                return str(val_other)
            return getattr(self, field)

        return LectureIdentity(
            date=_pick("date"),
            lecture_number=_pick("lecture_number"),
            keyword=_pick("keyword"),
            subject_name=_pick("subject_name"),
            audio_file=_pick("audio_file"),
            stem=_pick("stem"),
        )

    def matches(
        self,
        candidate_name: str,
        routing_map: Mapping[str, str] | None = None,
    ) -> bool:
        """
        Determines if candidate_name matches this lecture's identity,
        supporting exact stem matches, date matches, and mirrored numbered stems.
        """
        cleaned_cand = normalize_stem(candidate_name)

        # 1. Exact stem match
        if self.stem and normalize_stem(self.stem) == cleaned_cand:
            return True

        rm = routing_map if routing_map is not None else {}

        seed_tokens: set[str] = set()
        if self.keyword:
            norm_kw = normalize_arabic_token(self.keyword)
            if norm_kw:
                seed_tokens.add(norm_kw)
        if self.subject_name:
            norm_subj = normalize_arabic_token(self.subject_name)
            if norm_subj:
                seed_tokens.add(norm_subj)
            clean_sub = re.sub(r'\(.*?\)', '', self.subject_name).strip()
            norm_clean = normalize_arabic_token(clean_sub)
            if norm_clean:
                seed_tokens.add(norm_clean)

        kw_variants: set[str] = set(seed_tokens)
        for k, v in rm.items():
            k_norm = normalize_arabic_token(k)
            v_norm = normalize_arabic_token(v)
            for token in list(seed_tokens):
                if token == k_norm or token == v_norm or (len(token) >= 3 and (token in v_norm or v_norm in token)):
                    if k_norm:
                        kw_variants.add(k_norm)
                    if v_norm:
                        kw_variants.add(v_norm)

        # 2. Date-based matching (YYYY-MM-DD)
        if self.date and re.match(r'^\d{4}-\d{2}-\d{2}$', str(self.date)):
            if str(self.date) not in candidate_name:
                return False
            if not kw_variants:
                return True
            stem_rem = cleaned_cand.replace(str(self.date), " ").strip(" _-")
            norm_rem = normalize_arabic_token(stem_rem)
            return bool(norm_rem) and any(v in norm_rem or norm_rem in v for v in kw_variants)

        # 3. Numbered stem matching
        target_num = self.lecture_number or (str(self.date) if self.date and str(self.date).isdigit() else None)
        if not target_num and self.stem:
            stem_num_match = re.search(r'(?<!\d)(\d+)(?!\d)', self.stem)
            if stem_num_match:
                target_num = stem_num_match.group(1)

        cand_numbered = re.match(r'^(\d+)[-_](.+?)[-_](\d+)$', cleaned_cand)
        if cand_numbered:
            n1, middle, n2 = cand_numbered.group(1), cand_numbered.group(2), cand_numbered.group(3)
            if n1 == n2:  # Mirrored stem
                if not target_num or str(target_num) != n1:
                    return False
                norm_mid = normalize_arabic_token(middle)
                return bool(norm_mid) and any(v in norm_mid or norm_mid in v for v in kw_variants)

        # 4. Fallback: check if target_num and keyword variant appear in cleaned_cand
        if target_num:
            cand_numbers = re.findall(r'(?<!\d)\d+(?!\d)', cleaned_cand)
            if str(target_num) in cand_numbers:
                norm_cand = normalize_arabic_token(cleaned_cand)
                return bool(norm_cand) and any(v in norm_cand for v in kw_variants)

        return False

    @classmethod
    def from_text(
        cls,
        text: str,
        routing_map: Mapping[str, str] | None = None,
    ) -> LectureIdentity:
        """
        Extracts date, keyword, audio_file, clean canonical subject_name,
        and lecture_number from markdown text, filenames, or raw transcript headers.
        """
        rm = routing_map if routing_map is not None else {}
        date: str | None = None
        lecture_number: str | None = None
        keyword: str | None = None
        subject_name: str | None = None
        audio_file: str | None = None
        stem: str | None = None

        # 1. Date extraction (YYYY-MM-DD)
        date_match = re.search(r'(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)', text)
        if date_match:
            date = date_match.group(1)

        # 2. Lecture number from explicit label (المحاضرة: 17)
        lec_match = re.search(r'^(?:المحاضرة|محاضرة|الدرس|درس)\s*:\s*(\d+)', text, re.MULTILINE)
        if lec_match:
            lecture_number = lec_match.group(1).strip()

        # 3. Audio file token extraction
        audio_match = re.search(r'(?<!\d)(\d{4}-\d{2}-\d{2}[ _]+[^\n\r]+?\.(?:mp3|m4a|wav|aac|ogg|opus))\b', text, re.IGNORECASE)
        if not audio_match:
            audio_match = re.search(r'\b([^\n\r]+?\.(?:mp3|m4a|wav|aac|ogg|opus))\b', text, re.IGNORECASE)
        if audio_match:
            audio_file = audio_match.group(1).strip()

        # 4. Mirrored numbered stem pattern (e.g. 17-فقه_البيوع_17 or 17-بيوع-17)
        numbered_stem_match = re.search(r'(?<!\d)(\d+)[-_]([^\s\d\n\r]+?)[-_](\d+)(?!\d)', text)
        if numbered_stem_match:
            n1 = numbered_stem_match.group(1)
            stem_middle = numbered_stem_match.group(2).strip()
            n2 = numbered_stem_match.group(3)
            if n1 == n2:
                lecture_number = n1
                stem = f"{n1}-{stem_middle}_{n2}"
                if not keyword:
                    clean_middle = stem_middle.replace("_", " ").strip()
                    canonical_key, canonical_subj = match_canonical_subject(clean_middle, rm)
                    if canonical_key:
                        keyword = canonical_key
                        subject_name = canonical_subj
                    else:
                        keyword = clean_middle

        # 5. Subject extraction from explicit label (المادة: ...)
        subject_match = re.search(r'^(?:اسم المادة|المادة)\s*:\s*([^\n\r]+)', text, re.MULTILINE)
        if subject_match:
            full_subject = subject_match.group(1).strip()
            first_word = re.split(r'[\s(]', full_subject)[0].strip()
            norm_key = normalize_arabic(first_word)
            if norm_key in rm:
                keyword = first_word
                subject_name = rm[norm_key]
            else:
                canonical_key, canonical_subj = match_canonical_subject(full_subject, rm)
                if canonical_key:
                    keyword = canonical_key
                    subject_name = canonical_subj
                else:
                    clean_sub = re.sub(r'\s*\([^)]*فصل[^)]*\)', '', full_subject).strip()
                    keyword = first_word
                    subject_name = clean_sub

        # 6. Immediate filename/word token fallback after date (never scan trailing body prose)
        if not keyword and date:
            token_match = re.search(
                rf'(?<!\d){re.escape(date)}[ _]+([^\s.]+)',
                text,
            )
            if token_match:
                raw_token = token_match.group(1).strip()
                clean_token = raw_token.replace("_", " ").strip()
                canonical_key, canonical_subj = match_canonical_subject(clean_token, rm)
                if canonical_key:
                    keyword = canonical_key
                    subject_name = canonical_subj
                else:
                    first_part = raw_token.split("_")[0].strip()
                    keyword = first_part
                    norm_key = normalize_arabic(first_part)
                    subject_name = rm.get(norm_key, first_part)

        # 7. Reverse lookup from audio file if keyword still missing
        if not keyword and audio_file:
            canonical_key, canonical_subj = match_canonical_subject(audio_file, rm)
            if canonical_key:
                keyword = canonical_key
                subject_name = canonical_subj

        return cls(
            date=date,
            lecture_number=lecture_number,
            keyword=keyword,
            subject_name=subject_name,
            audio_file=audio_file,
            stem=stem,
        )

    @classmethod
    def from_filename(
        cls,
        filename: str,
        fallback_subject: str | None = None,
        routing_map: Mapping[str, str] | None = None,
    ) -> LectureIdentity:
        """Parses identity from a standalone filename."""
        cleaned = normalize_stem(filename)
        parsed = cls.from_text(cleaned, routing_map=routing_map)
        subject_name = parsed.subject_name
        keyword = parsed.keyword
        if not parsed.lecture_number:
            canonical_key, canonical_subj = match_canonical_subject(
                cleaned.replace("_", " "),
                routing_map,
            )
            if canonical_key and (
                not keyword
                or normalize_arabic(keyword) not in {normalize_arabic(k) for k in (routing_map or {})}
                or (
                    normalize_arabic(canonical_key).startswith(normalize_arabic(keyword))
                    and len(canonical_key) > len(keyword)
                )
            ):
                keyword = canonical_key
                subject_name = canonical_subj
        if fallback_subject:
            canonical_key, canonical_subj = match_canonical_subject(fallback_subject, routing_map)
            if not subject_name:
                subject_name = canonical_subj or fallback_subject
            if not keyword:
                keyword = canonical_key or fallback_subject
        return replace(parsed, stem=cleaned, subject_name=subject_name, keyword=keyword)


def resolve_document_identity(
    markdown_text: str,
    identity: LectureIdentity | None = None,
    *,
    path_identity: LectureIdentity | None = None,
    routing_map: Mapping[str, str] | None = None,
) -> LectureIdentity:
    """
    Parses transcript metadata and applies non-destructive merge precedence:
    explicit override > path metadata > parsed transcript metadata.
    When a higher-precedence layer provides a lecture_number without a date,
    prioritizes numbered lecture formatting over parsed text dates without mutating instances,
    and clears stale lower-precedence stems when naming fields are overridden.
    """
    resolved = LectureIdentity.from_text(markdown_text, routing_map=routing_map)
    for layer in (path_identity, identity):
        if layer is None:
            continue
        prev = resolved
        resolved = prev.merge(layer)
        if layer.keyword and not layer.subject_name and routing_map:
            canonical_key, canonical_subj = match_canonical_subject(layer.keyword, routing_map)
            if canonical_subj:
                resolved = replace(
                    resolved,
                    keyword=canonical_key or resolved.keyword,
                    subject_name=canonical_subj,
                )
        if layer.lecture_number and not layer.date:
            resolved = replace(resolved, date=None)
        if not layer.stem and (
            (layer.lecture_number and layer.lecture_number != prev.lecture_number)
            or (layer.date and layer.date != prev.date)
            or (resolved.subject_name and resolved.subject_name != prev.subject_name)
        ):
            resolved = replace(resolved, stem=None)
    return resolved


def strip_header_blocks(markdown_text: str) -> list[list[str]]:
    """
    Strips NotebookLM tags and existing lecture header lines from markdown paragraphs,
    returning non-empty cleaned line lists per paragraph.
    """
    blocks: list[list[str]] = []
    for para in markdown_text.split('\n\n'):
        lines = [line.strip() for line in para.split('\n') if line.strip()]
        if not lines or all(is_header_line(line) for line in lines):
            continue
        while lines and is_header_line(lines[0]):
            lines.pop(0)
        if lines:
            blocks.append(lines)
    return blocks


def apply_transcript_header(markdown_text: str, identity: LectureIdentity) -> str:
    """Strips existing tags/headers and prepends the canonical 3-line header for identity."""
    body = '\n\n'.join('\n'.join(lines) for lines in strip_header_blocks(markdown_text))
    header = '\n'.join(identity.header_lines)
    if body:
        return f"{header}\n\n{body}"
    return header


def standardize_transcript_header(
    markdown_text: str,
    identity: LectureIdentity | None = None,
    *,
    path_identity: LectureIdentity | None = None,
    routing_map: Mapping[str, str] | None = None,
) -> str:
    """
    Strips NotebookLM tags (Source guide, audio file names, etc.) and existing headers,
    returning cleanly standardized markdown beginning with the 3-line centered header.
    """
    ident = resolve_document_identity(
        markdown_text,
        identity,
        path_identity=path_identity,
        routing_map=routing_map,
    )
    return apply_transcript_header(markdown_text, ident)
