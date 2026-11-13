"""Lazy immutable Workspace Configuration and Unified Rule Catalog seam."""

from __future__ import annotations

import os
import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from .arabic_normalizer import normalize_arabic, normalize_arabic_token, strip_tashkeel

_SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DIALECT_RULES = _SKILL_ROOT / "references" / "dialect-rules.md"

_BASE_DIALECT_MARKERS: frozenset[str] = frozenset({
    "كدا", "كده", "ده", "دا", "دي", "ايه", "إيه", "ازاي", "ازاى", "احنا", "إحنا",
    "برضه", "برضو", "علطول", "أومال", "امال", "مش", "عشان", "علشان", "بقى",
    "مفيش", "مافيش", "مكانش", "ماكانش", "حد", "تاني", "قوي", "خالص", "يلا",
    "طب", "طيب", "يعني", "حاجة", "بتاع", "اللي", "دلوقتي", "عاوز", "عايز", "عايزة",
    "بيقول", "يقولوا", "شوية", "تلاقي", "طبعا", "أهو", "اهو", "يبقى", "ماشي", "بقول",
    "ولواحد",
})

_DEFAULT_PLACEHOLDER = "فلان"
_DEFAULT_KINSHIP_NOUNS: frozenset[str] = frozenset({
    "أخوكم", "اخوكم", "أخونا", "اخونا", "الأخ", "الاخ", "الأخت", "الاخت",
})
_DEFAULT_KUNYA_PREFIXES: frozenset[str] = frozenset({
    "أبو", "ابو", "أبا", "ابا",
})
_DEFAULT_TITLE_PREFIXES: frozenset[str] = frozenset({
    "شيخ", "الشيخ", "دكتور", "الدكتور",
})
_DEFAULT_EXEMPT_NAMES: frozenset[str] = frozenset({
    "زيد", "عمرو", "بكر", "هند", "جحا", "إبراهيم",
})
_DEFAULT_KNOWN_ATTENDEE_NAMES: frozenset[str] = frozenset({
    "معاذ", "طارق", "سارة",
})
_DEFAULT_KINSHIP_STOPWORDS: frozenset[str] = frozenset({
    "ده", "في", "هنا", "هناك", "بيسأل", "يسأل", "قال", "بيقول", "يقول",
    "بتاع", "عايز", "عاوز", "طلب", "بعث", "بعت", "كاتب", "كتب", "اللي",
    "المسلم", "المؤمن", "الصعيدي", "الصييت", "الطالب", "الحاضر", "السائل",
    "المصري", "التاني", "بقى", "على", "يعني", "أحد", "يبقى", "وجاي", "واعتذر",
    "بيتساءل", "بتقول", "بيضرب", "عمال",
})
_DEFAULT_VOCATIVE_STOPWORDS: frozenset[str] = frozenset({
    "سيدي", "سيدنا", "ابني", "بني", "أخي", "أخانا", "أخونا", "أخويا", "اخويا",
    "جماعة", "إخواننا", "إخواني", "شباب", "ولاد", "أولاد", "أستاذ", "أستاذنا", "مولانا",
    "شيخنا", "عم", "رب", "ربنا", "ربي", "الله", "رسول", "نبي", "بشر",
    "ناس", "طالب", "طلاب", "حبيبي", "حبيبنا", "بشمهندس", "مهندس",
    "جميل", "عسل", "عساسيل", "عسايل", "حلويات", "إما", "اما", "إيه", "ايه", "ولا",
    "قول", "سؤال", "سلام", "نهار", "ابن", "واد", "كمن", "اللي", "ليتني", "ذا", "روح",
})
_ILLUSTRATION_ACTIONS = (
    r"(?:ب?[يت]عمل|ب?[يت]سأل|ب?[يت]قول|قال[ت]?|عايز[ةه]?|عاوز[ةه]?|"
    r"قاعد[ةه]?|واقف[ةه]?|نايم[ةه]?|جه|جا[تت]|راح[ت]?|شايف[ةه]?|سامع[ةه]?)"
)


def _discover_repo_root(start_dir: Path | None = None) -> Path:
    """Discovers the Tafreegh repository root lazily from cwd or package ancestors."""
    candidates: list[Path] = []
    if start_dir is not None:
        resolved_start = Path(start_dir)
        candidates.extend([resolved_start, *resolved_start.parents])
    package_anchor = Path(__file__).resolve()
    candidates.extend(package_anchor.parents)

    for directory in candidates:
        context_file = directory / "CONTEXT.md"
        if context_file.is_file():
            return directory

    return _SKILL_ROOT.parent.parent.parent


def _pick_path_override(
    explicit: Path | str | None,
    env: Mapping[str, str],
    env_key: str,
) -> Path | None:
    if explicit is not None and str(explicit).strip():
        return Path(explicit)
    env_val = env.get(env_key)
    if env_val is not None and env_val.strip():
        return Path(env_val.strip())
    return None


def _resolve_existing_or_fallback(
    explicit: Path | str | None,
    env: Mapping[str, str],
    env_key: str,
    local_candidate: Path,
    repo_fallback: Path,
) -> Path:
    override = _pick_path_override(explicit, env, env_key)
    if override is not None:
        return override
    if local_candidate.is_file():
        return local_candidate
    if repo_fallback.is_file():
        return repo_fallback
    return local_candidate


@dataclass(frozen=True)
class WorkspaceConfig:
    """Immutable resolved directory layout and steering document paths."""

    project_root: Path
    onedrive_base: Path
    matn_sources_dir: Path
    raw_inputs_dir: Path
    ai_outputs_dir: Path
    training_data_dir: Path
    context_path: Path
    dialect_rules_path: Path
    word_base_template: Path

    @classmethod
    def resolve(
        cls,
        *,
        project_root: Path | str | None = None,
        onedrive_base: Path | str | None = None,
        matn_sources_dir: Path | str | None = None,
        raw_inputs_dir: Path | str | None = None,
        ai_outputs_dir: Path | str | None = None,
        training_data_dir: Path | str | None = None,
        context_path: Path | str | None = None,
        dialect_rules_path: Path | str | None = None,
        word_base_template: Path | str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> WorkspaceConfig:
        """Resolves workspace roots lazily via explicit args > env vars > repo discovery."""
        active_env = os.environ if env is None else env
        active_cwd = Path.cwd() if cwd is None else Path(cwd)
        discovered_root = _discover_repo_root(active_cwd)

        resolved_root = (
            _pick_path_override(project_root, active_env, "TAFREEGH_PROJECT_ROOT")
            or discovered_root
        )
        resolved_onedrive = (
            _pick_path_override(onedrive_base, active_env, "TAFREEGH_ONEDRIVE_BASE")
            or (Path.home() / "OneDrive" / "1. دوري")
        )

        resolved_matn = (
            _pick_path_override(matn_sources_dir, active_env, "TAFREEGH_MATN_SOURCES_DIR")
            or (resolved_root / "01_Matn_Sources")
        )
        resolved_raw = (
            _pick_path_override(raw_inputs_dir, active_env, "TAFREEGH_RAW_INPUTS_DIR")
            or (resolved_root / "02_Raw_Inputs")
        )
        resolved_ai = (
            _pick_path_override(ai_outputs_dir, active_env, "TAFREEGH_AI_OUTPUTS_DIR")
            or (resolved_root / "03_AI_Outputs")
        )
        resolved_training = (
            _pick_path_override(training_data_dir, active_env, "TAFREEGH_TRAINING_DATA_DIR")
            or (resolved_root / "04_Training_Data")
        )

        resolved_context = _resolve_existing_or_fallback(
            context_path,
            active_env,
            "TAFREEGH_CONTEXT_PATH",
            resolved_root / "CONTEXT.md",
            discovered_root / "CONTEXT.md",
        )
        resolved_dialect = _resolve_existing_or_fallback(
            dialect_rules_path,
            active_env,
            "TAFREEGH_DIALECT_RULES_PATH",
            resolved_root / ".agents" / "skills" / "tafreegh" / "references" / "dialect-rules.md",
            _DEFAULT_DIALECT_RULES,
        )
        resolved_template = _resolve_existing_or_fallback(
            word_base_template,
            active_env,
            "TAFREEGH_WORD_BASE_TEMPLATE",
            resolved_root / "Word base.docx",
            discovered_root / "Word base.docx",
        )

        return cls(
            project_root=resolved_root,
            onedrive_base=resolved_onedrive,
            matn_sources_dir=resolved_matn,
            raw_inputs_dir=resolved_raw,
            ai_outputs_dir=resolved_ai,
            training_data_dir=resolved_training,
            context_path=resolved_context,
            dialect_rules_path=resolved_dialect,
            word_base_template=resolved_template,
        )


@dataclass(frozen=True)
class CanonicalCourseEntry:
    """One row from the CONTEXT.md Section 3 routing table including keyword aliases."""

    canonical_subject: str
    primary_keyword: str
    keywords: tuple[str, ...]
    aliases: tuple[str, ...]
    matn_source: str = ""

    def folder_search_candidates(self, query_keyword: str | None = None) -> tuple[str, ...]:
        """Returns ordered folder search candidates starting from query/primary keyword."""
        ordered: list[str] = []
        seen: set[str] = set()
        raw_items = [
            query_keyword or "",
            self.primary_keyword,
            self.canonical_subject,
            *self.keywords,
            *self.aliases,
        ]
        for item in raw_items:
            cleaned = normalize_arabic(item)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                ordered.append(cleaned)
        return tuple(ordered)


@dataclass(frozen=True)
class AttendeeAnonymizationRules:
    """Immutable attendee anonymization lexicons, stopwords, and leak detector."""

    placeholder: str = _DEFAULT_PLACEHOLDER
    kinship_nouns: frozenset[str] = _DEFAULT_KINSHIP_NOUNS
    kunya_prefixes: frozenset[str] = _DEFAULT_KUNYA_PREFIXES
    title_prefixes: frozenset[str] = _DEFAULT_TITLE_PREFIXES
    exempt_names: frozenset[str] = _DEFAULT_EXEMPT_NAMES
    kinship_stopwords: frozenset[str] = _DEFAULT_KINSHIP_STOPWORDS
    vocative_stopwords: frozenset[str] = _DEFAULT_VOCATIVE_STOPWORDS
    known_attendee_names: frozenset[str] = _DEFAULT_KNOWN_ATTENDEE_NAMES

    @classmethod
    def baseline(cls) -> AttendeeAnonymizationRules:
        """Returns the immutable baseline attendee anonymization ruleset."""
        return cls()

    def is_vocative_non_name(self, token: str) -> bool:
        """Returns True when a vocative token is a grammatical expression rather than a name."""
        if token in self.vocative_stopwords:
            return True
        if token.endswith(("وك", "ها", "هم", "كم")):
            return True
        return bool(re.match(r"^ت[\u0621-\u064A]{3,}ه$", token))

    def find_leaks(self, text: str) -> list[tuple[str, str]]:
        """Scans stripped prose for unanonymized kinship, classroom vocative, and illustration attendee references."""
        all_prefixes = sorted(self.kunya_prefixes | self.title_prefixes, key=len, reverse=True)
        prefix_alt = "|".join(re.escape(p) for p in all_prefixes)
        kinship_alt = "|".join(
            re.escape(k) for k in sorted(self.kinship_nouns, key=len, reverse=True)
        )
        prefix_group = rf"(?:(?:{prefix_alt})\s+)*" if prefix_alt else ""
        voc_prefix_group = rf"(?:(?P<prefix>{prefix_alt})\s+)?" if prefix_alt else ""

        leaks: list[tuple[str, str]] = []
        matched_spans: list[tuple[int, int]] = []

        def _overlaps(start: int, end: int) -> bool:
            return any(max(start, s) < min(end, e) for s, e in matched_spans)

        if kinship_alt:
            kinship_re = re.compile(
                rf"(?<!\w)[وف]?(?:{kinship_alt})\s+(?P<prefixes>{prefix_group})(?P<cand>[\u0621-\u064A]{{3,}})(?!\w)"
            )
            for m_kin in kinship_re.finditer(text):
                cand = m_kin.group("cand")
                prefix_tokens = m_kin.group("prefixes").split()
                has_kunya = any(p in self.kunya_prefixes for p in prefix_tokens)
                if cand == self.placeholder:
                    continue
                if not has_kunya and (cand in self.exempt_names or cand in self.kinship_stopwords):
                    continue
                matched_spans.append((m_kin.start(), m_kin.end()))
                leaks.append(("reference", m_kin.group(0)))

        vocative_re = re.compile(
            rf"(?<!\w)[وف]?(?P<trig>ولا\s+(?:إيه|ايه)|إيه|ايه|ها|قول|اتفضل|تفضل|نعم|ماشي|صح|فاهم)\s+يا\s+"
            rf"{voc_prefix_group}(?P<cand>[\u0621-\u064A]{{3,}})(?!\w)"
        )
        for m_voc in vocative_re.finditer(text):
            cand = m_voc.group("cand")
            prefix = m_voc.groupdict().get("prefix")
            trig = m_voc.group("trig").strip()
            if cand == self.placeholder:
                continue
            if prefix and prefix in self.kunya_prefixes:
                # Exempt Egyptian rhetorical topical echo: '<word> إيه يا أبو <word>'
                pre_window = text[max(0, m_voc.start() - 35) : m_voc.start()]
                if trig in ("إيه", "ايه") and re.search(
                    rf"(?<!\w)(?:[وفبكل]?ال|[وفبكل])?{re.escape(cand)}(?!\w)", pre_window
                ):
                    continue
                if not _overlaps(m_voc.start(), m_voc.end()):
                    matched_spans.append((m_voc.start(), m_voc.end()))
                    leaks.append(("vocative", m_voc.group(0)))
                continue
            if cand in self.exempt_names or cand in self.title_prefixes or self.is_vocative_non_name(cand):
                continue
            if not _overlaps(m_voc.start(), m_voc.end()):
                matched_spans.append((m_voc.start(), m_voc.end()))
                leaks.append(("vocative", m_voc.group(0)))

        cand_names = sorted(
            [n for n in self.known_attendee_names if n != self.placeholder and n not in self.exempt_names],
            key=len,
            reverse=True,
        )
        if cand_names:
            cand_alt = "|".join(re.escape(n) for n in cand_names)
            quote_spans = [(m.start(), m.end()) for m in re.finditer(r'«[^»]*»|"[^"]*"', text)]
            bare_voc_re = re.compile(
                rf"(?<!\w)[وف]?(?:يا|يَا)\s+{prefix_group}(?P<cand>{cand_alt})(?!\w)"
            )
            for m_bvoc in bare_voc_re.finditer(text):
                if _overlaps(m_bvoc.start(), m_bvoc.end()):
                    continue
                if any(qs <= m_bvoc.start() and m_bvoc.end() <= qe for qs, qe in quote_spans):
                    continue
                tail_stripped = strip_tashkeel(text[m_bvoc.end():])
                if re.match(r"^\s*(?:بن|ابن)\s+[\u0621-\u064A]{2,}", tail_stripped):
                    continue
                matched_spans.append((m_bvoc.start(), m_bvoc.end()))
                leaks.append(("vocative", m_bvoc.group(0)))

            illustration_patterns = [
                re.compile(
                    rf"(?<!\w){prefix_group}(?P<cand>{cand_alt})\s+{_ILLUSTRATION_ACTIONS}(?!\w)"
                ),
                re.compile(
                    rf"(?<!\w)(?:مثل[اً]?|زي)\s*:\s*{prefix_group}(?P<cand>{cand_alt})(?!\w)"
                ),
                re.compile(
                    rf"(?<!\w)زي\s+ما\s+(?:قال[ت]?|ب?[يت]قول)\s+{prefix_group}(?P<cand>{cand_alt})(?!\w)"
                ),
            ]
            for pat in illustration_patterns:
                for m_ill in pat.finditer(text):
                    if _overlaps(m_ill.start(), m_ill.end()):
                        continue
                    matched_spans.append((m_ill.start(), m_ill.end()))
                    leaks.append(("reference", m_ill.group(0)))

        return leaks


def _expand_course_aliases(tokens: list[str], canonical_name: str) -> tuple[str, ...]:
    aliases: list[str] = []
    seen: set[str] = set()

    def _add(val: str) -> None:
        if val and val not in seen:
            seen.add(val)
            aliases.append(val)

    for token in tokens:
        _add(token)
        _add(normalize_arabic(token))
        if "_" in token:
            space_v = token.replace("_", " ").strip()
            _add(space_v)
            _add(normalize_arabic(space_v))
        if " " in token:
            under_v = token.replace(" ", "_").strip()
            _add(under_v)
            _add(normalize_arabic(under_v))
        norm_token = normalize_arabic(token)
        if not norm_token.startswith("ال"):
            al_v = f"ال{token}"
            _add(al_v)
            _add(normalize_arabic(al_v))

    _add(canonical_name)
    _add(normalize_arabic(canonical_name))
    return tuple(aliases)


def _parse_routing_courses(
    context_path: Path,
) -> tuple[tuple[CanonicalCourseEntry, ...], Mapping[str, str]]:
    """Parses CONTEXT.md Section 3 Routing Map into CanonicalCourseEntry rows and routing map."""
    if not context_path.is_file():
        return (), MappingProxyType({})

    lines = context_path.read_text(encoding="utf-8").splitlines()
    has_section_3 = any(
        line.strip().startswith("## 3.") or "توجيه المتون" in line for line in lines
    )
    in_section_3 = False
    in_table = False
    kw_col_idx = 0
    subj_col_idx = 1
    matn_col_idx: int | None = 2
    header_found = False

    courses: list[CanonicalCourseEntry] = []
    routing_dict: dict[str, str] = {}

    for line in lines:
        stripped = line.strip()
        if has_section_3:
            if stripped.startswith("## 3.") or "توجيه المتون" in stripped:
                in_section_3 = True
                continue
            if in_section_3 and stripped.startswith("## "):
                break
            if not in_section_3:
                continue

        if not (stripped.startswith("|") and stripped.endswith("|")):
            if in_table:
                break
            continue

        cells = [c.strip() for c in re.split(r"(?<!\\)\|", stripped)[1:-1]]
        if not cells:
            continue

        if all(re.match(r"^:?-+:?$", c) for c in cells):
            in_table = True
            continue

        if not header_found:
            found_kw = None
            found_subj = None
            found_matn = None
            for idx, cell in enumerate(cells):
                norm_c = normalize_arabic(cell)
                if any(w in norm_c for w in ("الكلمة", "الدلالية", "keyword")):
                    found_kw = idx
                elif any(w in norm_c for w in ("المادة", "المعتمدة", "subject")):
                    found_subj = idx
                elif any(w in norm_c for w in ("المتن", "مصدره", "matn", "source")):
                    found_matn = idx
            if found_kw is not None or found_subj is not None:
                header_found = True
                in_table = True
                if found_kw is not None:
                    kw_col_idx = found_kw
                if found_subj is not None:
                    subj_col_idx = found_subj
                matn_col_idx = found_matn
                continue

        in_table = True
        keyword_cell = cells[kw_col_idx] if kw_col_idx < len(cells) else cells[0]
        subject_cell = (
            cells[subj_col_idx]
            if subj_col_idx < len(cells)
            else (cells[1] if len(cells) > 1 else cells[0])
        )
        matn_cell = (
            cells[matn_col_idx]
            if matn_col_idx is not None and matn_col_idx < len(cells)
            else ""
        )

        bold_match = re.search(r"\*\*([^*]+)\*\*", subject_cell)
        if bold_match:
            canonical_name = bold_match.group(1).strip()
        else:
            clean_sub = re.sub(r"\s*\(للإمام[^)]*\)", "", subject_cell)
            clean_sub = re.sub(r"\s*\(للشيخ[^)]*\)", "", clean_sub)
            canonical_name = clean_sub.strip()

        raw_tokens = re.findall(r"`?\(?([^`()/]+)\)?`?", keyword_cell)
        tokens = [t.strip("`() /") for t in raw_tokens if t.strip("`() /")]
        aliases = _expand_course_aliases(tokens, canonical_name)

        entry = CanonicalCourseEntry(
            canonical_subject=canonical_name,
            primary_keyword=tokens[0] if tokens else canonical_name,
            keywords=tuple(tokens),
            aliases=aliases,
            matn_source=matn_cell,
        )
        courses.append(entry)
        for alias in aliases:
            routing_dict[alias] = canonical_name

    return tuple(courses), MappingProxyType(routing_dict)


def _parse_dialect_rules(
    rules_path: Path,
) -> tuple[
    frozenset[str],
    tuple[tuple[re.Pattern[str], str], ...],
    AttendeeAnonymizationRules,
]:
    """Parses references/dialect-rules.md once into markers, replacements, and attendee rules."""
    if not rules_path.is_file():
        warnings.warn(
            f"Dialect rules file not found at {rules_path}; using baseline attendee anonymization rules.",
            UserWarning,
            stacklevel=3,
        )
        return _BASE_DIALECT_MARKERS, (), AttendeeAnonymizationRules.baseline()

    text = rules_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    markers: set[str] = set()
    in_lexicon = False
    replacements: list[tuple[re.Pattern[str], str]] = []
    fused_particles: set[str] = set()

    placeholder = _DEFAULT_PLACEHOLDER
    header_m = re.search(r"^##\s+Attendee Anonymization\s*\(([\u0621-\u064A]+)\)", text, re.MULTILINE)
    if header_m:
        placeholder = header_m.group(1)

    kinship_nouns: set[str] = set()
    kunya_prefixes: set[str] = set()
    title_prefixes: set[str] = set()
    exempt_names: set[str] = set()
    known_attendee_names: set[str] = set(_DEFAULT_KNOWN_ATTENDEE_NAMES)

    for line in lines:
        stripped = line.strip()

        # Section tracking for colloquial markers
        if stripped.startswith("## "):
            if "Colloquial Lexicon" in stripped:
                in_lexicon = True
                continue
            in_lexicon = False

        if in_lexicon:
            for bold_token in re.findall(r"\*\*([^*]+)\*\*", stripped):
                if not re.search(r"[\u0600-\u06FF]", bold_token):
                    continue
                for word in re.findall(r"\w+", bold_token):
                    if re.search(r"[\u0600-\u06FF]", word):
                        markers.add(word.strip())

        # Table replacements
        if stripped.startswith("|") and "**" in stripped:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) >= 2:
                raw_col, target_col = cells[0], cells[1]
                target_m = re.search(r"\*\*(.+?)\*\*", target_col)
                if target_m:
                    target = target_m.group(1).strip()
                    raw_without_placeholders = re.sub(r"\[[^\]]*\]", "", raw_col).strip()
                    if raw_without_placeholders:
                        variants = []
                        for v in raw_without_placeholders.split("/"):
                            v_clean = v.strip()
                            if not v_clean or any(ch in v_clean for ch in "[]()") or v_clean == target:
                                continue
                            variants.append(re.sub(r"\s+", r"\\s+", re.escape(v_clean)))
                        if variants:
                            joined = "|".join(variants) if len(variants) > 1 else variants[0]
                            replacements.append((re.compile(rf"(?<!\w)(?:{joined})(?!\w)"), target))
            continue

        if "Fused Negation Particles" in stripped:
            tokens = [m[0] or m[1] for m in re.findall(r"\*\*([^*]+)\*\*|`([^`]+)`", stripped)]
            for tok in tokens:
                tok_clean = tok.strip()
                if not re.search(r"[\u0600-\u06FF]", tok_clean):
                    continue
                fused_particles.add(tok_clean)
                if tok_clean.startswith("م") and not tok_clean.startswith("ما"):
                    unfused = "ما" + tok_clean[1:]
                    fused_particles.add(unfused)
                    replacements.append((re.compile(rf"(?<!\w){re.escape(unfused)}(?!\w)"), tok_clean))
        elif "Compound Verb Negation" in stripped:
            tokens = [m[0] or m[1] for m in re.findall(r"\*\*([^*]+)\*\*|`([^`]+)`", stripped)]
            for tok in tokens:
                tok_clean = tok.strip()
                if tok_clean.startswith("ما ") and tok_clean.endswith("ش") and "[" not in tok_clean and "+" not in tok_clean:
                    joined_form = tok_clean.replace(" ", "")
                    replacements.append((re.compile(rf"(?<!\w){re.escape(joined_form)}(?!\w)"), tok_clean))

            if fused_particles:
                excl = "|".join(re.escape(fp) for fp in sorted(fused_particles))
                comp_pat = re.compile(rf"(?<!\w)(?!(?:{excl})(?!\w))ما([\u0600-\u06FF]{{2,}})ش(?!\w)")
            else:
                comp_pat = re.compile(r"(?<!\w)ما([\u0600-\u06FF]{2,})ش(?!\w)")
            replacements.append((comp_pat, r"ما \1ش"))
        elif "Preserved Titles & Kunyas" in stripped:
            clean_line = stripped.replace("**", "")
            for tok in re.findall(rf"([\u0621-\u064A]+)\s+{re.escape(placeholder)}(?!\w)", clean_line):
                if tok == "يا":
                    continue
                dehamza = normalize_arabic(tok)
                if dehamza.startswith("اخو"):
                    kinship_nouns.update({"أخوكم", "اخوكم", "أخونا", "اخونا", tok, dehamza})
                elif dehamza in ("الاخ", "الاخت"):
                    kinship_nouns.update({tok, dehamza})
                elif dehamza in ("ابو", "ابا"):
                    hamza_form = f"أ{dehamza[1:]}"
                    kunya_prefixes.update({tok, dehamza, hamza_form})
                else:
                    base = tok[2:] if tok.startswith("ال") and len(tok) >= 5 else tok
                    definite = tok if tok.startswith("ال") else f"ال{tok}"
                    title_prefixes.update({
                        base,
                        definite,
                        normalize_arabic(base),
                        normalize_arabic(definite),
                    })
        elif "Preserved Non-Attendee Names" in stripped:
            for grp in re.findall(r"\(([^)]+)\)", stripped):
                exempt_names.update(re.findall(r"[\u0621-\u064A]+", grp))
        elif "Known Attendee Names" in stripped:
            parsed_known: set[str] = set()
            for grp in re.findall(r"\(([^)]+)\)", stripped):
                parsed_known.update(re.findall(r"[\u0621-\u064A]+", grp))
            if parsed_known:
                known_attendee_names = parsed_known

    if not kinship_nouns or not kunya_prefixes or not title_prefixes or not exempt_names:
        warnings.warn(
            f"Attendee anonymization rules parsed from {rules_path} produced empty rule set(s); falling back to baseline rules.",
            UserWarning,
            stacklevel=3,
        )
        if not kinship_nouns:
            kinship_nouns.update(_DEFAULT_KINSHIP_NOUNS)
        if not kunya_prefixes:
            kunya_prefixes.update(_DEFAULT_KUNYA_PREFIXES)
        if not title_prefixes:
            title_prefixes.update(_DEFAULT_TITLE_PREFIXES)
        if not exempt_names:
            exempt_names.update(_DEFAULT_EXEMPT_NAMES)

    attendee_rules = AttendeeAnonymizationRules(
        placeholder=placeholder,
        kinship_nouns=frozenset(kinship_nouns),
        kunya_prefixes=frozenset(kunya_prefixes),
        title_prefixes=frozenset(title_prefixes),
        exempt_names=frozenset(exempt_names),
        kinship_stopwords=_DEFAULT_KINSHIP_STOPWORDS,
        vocative_stopwords=_DEFAULT_VOCATIVE_STOPWORDS,
        known_attendee_names=frozenset(known_attendee_names),
    )
    return frozenset(_BASE_DIALECT_MARKERS | markers), tuple(replacements), attendee_rules


@dataclass(frozen=True)
class RuleCatalog:
    """Lazy, immutable snapshot of all Tafreegh steering rules."""

    courses: tuple[CanonicalCourseEntry, ...] = ()
    routing_map: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    canonical_subjects: frozenset[str] = field(default_factory=frozenset)
    dialect_markers: frozenset[str] = _BASE_DIALECT_MARKERS
    dialect_replacements: tuple[tuple[re.Pattern[str], str], ...] = ()
    attendee_rules: AttendeeAnonymizationRules = field(
        default_factory=AttendeeAnonymizationRules.baseline
    )

    @classmethod
    def load(
        cls,
        *,
        context_path: Path | str | None = None,
        dialect_rules_path: Path | str | None = None,
        workspace: WorkspaceConfig | None = None,
    ) -> RuleCatalog:
        """Lazily reads and parses steering documents into an immutable RuleCatalog."""
        if workspace is None and (context_path is None or dialect_rules_path is None):
            workspace = WorkspaceConfig.resolve(
                context_path=context_path,
                dialect_rules_path=dialect_rules_path,
            )

        resolved_context = (
            Path(context_path)
            if context_path is not None
            else workspace.context_path  # type: ignore[union-attr]
        )
        resolved_dialect = (
            Path(dialect_rules_path)
            if dialect_rules_path is not None
            else workspace.dialect_rules_path  # type: ignore[union-attr]
        )

        courses, routing_map = _parse_routing_courses(resolved_context)
        canonical_subjects = frozenset(c.canonical_subject for c in courses)
        dialect_markers, dialect_replacements, attendee_rules = _parse_dialect_rules(
            resolved_dialect
        )
        return cls(
            courses=courses,
            routing_map=routing_map,
            canonical_subjects=canonical_subjects,
            dialect_markers=dialect_markers,
            dialect_replacements=dialect_replacements,
            attendee_rules=attendee_rules,
        )

    def match_subject(self, text: str) -> tuple[str | None, str | None]:
        """Matches text against canonical routing keys in descending length order."""
        if not text:
            return None, None
        norm_text = normalize_arabic(text)
        for key in sorted(self.routing_map.keys(), key=len, reverse=True):
            if normalize_arabic(key) in norm_text:
                return key, self.routing_map[key]
        return None, None

    def resolve_course(self, keyword_or_subject: str) -> CanonicalCourseEntry | None:
        """Resolves a keyword, alias, or canonical subject name to its CanonicalCourseEntry."""
        if not keyword_or_subject:
            return None
        cleaned = normalize_arabic(keyword_or_subject)
        token_norm = normalize_arabic_token(keyword_or_subject)

        canonical = (
            self.routing_map.get(keyword_or_subject)
            or self.routing_map.get(cleaned)
        )
        if canonical is None:
            for course in self.courses:
                if any(normalize_arabic_token(a) == token_norm for a in course.aliases):
                    return course
            _, matched_subj = self.match_subject(keyword_or_subject)
            canonical = matched_subj

        if canonical is None:
            return None
        return next(
            (c for c in self.courses if c.canonical_subject == canonical),
            None,
        )

    def resolve_onedrive_folder(self, keyword: str, base_path: Path) -> Path:
        """Resolves the target OneDrive folder using per-row keyword alias groups."""
        cleaned = normalize_arabic(keyword)
        if not cleaned:
            return base_path / "عام"

        course = self.resolve_course(cleaned)
        candidates = (
            course.folder_search_candidates(cleaned)
            if course is not None
            else (cleaned,)
        )

        if base_path.exists() and base_path.is_dir():
            dirs = [d for d in base_path.iterdir() if d.is_dir()]
            dir_tokens = [
                (d, normalize_arabic_token(d.name), set(normalize_arabic_token(d.name).split()))
                for d in dirs
            ]
            # 1. Prefer exact token or definite-article token matches across candidates
            for cand in candidates:
                cand_tok = normalize_arabic_token(cand)
                if not cand_tok:
                    continue
                cand_variants = {cand_tok}
                if not cand_tok.startswith("ال"):
                    cand_variants.add(f"ال{cand_tok}")
                for d, d_norm, d_words in dir_tokens:
                    if cand_tok == d_norm or (cand_variants & d_words):
                        return d
            # 2. Substring fallback across candidates (e.g., multi-word subject phrase)
            for cand in candidates:
                cand_tok = normalize_arabic_token(cand)
                if not cand_tok:
                    continue
                for d, d_norm, _ in dir_tokens:
                    if cand_tok in d_norm:
                        return d

        fallback_name = course.primary_keyword if course is not None else cleaned
        return base_path / fallback_name
