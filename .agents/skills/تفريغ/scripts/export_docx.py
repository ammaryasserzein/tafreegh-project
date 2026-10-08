from __future__ import annotations

import sys
import re
import shutil
from pathlib import Path
from dataclasses import dataclass
import docx
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

try:
    from matn_matcher import (
        SequentialMatnMatcher,
        MatchMode,
        MatnMatchResult,
        format_matn_segment,
        generate_fallback_summary,
    )
except ImportError:
    try:
        from .matn_matcher import (
            SequentialMatnMatcher,
            MatchMode,
            MatnMatchResult,
            format_matn_segment,
            generate_fallback_summary,
        )
    except ImportError:
        pass

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CANONICAL_SUBJECT_NAMES = {
    "اسماء": "الأسماء الحسنى",
    "أسماء": "الأسماء الحسنى",
    "الاسماء": "الأسماء الحسنى",
    "الأسماء": "الأسماء الحسنى",
    "رياض": "رياض الصالحين",
    "رياض الصالحين": "رياض الصالحين",
    "سيرة": "سيرة (الرحيق المختوم)",
    "السيرة": "سيرة (الرحيق المختوم)",
    "رحيق": "سيرة (الرحيق المختوم)",
    "معاملات": "دليل الطالب (كتاب البيع)",
    "المعاملات": "دليل الطالب (كتاب البيع)",
    "دليل": "دليل الطالب (كتاب البيع)",
    "دليل الطالب": "دليل الطالب (كتاب البيع)",
    "توحيد": "فتح الباري (كتاب التوحيد)",
    "التوحيد": "فتح الباري (كتاب التوحيد)",
    "فتح": "فتح الباري (كتاب التوحيد)",
    "فتح الباري": "فتح الباري (كتاب التوحيد)",
    "لب": "لب الأصول",
    "لب الاصول": "لب الأصول",
    "لب الأصول": "لب الأصول",
    "اصول": "لب الأصول",
    "أصول": "لب الأصول",
    "الاصول": "لب الأصول",
    "الأصول": "لب الأصول",
    "ديوان": "ديوان الشافعي",
    "ديوان الشافعي": "ديوان الشافعي",
    "زاد": "زاد المعاد",
    "زاد المعاد": "زاد المعاد",
    "روضة": "شرح مختصر الروضة",
    "الروضة": "شرح مختصر الروضة",
    "مختصر الروضة": "شرح مختصر الروضة",
    "روضة الناظر": "شرح مختصر الروضة",
    "صيد": "صيد الخاطر",
    "صيد الخاطر": "صيد الخاطر",
    "منطق": "المنطق (السلم المنورق)",
    "المنطق": "المنطق (السلم المنورق)",
    "سلم": "المنطق (السلم المنورق)",
    "السلم": "المنطق (السلم المنورق)",
}

DEFAULT_BASE_ONEDRIVE = Path(r"C:\Users\L\OneDrive\1. دوري")
DEFAULT_PROJECT_ROOT = Path(r"c:\Users\L\Documents\Tafreegh_Project")
WORD_BASE_TEMPLATE = DEFAULT_PROJECT_ROOT / "Word base.docx"
DEFAULT_FONT_NAME = "Traditional Arabic"
DEFAULT_FONT_SIZE = 18

NOTEBOOKLM_HEADER_PATTERNS = [
    re.compile(r'^(?:المصادر|مصادر|المصدر|دليل المصدر|دليل مصادر)$', re.IGNORECASE),
    re.compile(r'^(?:source\s*guide|sources)$', re.IGNORECASE),
    re.compile(r'^\d{4}-\d{2}-\d{2}[ _]+.*\.(?:mp3|m4a|wav|aac|ogg|opus)$', re.IGNORECASE),
    re.compile(r'^.*\.(?:mp3|m4a|wav|aac|ogg|opus)$', re.IGNORECASE),
]


def normalize_arabic(text: str) -> str:
    """Normalizes hamzas, wasl, and cleans leading/trailing whitespace."""
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r'[أإآٱ]', 'ا', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def parse_metadata(text: str) -> dict:
    """
    Extracts date, keyword, audio_file, and clean canonical subject_name
    from markdown text or raw transcript headers.
    """
    metadata = {
        "date": None,
        "keyword": None,
        "subject_name": None,
        "audio_file": None
    }
    
    # 1. Date extraction (YYYY-MM-DD)
    date_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text)
    if date_match:
        metadata["date"] = date_match.group(1)
        
    # 2. Audio file token extraction
    audio_match = re.search(r'\b(\d{4}-\d{2}-\d{2}[ _]+[^\n\r]+?\.(?:mp3|m4a|wav|aac|ogg|opus))\b', text, re.IGNORECASE)
    if not audio_match:
        audio_match = re.search(r'\b([^\n\r]+?\.(?:mp3|m4a|wav|aac|ogg|opus))\b', text, re.IGNORECASE)
    if audio_match:
        metadata["audio_file"] = audio_match.group(1).strip()
        
    # 3. Subject extraction from explicit label
    subject_match = re.search(r'^(?:اسم المادة|المادة)\s*:\s*([^\n\r]+)', text, re.MULTILINE)
    if subject_match:
        full_subject = subject_match.group(1).strip()
        first_word = re.split(r'[\s(]', full_subject)[0].strip()
        metadata["keyword"] = first_word
        
        norm_key = normalize_arabic(first_word)
        if norm_key in CANONICAL_SUBJECT_NAMES:
            metadata["subject_name"] = CANONICAL_SUBJECT_NAMES[norm_key]
        else:
            clean_sub = re.sub(r'\s*\([^)]*فصل[^)]*\)', '', full_subject).strip()
            metadata["subject_name"] = clean_sub
            
    # 4. Filename token fallback if subject line not present
    if not metadata["keyword"] and metadata["date"]:
        file_token_match = re.search(r'\b\d{4}-\d{2}-\d{2}\s+([^\s.]+)(?:\.mp3|\.m4a|\.wav|\.aac|\.ogg)?', text)
        if file_token_match:
            metadata["keyword"] = file_token_match.group(1).strip()
            norm_key = normalize_arabic(metadata["keyword"])
            if norm_key in CANONICAL_SUBJECT_NAMES:
                metadata["subject_name"] = CANONICAL_SUBJECT_NAMES[norm_key]
            else:
                metadata["subject_name"] = metadata["keyword"]
                
    # 5. Reverse lookup from audio file if keyword still missing
    if not metadata["keyword"] and metadata["audio_file"]:
        clean_audio = metadata["audio_file"]
        for key in CANONICAL_SUBJECT_NAMES:
            if key in clean_audio:
                metadata["keyword"] = key
                metadata["subject_name"] = CANONICAL_SUBJECT_NAMES[key]
                break

    return metadata


KEYWORD_FOLDER_HINTS = {
    "دليل": "معاملات",
    "دليل الطالب": "معاملات",
    "رحيق": "سيرة",
    "سلم": "منطق",
    "السلم": "منطق",
    "فتح": "توحيد",
    "فتح الباري": "توحيد",
}

def get_onedrive_folder(keyword: str, base_path: Path = DEFAULT_BASE_ONEDRIVE) -> Path:
    """
    Returns the target OneDrive folder Path for a given discipline keyword.
    Scans the base_path dynamically to find a matching folder.
    """
    cleaned = normalize_arabic(keyword)
    if not cleaned:
        return base_path / "عام"
        
    k_search = KEYWORD_FOLDER_HINTS.get(cleaned, cleaned)
    if base_path.exists() and base_path.is_dir():
        k_clean = k_search.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        for d in base_path.iterdir():
            if d.is_dir():
                d_name_clean = d.name.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
                if k_clean in d_name_clean:
                    return d
                    
    return base_path / cleaned


def is_header_line(line: str) -> bool:
    """Checks if a given line belongs to the standard header block or NotebookLM tags."""
    l = line.strip()
    if not l:
        return True
    if l in ("بسم الله الرحمن الرحيم", "بسم الله الرحمن الرحيم."):
        return True
    if l.startswith("المادة:") or l.startswith("اسم المادة:"):
        return True
    if re.match(r'^\d{4}-\d{2}-\d{2}$', l):
        return True
    for pat in NOTEBOOKLM_HEADER_PATTERNS:
        if pat.match(l):
            return True
    return False


def standardize_transcript_header(markdown_text: str) -> str:
    """
    Strips NotebookLM tags (Source guide, audio file names, etc.) and existing headers,
    returning cleanly standardized markdown beginning with the 3-line centered header.
    """
    meta = parse_metadata(markdown_text)
    clean_subject = meta.get("subject_name") or meta.get("keyword") or "المادة"
    used_date = meta.get("date") or "تاريخ_غير_محدد"
    
    paragraphs = markdown_text.split('\n\n')
    cleaned_paragraphs = []
    
    for para in paragraphs:
        lines = [line.strip() for line in para.split('\n') if line.strip()]
        if not lines:
            continue
        if all(is_header_line(l) for l in lines):
            continue
        while lines and is_header_line(lines[0]):
            lines.pop(0)
        if not lines:
            continue
        cleaned_paragraphs.append('\n'.join(lines))
        
    body = '\n\n'.join(cleaned_paragraphs)
    header = f"بسم الله الرحمن الرحيم\nالمادة: {clean_subject}\n{used_date}"
    if body:
        return f"{header}\n\n{body}"
    return header


def set_p_rtl(p, align=None):
    """Configures paragraph with proper RTL and language attributes."""
    pPr = p._p.get_or_add_pPr()
    if pPr.find(qn('w:bidi')) is None:
        pPr.append(OxmlElement('w:bidi'))
    if align:
        jc = pPr.find(qn('w:jc'))
        if jc is None:
            jc = OxmlElement('w:jc')
            pPr.append(jc)
        jc.set(qn('w:val'), align)
        
    p_rPr = pPr.find(qn('w:rPr'))
    if p_rPr is None:
        p_rPr = OxmlElement('w:rPr')
        pPr.append(p_rPr)
    if p_rPr.find(qn('w:rtl')) is None:
        p_rPr.append(OxmlElement('w:rtl'))
    lang = p_rPr.find(qn('w:lang'))
    if lang is None:
        lang = OxmlElement('w:lang')
        p_rPr.append(lang)
    lang.set(qn('w:bidi'), "ar-SA")


def set_run_font(run, font_name=DEFAULT_FONT_NAME, size_pt=DEFAULT_FONT_SIZE, bold=False):
    """Applies Arabic font, size, RTL flag, bidi language, and bold styling (w:b + w:bCs). Strictly black color."""
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    rPr = run._r.get_or_add_rPr()
    
    # RTL attribute
    if rPr.find(qn('w:rtl')) is None:
        rPr.append(OxmlElement('w:rtl'))
        
    # Complex script fonts
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.append(rFonts)
    rFonts.set(qn('w:cs'), font_name)
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:hAnsi'), font_name)
    
    # Language
    lang = rPr.find(qn('w:lang'))
    if lang is None:
        lang = OxmlElement('w:lang')
        rPr.append(lang)
    lang.set(qn('w:bidi'), "ar-SA")
    
    # Bold handling: BOTH w:b and w:bCs are strictly required for Word to render Arabic bold!
    if bold:
        run.bold = True
        if rPr.find(qn('w:bCs')) is None:
            rPr.append(OxmlElement('w:bCs'))
    else:
        run.bold = False
        bCs = rPr.find(qn('w:bCs'))
        if bCs is not None:
            rPr.remove(bCs)


def create_docx(markdown_text: str, output_path: Path, template_path: Path = WORD_BASE_TEMPLATE) -> Path:
    """
    Converts scholarly transcription markdown into a formatted .docx document.
    Inherits formatting from Word base.docx if available, with 0.5in margins,
    Traditional Arabic 18pt font, black color, bold matn tags (w:bCs), and centered headers.
    Generates one Word paragraph (^p) per line for seamless Ctrl+Down navigation.
    """
    if template_path and Path(template_path).exists():
        doc = docx.Document(str(template_path))
        p_elements = doc._body._element.xpath('./w:p')
        for p in p_elements:
            doc._body._element.remove(p)
    else:
        doc = docx.Document()
    
    for s in doc.sections:
        s.top_margin = Inches(0.5)
        s.bottom_margin = Inches(0.5)
        s.left_margin = Inches(0.5)
        s.right_margin = Inches(0.5)
        
    meta = parse_metadata(markdown_text)
    clean_subject = meta.get("subject_name") or "المادة"
    used_date = meta.get("date") or "تاريخ_غير_محدد"
    
    # 1. P0: بسم الله الرحمن الرحيم (Centered)
    p0 = doc.add_paragraph()
    set_p_rtl(p0, align='center')
    r0 = p0.add_run("بسم الله الرحمن الرحيم")
    set_run_font(r0, font_name=DEFAULT_FONT_NAME, size_pt=DEFAULT_FONT_SIZE, bold=False)
    
    # 2. P1: المادة: [clean_subject] (Centered)
    p1 = doc.add_paragraph()
    set_p_rtl(p1, align='center')
    r1 = p1.add_run(f"المادة: {clean_subject}")
    set_run_font(r1, font_name=DEFAULT_FONT_NAME, size_pt=DEFAULT_FONT_SIZE, bold=False)
    
    # 3. P2: [used_date] (Centered)
    p2 = doc.add_paragraph()
    set_p_rtl(p2, align='center')
    r2 = p2.add_run(used_date)
    set_run_font(r2, font_name=DEFAULT_FONT_NAME, size_pt=DEFAULT_FONT_SIZE, bold=False)
    
    paragraphs = markdown_text.split('\n\n')
    for para_text in paragraphs:
        cleaned_para = para_text.strip()
        if not cleaned_para:
            continue
            
        lines = [line.strip() for line in cleaned_para.split('\n') if line.strip()]
        if not lines:
            continue
            
        # Skip paragraph if it consists entirely of header block lines
        if all(is_header_line(l) for l in lines):
            continue
            
        # Strip any leading header lines if merged at top of paragraph
        while lines and is_header_line(lines[0]):
            lines.pop(0)
            
        if not lines:
            continue
            
        # One Word paragraph (^p) per line, never manual line break (^l)
        for line in lines:
            # Skip HTML comments like <!-- fallback --> in Word output
            if line.startswith("<!--") and line.endswith("-->"):
                continue

            line = re.sub(r'<!--.*?-->\s*', '', line).strip()
            if not line:
                continue

            p = doc.add_paragraph()
            set_p_rtl(p, align=None)

            # Full line matn: **(...)** or **...**
            matn_full_match = re.match(r'^\*\*(.+)\*\*$', line)
            if matn_full_match:
                matn_content = matn_full_match.group(1)
                run = p.add_run(matn_content)
                set_run_font(run, font_name=DEFAULT_FONT_NAME, size_pt=DEFAULT_FONT_SIZE, bold=True)
                continue
                
            # Mixed line with inline **(...)**
            parts = re.split(r'(\*\*[^*]+\*\*)', line)
            for part in parts:
                if not part:
                    continue
                if part.startswith('**') and part.endswith('**'):
                    inner_text = part[2:-2]
                    run = p.add_run(inner_text)
                    set_run_font(run, font_name=DEFAULT_FONT_NAME, size_pt=DEFAULT_FONT_SIZE, bold=True)
                elif part.startswith('طالب:'):
                    run_label = p.add_run('طالب: ')
                    set_run_font(run_label, font_name=DEFAULT_FONT_NAME, size_pt=DEFAULT_FONT_SIZE, bold=False)
                    rest_text = part[len('طالب:'):].strip()
                    if rest_text:
                        run_rest = p.add_run(rest_text)
                        set_run_font(run_rest, font_name=DEFAULT_FONT_NAME, size_pt=DEFAULT_FONT_SIZE, bold=False)
                else:
                    run = p.add_run(part)
                    set_run_font(run, font_name=DEFAULT_FONT_NAME, size_pt=DEFAULT_FONT_SIZE, bold=False)
                    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path


def normalize_stem(candidate_name: str) -> str:
    """
    Strips double extensions (.md.md), trailing extensions (.docx, .md),
    and suffixes (_AI, _processed, _full, _مقاطع, #AI) per ADR 0002 § 9.
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


def is_matching_stem(candidate_name: str, date: str, keyword: str) -> bool:
    """
    Returns True if candidate_name matches the (date, keyword) tuple,
    ignoring delimiter style, extensions, and suffixes per ADR 0002 § 9.
    """
    if date not in candidate_name:
        return False

    cleaned_stem = normalize_stem(candidate_name)
    stem_rem = cleaned_stem.replace(date, " ").strip(" _-")

    def _normalize_token(t: str) -> str:
        t = normalize_arabic(t)
        t = re.sub(r'ة', 'ه', t)
        t = re.sub(r'ى', 'ي', t)
        t = re.sub(r'[_\s]+', ' ', t)
        return t.strip()

    norm_rem = _normalize_token(stem_rem)
    norm_kw = _normalize_token(keyword)

    kw_variants = {norm_kw}
    for k, v in CANONICAL_SUBJECT_NAMES.items():
        k_norm = _normalize_token(k)
        v_norm = _normalize_token(v)
        if k_norm == norm_kw or v_norm == norm_kw:
            kw_variants.add(k_norm)
            kw_variants.add(v_norm)

    return any(v in norm_rem for v in kw_variants)


def archive_processed_inputs(
    date: str,
    keyword: str,
    project_root: Path = DEFAULT_PROJECT_ROOT
) -> dict:
    """
    Moves matching raw inputs and matn sources into processed/ subfolders,
    and removes reproducible chunk folders (_مقاطع/).
    03_AI_Outputs remains flat and untouched.
    """
    project_root = Path(project_root)
    matn_dir = project_root / "01_Matn_Sources"
    raw_dir = project_root / "02_Raw_Inputs"
    
    matn_processed = matn_dir / "processed"
    raw_processed = raw_dir / "processed"
    matn_processed.mkdir(parents=True, exist_ok=True)
    raw_processed.mkdir(parents=True, exist_ok=True)
    
    archived_matn = []
    archived_raw = []
    deleted_chunks = []
    
    if matn_dir.exists():
        for item in matn_dir.iterdir():
            if item.is_file() and is_matching_stem(item.name, date, keyword):
                dest = matn_processed / item.name
                shutil.move(str(item), str(dest))
                archived_matn.append(dest)
                
    if raw_dir.exists():
        for item in raw_dir.iterdir():
            if is_matching_stem(item.name, date, keyword):
                if item.is_dir() and "_مقاطع" in item.name:
                    shutil.rmtree(str(item))
                    deleted_chunks.append(item)
                elif item.is_file():
                    dest = raw_processed / item.name
                    shutil.move(str(item), str(dest))
                    archived_raw.append(dest)
                    
    return {
        "matn_files": archived_matn,
        "raw_files": archived_raw,
        "deleted_chunk_dirs": deleted_chunks
    }


DIALECT_MARKERS = {
    "كدا", "كده", "ده", "دا", "دي", "ايه", "إيه", "ازاي", "ازاى", "احنا", "إحنا",
    "برضه", "برضو", "علطول", "أومال", "امال", "مش", "عشان", "علشان", "بقى",
    "مفيش", "مافيش", "مكانش", "ماكانش", "حد", "تاني", "قوي", "خالص", "يلا"
}


def verify_isolated_segment(text: str) -> bool:
    """Strict verification for isolated fallback segments.
    Returns True if segment passes strict verification (pure Classical Arabic),
    False if it contains dialect markers indicating Sheikh's commentary.
    """
    if not text:
        return False
    words = re.findall(r'\b\w+\b', normalize_arabic(text))
    for w in words:
        if w in DIALECT_MARKERS:
            return False
    return True


def find_matching_matn_source(
    date: str,
    keyword: str,
    project_root: Path = DEFAULT_PROJECT_ROOT
) -> Path | None:
    """
    Locates a matching canonical Matn source file in 01_Matn_Sources/
    or 01_Matn_Sources/processed/ (if reprocessing).
    """
    project_root = Path(project_root)
    matn_dir = project_root / "01_Matn_Sources"
    if not matn_dir.exists():
        return None

    # Check unarchived sources first
    for item in matn_dir.iterdir():
        if item.is_file() and is_matching_stem(item.name, date, keyword):
            return item

    # Check processed/ subdirectory if reprocessing
    processed_dir = matn_dir / "processed"
    if processed_dir.exists():
        for item in processed_dir.iterdir():
            if item.is_file() and is_matching_stem(item.name, date, keyword):
                return item

    return None


def read_matn_source_content(path: Path) -> str:
    """Reads matn source from .docx or text/markdown."""
    path = Path(path)
    if path.suffix.lower() == ".docx":
        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return path.read_text(encoding="utf-8")


@dataclass
class _CandidateItem:
    para_idx: int
    line_idx: int
    is_standalone: bool
    has_preceding_fallback_line: bool
    inline_span: tuple[int, int] | None
    cand_query: str
    result: MatnMatchResult | None = None


def _extract_candidate_query(inner_text: str) -> str:
    """Strips outer parentheses if present from inner matn text."""
    inner = inner_text.strip()
    if inner.startswith('(') and inner.endswith(')'):
        return inner[1:-1].strip()
    return inner


def _format_segment_output(res: MatnMatchResult, is_standalone: bool = True) -> list[str] | str:
    """Formats matched matn segment for markdown output based on match mode and context."""
    clean_text = res.text.strip()
    if res.mode == MatchMode.PRIMARY:
        return [f"**({clean_text})**"] if is_standalone else f"**({clean_text})**"

    is_valid = res.is_sandwiched or verify_isolated_segment(res.text)
    if is_standalone:
        if is_valid:
            return ["<!-- fallback -->", f"**({clean_text})**"]
        return [f"({clean_text})"]
    else:
        if is_valid:
            return f"<!-- fallback --> **({clean_text})**"
        return f"({clean_text})"


def interleave_matn_segments(markdown_text: str, matcher: SequentialMatnMatcher) -> str:
    """
    Processes candidate matn segments through SequentialMatnMatcher,
    formatting primary matches as vowelized canonical text,
    and fallback matches with <!-- fallback --> comments.
    Applies context-dependent Conservative Doubt (sandwiched vs isolated).
    """
    paragraphs = markdown_text.split('\n\n')
    candidates: list[_CandidateItem] = []

    for p_idx, para in enumerate(paragraphs):
        lines = para.split('\n')
        skip_next = False

        for l_idx, line in enumerate(lines):
            if skip_next:
                skip_next = False
                continue

            stripped = line.strip()
            if not stripped:
                continue

            # Check if this line is <!-- fallback --> followed by standalone matn
            if stripped == "<!-- fallback -->" and l_idx + 1 < len(lines):
                next_stripped = lines[l_idx + 1].strip()
                matn_m = re.match(r'^\*\*(.+)\*\*$', next_stripped)
                if matn_m:
                    candidates.append(_CandidateItem(
                        para_idx=p_idx,
                        line_idx=l_idx + 1,
                        is_standalone=True,
                        has_preceding_fallback_line=True,
                        inline_span=None,
                        cand_query=_extract_candidate_query(matn_m.group(1))
                    ))
                    skip_next = True
                    continue

            # Check if line itself is standalone matn: **(...)** or **...**
            matn_m = re.match(r'^\*\*(.+)\*\*$', stripped)
            if matn_m:
                candidates.append(_CandidateItem(
                    para_idx=p_idx,
                    line_idx=l_idx,
                    is_standalone=True,
                    has_preceding_fallback_line=False,
                    inline_span=None,
                    cand_query=_extract_candidate_query(matn_m.group(1))
                ))
                continue

            # Line contains inline **...**
            inline_matches = list(re.finditer(r'\*\*(.+?)\*\*', line))
            for im in inline_matches:
                candidates.append(_CandidateItem(
                    para_idx=p_idx,
                    line_idx=l_idx,
                    is_standalone=False,
                    has_preceding_fallback_line=False,
                    inline_span=(im.start(), im.end()),
                    cand_query=_extract_candidate_query(im.group(1))
                ))

    # Pass 1: Sequential matching through matcher
    for c in candidates:
        c.result = matcher.match_segment(c.cand_query)

    # Resolve context-dependent sandwiching across the full document history
    matcher.resolve_sandwiched_fallbacks()

    # Pass 2: Reconstruct document
    new_paragraphs = []
    for p_idx, para in enumerate(paragraphs):
        lines = para.split('\n')
        new_lines = []
        l_idx = 0

        while l_idx < len(lines):
            line = lines[l_idx]

            # Standalone candidate at current line
            standalone_cand = next(
                (c for c in candidates if c.para_idx == p_idx and c.line_idx == l_idx and c.is_standalone),
                None
            )
            if standalone_cand:
                if standalone_cand.result is not None:
                    new_lines.extend(_format_segment_output(standalone_cand.result, is_standalone=True))
                l_idx += 1
                continue

            # Check if this line is preceding <!-- fallback --> for next standalone candidate
            if line.strip() == "<!-- fallback -->" and l_idx + 1 < len(lines):
                next_cand = next(
                    (c for c in candidates if c.para_idx == p_idx and c.line_idx == l_idx + 1 and c.is_standalone and c.has_preceding_fallback_line),
                    None
                )
                if next_cand:
                    if next_cand.result is not None:
                        new_lines.extend(_format_segment_output(next_cand.result, is_standalone=True))
                    l_idx += 2
                    continue

            # Check for inline candidates in this line
            line_cands = [
                c for c in candidates if c.para_idx == p_idx and c.line_idx == l_idx and not c.is_standalone
            ]
            if line_cands:
                line_cands_sorted = sorted(line_cands, key=lambda c: c.inline_span[0], reverse=True)
                cur_line = line
                for c in line_cands_sorted:
                    start, end = c.inline_span
                    if c.result is not None:
                        rep = _format_segment_output(c.result, is_standalone=False)
                    else:
                        rep = cur_line[start:end]
                    cur_line = cur_line[:start] + rep + cur_line[end:]
                new_lines.append(cur_line)
                l_idx += 1
                continue

            new_lines.append(line)
            l_idx += 1

        new_paragraphs.append('\n'.join(new_lines))

    return '\n\n'.join(new_paragraphs)


def export_documents(
    markdown_text: str,
    original_md_path: Path = None,
    keyword: str = None,
    date: str = None,
    base_onedrive: Path = DEFAULT_BASE_ONEDRIVE,
    project_root: Path = DEFAULT_PROJECT_ROOT,
    matn_source_path: Path = None,
) -> dict:
    """
    Exports a .docx to OneDrive and saves the AI baseline .md into 03_AI_Outputs.
    Strips raw NotebookLM source tags and standardizes the 3-line header.
    Interleaves canonical Matn alignment via SequentialMatnMatcher if available.
    On confirmed export, atomically archives input files into processed/.
    """
    project_root = Path(project_root)
    clean_md = standardize_transcript_header(markdown_text)
    meta = parse_metadata(markdown_text)
    used_date = date or meta.get("date") or "تاريخ_غير_محدد"
    used_keyword = keyword or meta.get("keyword") or "عام"
    
    # 1. Matn Matching & Interleaving
    target_matn_file = matn_source_path or find_matching_matn_source(used_date, used_keyword, project_root)
    matcher = None
    if target_matn_file and Path(target_matn_file).exists():
        matn_content = read_matn_source_content(target_matn_file)
        matcher = SequentialMatnMatcher(matn_content)
        clean_md = interleave_matn_segments(clean_md, matcher)

    # 2. Target OneDrive path (docx)
    onedrive_dir = get_onedrive_folder(used_keyword, base_onedrive)
    onedrive_file = onedrive_dir / f"{used_date}.docx"
    
    if onedrive_file.exists():
        base_stem = f"{onedrive_file.stem} #AI"
        onedrive_file = onedrive_file.with_name(f"{base_stem}{onedrive_file.suffix}")
        counter = 1
        while onedrive_file.exists():
            onedrive_file = onedrive_file.with_name(f"{base_stem} ({counter}){onedrive_file.suffix}")
            counter += 1
            
    create_docx(clean_md, onedrive_file)
    
    # 3. Target Project path (md)
    project_dir = project_root / "03_AI_Outputs"
    project_dir.mkdir(parents=True, exist_ok=True)
    
    subject_part = meta.get("subject_name") or used_keyword
    subject_clean = re.sub(r'[\\/*?:"<>|()]', "", subject_part).strip().replace(" ", "_")
    
    # AI baseline MD file with fallback summary if matcher was active
    project_file = project_dir / f"{used_date}_{subject_clean}_AI.md"
    ai_md_content = clean_md
    if matcher and matcher.history:
        summary_report = generate_fallback_summary(matcher)
        ai_md_content = f"{clean_md}\n\n{summary_report}\n"
    project_file.write_text(ai_md_content, encoding='utf-8')
    
    # 4. Atomic archiving
    archived_info = None
    if onedrive_file.exists() and project_file.exists():
        archived_info = archive_processed_inputs(used_date, used_keyword, project_root=project_root)
        
    return {
        "onedrive_file": onedrive_file,
        "project_file": project_file,
        "archived": archived_info,
        "matcher": matcher
    }


# Backwards compatibility alias
export_dual_copies = export_documents


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py export_docx.py <path_to_markdown_transcript> [keyword] [date] [matn_source_path]")
        sys.exit(1)
        
    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(f"Error: File not found: {md_path}")
        sys.exit(1)
        
    content = md_path.read_text(encoding='utf-8')
    cli_keyword = sys.argv[2] if len(sys.argv) > 2 else None
    cli_date = sys.argv[3] if len(sys.argv) > 3 else None
    cli_matn = sys.argv[4] if len(sys.argv) > 4 else None
    
    results = export_documents(content, md_path, keyword=cli_keyword, date=cli_date, matn_source_path=cli_matn)
    print(f"✓ OneDrive docx exported: {results['onedrive_file']}")
    print(f"✓ Project baseline MD saved: {results['project_file']}")
    if results.get("archived"):
        print(f"✓ Archived inputs: {len(results['archived']['matn_files'])} matn, {len(results['archived']['raw_files'])} raw")
    if results.get("matcher"):
        print(f"✓ Matn matching: {len(results['matcher'].history)} segments processed")
