import sys
from pathlib import Path

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
}

DEFAULT_BASE_ONEDRIVE = Path(r"C:\Users\L\OneDrive\1. دوري")

def normalize_arabic(text: str) -> str:
    """Normalizes hamzas, wasl, and cleans leading/trailing whitespace."""
    if not text:
        return ""
    text = text.strip()
    return text

import re

def parse_metadata(text: str) -> dict:
    """
    Extracts date, keyword, and clean canonical subject_name from markdown text or raw transcript headers.
    """
    metadata = {
        "date": None,
        "keyword": None,
        "subject_name": None
    }
    
    # 1. Date extraction (YYYY-MM-DD)
    date_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text)
    if date_match:
        metadata["date"] = date_match.group(1)
        
    # 2. Subject extraction
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
            
    # 3. Filename token fallback
    if not metadata["keyword"] and metadata["date"]:
        file_token_match = re.search(r'\b\d{4}-\d{2}-\d{2}\s+([^\s.]+)(?:\.mp3|\.m4a|\.wav)?', text)
        if file_token_match:
            metadata["keyword"] = file_token_match.group(1).strip()
            norm_key = normalize_arabic(metadata["keyword"])
            if norm_key in CANONICAL_SUBJECT_NAMES:
                metadata["subject_name"] = CANONICAL_SUBJECT_NAMES[norm_key]
                
    return metadata

def get_onedrive_folder(keyword: str, base_path: Path = DEFAULT_BASE_ONEDRIVE) -> Path:
    """
    Returns the target OneDrive folder Path for a given discipline keyword.
    Scans the base_path dynamically to find a matching folder.
    """
    cleaned = normalize_arabic(keyword)
    if not cleaned:
        return base_path / "عام"
        
    if base_path.exists() and base_path.is_dir():
        # Clean keyword for fuzzy matching (remove common hamzas)
        k_clean = cleaned.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        for d in base_path.iterdir():
            if d.is_dir():
                d_name_clean = d.name.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
                if k_clean in d_name_clean:
                    return d
                    
    # Fallback to creating a new folder if no match found
    return base_path / cleaned

import docx
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

WORD_BASE_TEMPLATE = Path(r"C:\Users\L\Documents\Tafreegh_Project\Word base.docx")
DEFAULT_FONT_NAME = "Traditional Arabic"
DEFAULT_FONT_SIZE = 18

def set_p_rtl(p, align=None):
    """Configures paragraph with proper RTL and language attributes."""
    pPr = p._p.get_or_add_pPr()
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

def is_header_line(line: str) -> bool:
    """Checks if a given line belongs to the standard 3-line header block."""
    l = line.strip()
    if not l:
        return True
    if l == "بسم الله الرحمن الرحيم" or l == "بسم الله الرحمن الرحيم.":
        return True
    if l.startswith("المادة:") or l.startswith("اسم المادة:"):
        return True
    if re.match(r'^\d{4}-\d{2}-\d{2}$', l):
        return True
    return False

def create_docx(markdown_text: str, output_path: Path, template_path: Path = WORD_BASE_TEMPLATE) -> Path:
    """
    Converts scholarly transcription markdown into a formatted .docx document.
    Inherits formatting from Word base.docx if available, with 0.5in margins,
    Traditional Arabic 18pt font, black color, bold matn tags (w:bCs), and centered headers.
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
            
        # Body paragraph (pure RTL flow without forcing LTR alignment)
        p = doc.add_paragraph()
        set_p_rtl(p, align=None)
        
        for idx, line in enumerate(lines):
            if idx > 0:
                p.add_run('\n')
                
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

DEFAULT_PROJECT_ROOT = Path(r"c:\Users\L\Documents\Tafreegh_Project")

def export_documents(
    markdown_text: str,
    original_md_path: Path,
    keyword: str = None,
    date: str = None,
    base_onedrive: Path = DEFAULT_BASE_ONEDRIVE,
    project_root: Path = DEFAULT_PROJECT_ROOT
) -> dict:
    """
    Exports a .docx to OneDrive and saves the AI baseline .md into 03_AI_Outputs.
    """
    meta = parse_metadata(markdown_text)
    used_date = date or meta.get("date") or "تاريخ_غير_محدد"
    used_keyword = keyword or meta.get("keyword") or "عام"
    
    # 1. Target OneDrive path (docx)
    onedrive_dir = get_onedrive_folder(used_keyword, base_onedrive)
    onedrive_file = onedrive_dir / f"{used_date}.docx"
    
    if onedrive_file.exists():
        base_stem = f"{onedrive_file.stem} #AI"
        onedrive_file = onedrive_file.with_name(f"{base_stem}{onedrive_file.suffix}")
        counter = 1
        while onedrive_file.exists():
            onedrive_file = onedrive_file.with_name(f"{base_stem} ({counter}){onedrive_file.suffix}")
            counter += 1
            
    create_docx(markdown_text, onedrive_file)
    
    # 2. Target Project path (md)
    project_dir = project_root / "03_AI_Outputs"
    project_dir.mkdir(parents=True, exist_ok=True)
    
    subject_part = meta.get("subject_name") or used_keyword
    subject_clean = re.sub(r'[\\/*?:"<>|()]', "", subject_part).strip().replace(" ", "_")
    
    # AI baseline MD file
    project_file = project_dir / f"{used_date}_{subject_clean}_AI.md"
    project_file.write_text(markdown_text, encoding='utf-8')
    
    return {
        "onedrive_file": onedrive_file,
        "project_file": project_file
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py export_docx.py <path_to_markdown_transcript> [keyword] [date]")
        sys.exit(1)
        
    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(f"Error: File not found: {md_path}")
        sys.exit(1)
        
    content = md_path.read_text(encoding='utf-8')
    cli_keyword = sys.argv[2] if len(sys.argv) > 2 else None
    cli_date = sys.argv[3] if len(sys.argv) > 3 else None
    
    results = export_documents(content, md_path, keyword=cli_keyword, date=cli_date)
    print(f"✓ OneDrive docx exported: {results['onedrive_file']}")
    print(f"✓ Project baseline MD saved: {results['project_file']}")
