from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def normalize_arabic(text: str) -> str:
    """Normalizes hamzas, wasl, and cleans leading/trailing whitespace."""
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r'[أإآٱ]', 'ا', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


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


def _resolve_context_file(context_path: Path | None = None) -> Path | None:
    """Finds CONTEXT.md in explicit path or ascending repository directories."""
    if context_path and Path(context_path).exists():
        return Path(context_path)
    
    # 1. Traverse up from current script location
    for p in Path(__file__).resolve().parents:
        cand = p / "CONTEXT.md"
        if cand.exists() and cand.is_file():
            return cand

    # 2. Traverse up from current working directory
    for p in [Path.cwd(), *Path.cwd().parents]:
        cand = p / "CONTEXT.md"
        if cand.exists() and cand.is_file():
            return cand

    return None


def load_canonical_routing(context_path: Path | None = None) -> dict[str, str]:
    """
    Dynamically parses Section 3 Routing Map from CONTEXT.md as the single source of truth.
    Returns mapping from keyword variations to canonical subject names.
    """
    file_path = _resolve_context_file(context_path)
    routing_map: dict[str, str] = {}
    
    if not file_path:
        return routing_map

    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    has_section_3 = any(line.strip().startswith("## 3.") or "توجيه المتون" in line for line in lines)
    in_section_3 = False
    in_table = False

    kw_col_idx = 0
    subj_col_idx = 1
    header_found = False

    for line in lines:
        stripped = line.strip()
        if has_section_3:
            if stripped.startswith("## 3.") or "توجيه المتون" in stripped:
                in_section_3 = True
                continue
            if in_section_3 and stripped.startswith("## "):
                # Left Section 3
                break
            if not in_section_3:
                continue

        if not (stripped.startswith("|") and stripped.endswith("|")):
            if in_table:
                # End of table block
                break
            continue

        cells = [c.strip() for c in re.split(r"(?<!\\)\|", stripped)[1:-1]]
        if not cells:
            continue

        # Check for markdown table separator row: | --- | --- |
        if all(re.match(r"^:?-+:?$", c) for c in cells):
            in_table = True
            continue

        # Dynamic header detection
        if not header_found:
            found_kw = None
            found_subj = None
            for idx, cell in enumerate(cells):
                norm_c = normalize_arabic(cell)
                if any(w in norm_c for w in ("الكلمة", "الدلالية", "keyword")):
                    found_kw = idx
                elif any(w in norm_c for w in ("المادة", "المعتمدة", "subject")):
                    found_subj = idx
            if found_kw is not None or found_subj is not None:
                header_found = True
                in_table = True
                if found_kw is not None:
                    kw_col_idx = found_kw
                if found_subj is not None:
                    subj_col_idx = found_subj
                continue

        in_table = True
        keyword_cell = cells[kw_col_idx] if kw_col_idx < len(cells) else cells[0]
        subject_cell = cells[subj_col_idx] if subj_col_idx < len(cells) else (cells[1] if len(cells) > 1 else cells[0])

        # Extract bold text if present: **subject**
        bold_match = re.search(r"\*\*([^*]+)\*\*", subject_cell)
        if bold_match:
            canonical_name = bold_match.group(1).strip()
        else:
            # Fallback: clean parenthesized notes if any
            clean_sub = re.sub(r"\s*\(للإمام[^)]*\)", "", subject_cell)
            clean_sub = re.sub(r"\s*\(للشيخ[^)]*\)", "", clean_sub)
            canonical_name = clean_sub.strip()

        # Extract individual keyword tokens from keyword_cell
        # Example formats: `(زاد)` / `(زاد المعاد)`, `(بيوع)` / `(فقه_البيوع)` / `(خثلان)`
        raw_tokens = re.findall(r"`?\(?([^`()/]+)\)?`?", keyword_cell)
        tokens: list[str] = []
        for t in raw_tokens:
            cleaned_t = t.strip("`() /")
            if cleaned_t:
                tokens.append(cleaned_t)

        for token in tokens:
            routing_map[token] = canonical_name
            routing_map[normalize_arabic(token)] = canonical_name

            # Underscore / Space variants
            if "_" in token:
                space_v = token.replace("_", " ").strip()
                routing_map[space_v] = canonical_name
                routing_map[normalize_arabic(space_v)] = canonical_name
            if " " in token:
                under_v = token.replace(" ", "_").strip()
                routing_map[under_v] = canonical_name
                routing_map[normalize_arabic(under_v)] = canonical_name

            # Definite article (الـ) variant
            norm_token = normalize_arabic(token)
            if not norm_token.startswith("ال"):
                al_v = f"ال{token}"
                routing_map[al_v] = canonical_name
                routing_map[normalize_arabic(al_v)] = canonical_name

        # Map canonical name to itself
        routing_map[canonical_name] = canonical_name
        routing_map[normalize_arabic(canonical_name)] = canonical_name

    return routing_map


# Module-level routing dictionary dynamically loaded from CONTEXT.md
CANONICAL_ROUTING: dict[str, str] = load_canonical_routing()


def match_canonical_subject(
    text: str,
    routing_map: dict[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Matches text against canonical routing in descending length order."""
    if not text:
        return None, None
    rm = routing_map if routing_map is not None else CANONICAL_ROUTING
    norm_text = normalize_arabic(text)
    for key in sorted(rm.keys(), key=len, reverse=True):
        if normalize_arabic(key) in norm_text:
            return key, rm[key]
    return None, None


@dataclass
class LectureIdentity:
    """
    Consolidated domain entity representing a lecture's identity.
    Encapsulates date, lecture_number, keyword, subject_name, audio_file, and stem,
    eliminating data clump and shotgun surgery smells across export and training pipelines.
    """
    date: str | None = None
    lecture_number: str | None = None
    keyword: str | None = None
    subject_name: str | None = None
    audio_file: str | None = None
    stem: str | None = None

    # --- Mapping / Dict compatibility for legacy callers ---
    def __getitem__(self, key: str) -> Any:
        if key in self.__dataclass_fields__:
            return getattr(self, key)
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self.__dataclass_fields__:
            setattr(self, key, value)
        else:
            raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in self.__dataclass_fields__

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.__dataclass_fields__:
            val = getattr(self, key)
            return val if val is not None else default
        return default

    def items(self):
        return {
            "date": self.date,
            "lecture_number": self.lecture_number,
            "keyword": self.keyword,
            "subject_name": self.subject_name,
            "audio_file": self.audio_file,
            "stem": self.stem,
        }.items()

    def keys(self):
        return ["date", "lecture_number", "keyword", "subject_name", "audio_file", "stem"]

    def values(self):
        return [self.date, self.lecture_number, self.keyword, self.subject_name, self.audio_file, self.stem]

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
    def resolved_stem(self) -> str:
        """Derives a normalized canonical stem identifier."""
        if self.stem:
            return normalize_stem(self.stem)
        if self.lecture_number:
            subj = self.subject_name or self.keyword or "مادة"
            subj_token = re.sub(r'[\\/*?:"<>|()]', '', subj).strip().replace(" ", "_")
            return f"{self.lecture_number}-{subj_token}_{self.lecture_number}"
        if self.date:
            return str(self.date)
        return "تاريخ_غير_محدد"

    @property
    def resolved_subject(self) -> str:
        """Returns subject_name, keyword, or generic fallback."""
        return self.subject_name or self.keyword or "المادة"

    def merge(self, other: LectureIdentity | dict | None) -> LectureIdentity:
        """
        Returns a new LectureIdentity where non-empty fields from other override self,
        while fields not specified in other are preserved from self.
        """
        if not other:
            return self
        get_val = (lambda k: other.get(k)) if hasattr(other, 'get') else (lambda k: getattr(other, k, None))

        other_date = get_val("date")
        other_lec = get_val("lecture_number")
        has_other_date = other_date is not None and str(other_date).strip() != ""
        has_other_lec = other_lec is not None and str(other_lec).strip() != ""

        if has_other_lec and not has_other_date:
            target_date = None
            target_lec = str(other_lec)
        elif has_other_date and not has_other_lec:
            target_date = str(other_date)
            target_lec = None
        elif has_other_date and has_other_lec:
            target_date = str(other_date)
            target_lec = str(other_lec)
        else:
            target_date = self.date
            target_lec = self.lecture_number

        def _pick(field: str) -> str | None:
            val_other = get_val(field)
            if val_other is not None and str(val_other).strip() != "":
                return str(val_other)
            return getattr(self, field)

        return LectureIdentity(
            date=target_date,
            lecture_number=target_lec,
            keyword=_pick("keyword"),
            subject_name=_pick("subject_name"),
            audio_file=_pick("audio_file"),
            stem=_pick("stem"),
        )

    def matches(
        self,
        candidate_name: str,
        routing_map: dict[str, str] | None = None,
    ) -> bool:
        """
        Determines if candidate_name matches this lecture's identity,
        supporting exact stem matches, date matches, and mirrored numbered stems.
        """
        cleaned_cand = normalize_stem(candidate_name)

        # 1. Exact stem match
        if self.stem and normalize_stem(self.stem) == cleaned_cand:
            return True

        def _normalize_token(t: str) -> str:
            t = normalize_arabic(t)
            t = re.sub(r'ة', 'ه', t)
            t = re.sub(r'ى', 'ي', t)
            t = re.sub(r'[_\s]+', ' ', t)
            return t.strip()

        rm = routing_map if routing_map is not None else CANONICAL_ROUTING

        seed_tokens: set[str] = set()
        if self.keyword:
            seed_tokens.add(_normalize_token(self.keyword))
        if self.subject_name:
            norm_subj = _normalize_token(self.subject_name)
            if norm_subj:
                seed_tokens.add(norm_subj)
            clean_sub = re.sub(r'\(.*?\)', '', self.subject_name).strip()
            norm_clean = _normalize_token(clean_sub)
            if norm_clean:
                seed_tokens.add(norm_clean)

        kw_variants: set[str] = set(seed_tokens)
        for k, v in rm.items():
            k_norm = _normalize_token(k)
            v_norm = _normalize_token(v)
            for st in list(seed_tokens):
                if st == k_norm or st == v_norm:
                    kw_variants.add(k_norm)
                    kw_variants.add(v_norm)
                elif len(st) >= 3 and (st in v_norm or v_norm in st):
                    kw_variants.add(k_norm)
                    kw_variants.add(v_norm)


        # 2. Date-based matching (YYYY-MM-DD)
        if self.date and re.match(r'^\d{4}-\d{2}-\d{2}$', str(self.date)):
            if str(self.date) not in candidate_name:
                return False
            if not kw_variants:
                return True
            stem_rem = cleaned_cand.replace(str(self.date), " ").strip(" _-")
            norm_rem = _normalize_token(stem_rem)
            return any(v in norm_rem for v in kw_variants)

        # 3. Numbered stem matching
        target_num = self.lecture_number or (str(self.date) if self.date and str(self.date).isdigit() else None)
        if not target_num and self.stem:
            stem_num_match = re.search(r'\b(\d+)\b', self.stem)
            if stem_num_match:
                target_num = stem_num_match.group(1)

        cand_numbered = re.match(r'^(\d+)[-_](.+?)[-_](\d+)$', cleaned_cand)
        if cand_numbered:
            n1, middle, n2 = cand_numbered.group(1), cand_numbered.group(2), cand_numbered.group(3)
            if n1 == n2:  # Mirrored stem
                if not target_num or str(target_num) != n1:
                    return False
                norm_mid = _normalize_token(middle)
                return any(v in norm_mid or norm_mid in v for v in kw_variants)

        # 4. Fallback: check if target_num and keyword variant appear in cleaned_cand
        if target_num:
            cand_numbers = re.findall(r'\b\d+\b', cleaned_cand)
            if str(target_num) in cand_numbers:
                norm_cand = _normalize_token(cleaned_cand)
                return any(v in norm_cand for v in kw_variants)

        return False

    @classmethod
    def from_metadata(
        cls,
        meta: dict | LectureIdentity,
        routing_map: dict[str, str] | None = None,
    ) -> LectureIdentity:
        """Constructs LectureIdentity from metadata dict or existing instance."""
        if isinstance(meta, LectureIdentity):
            return meta
        return cls(
            date=meta.get("date"),
            lecture_number=meta.get("lecture_number"),
            keyword=meta.get("keyword"),
            subject_name=meta.get("subject_name"),
            audio_file=meta.get("audio_file"),
            stem=meta.get("stem"),
        )

    @classmethod
    def from_text(
        cls,
        text: str,
        routing_map: dict[str, str] | None = None,
    ) -> LectureIdentity:
        """
        Extracts date, keyword, audio_file, clean canonical subject_name,
        and lecture_number from markdown text, filenames, or raw transcript headers.
        """
        rm = routing_map if routing_map is not None else CANONICAL_ROUTING
        identity = cls()

        # 1. Date extraction (YYYY-MM-DD)
        date_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text)
        if date_match:
            identity.date = date_match.group(1)

        # 2. Lecture number from explicit label (المحاضرة: 17)
        lec_match = re.search(r'^(?:المحاضرة|محاضرة|الدرس|درس)\s*:\s*(\d+)', text, re.MULTILINE)
        if lec_match:
            identity.lecture_number = lec_match.group(1).strip()

        # 3. Audio file token extraction
        audio_match = re.search(r'\b(\d{4}-\d{2}-\d{2}[ _]+[^\n\r]+?\.(?:mp3|m4a|wav|aac|ogg|opus))\b', text, re.IGNORECASE)
        if not audio_match:
            audio_match = re.search(r'\b([^\n\r]+?\.(?:mp3|m4a|wav|aac|ogg|opus))\b', text, re.IGNORECASE)
        if audio_match:
            identity.audio_file = audio_match.group(1).strip()

        # 4. Mirrored numbered stem pattern (e.g. 17-فقه_البيوع_17 or 17-بيوع-17)
        numbered_stem_match = re.search(r'\b(\d+)[-_]([^\s\d\n\r]+?)[-_](\d+)\b', text)
        if numbered_stem_match:
            n1 = numbered_stem_match.group(1)
            stem_middle = numbered_stem_match.group(2).strip()
            n2 = numbered_stem_match.group(3)
            if n1 == n2:
                identity.lecture_number = n1
                identity.stem = f"{n1}-{stem_middle}_{n2}"
                if not identity.keyword:
                    clean_middle = stem_middle.replace("_", " ").strip()
                    canonical_key, canonical_subj = match_canonical_subject(clean_middle, rm)
                    if canonical_key:
                        identity.keyword = canonical_key
                        identity.subject_name = canonical_subj
                    else:
                        identity.keyword = clean_middle

        # 5. Subject extraction from explicit label (المادة: ...)
        subject_match = re.search(r'^(?:اسم المادة|المادة)\s*:\s*([^\n\r]+)', text, re.MULTILINE)
        if subject_match:
            full_subject = subject_match.group(1).strip()
            first_word = re.split(r'[\s(]', full_subject)[0].strip()
            norm_key = normalize_arabic(first_word)
            if norm_key in rm:
                identity.keyword = first_word
                identity.subject_name = rm[norm_key]
            else:
                canonical_key, canonical_subj = match_canonical_subject(full_subject, rm)
                if canonical_key:
                    identity.keyword = canonical_key
                    identity.subject_name = canonical_subj
                else:
                    clean_sub = re.sub(r'\s*\([^)]*فصل[^)]*\)', '', full_subject).strip()
                    identity.keyword = first_word
                    identity.subject_name = clean_sub

        # 6. Filename token fallback if subject line not present
        if not identity.keyword and identity.date:
            file_token_match = re.search(r'\b\d{4}-\d{2}-\d{2}\s+([^\s.]+)(?:\.mp3|\.m4a|\.wav|\.aac|\.ogg)?', text)
            if file_token_match:
                identity.keyword = file_token_match.group(1).strip()
                norm_key = normalize_arabic(identity.keyword)
                if norm_key in rm:
                    identity.subject_name = rm[norm_key]
                else:
                    identity.subject_name = identity.keyword

        # 7. Reverse lookup from audio file if keyword still missing
        if not identity.keyword and identity.audio_file:
            canonical_key, canonical_subj = match_canonical_subject(identity.audio_file, rm)
            if canonical_key:
                identity.keyword = canonical_key
                identity.subject_name = canonical_subj

        return identity

    @classmethod
    def from_filename(
        cls,
        filename: str,
        fallback_subject: str | None = None,
        routing_map: dict[str, str] | None = None,
    ) -> LectureIdentity:
        """Parses identity from a standalone filename."""
        cleaned = normalize_stem(filename)
        identity = cls.from_text(cleaned, routing_map=routing_map)
        identity.stem = cleaned
        if fallback_subject and not identity.subject_name:
            identity.subject_name = fallback_subject
        if fallback_subject and not identity.keyword:
            identity.keyword = fallback_subject
        return identity
