"""Symmetric Word OOXML Gateway for bidirectional extraction, rendering, and inspection."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import docx
import lxml.etree
from docx.opc.exceptions import OpcError
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from . import lecture_identity
from .lecture_identity import LectureIdentity
from .workspace_catalog import RuleCatalog, WorkspaceConfig, resolve_runtime_context

DEFAULT_FONT_NAME = "Traditional Arabic"
DEFAULT_FONT_SIZE = 18
DEFAULT_MARGIN_INCHES = 0.5
MARGIN_TOLERANCE_INCHES = 0.02
DEFAULT_BIDI_LANG = "ar-SA"
HYBRID_SUMMARY_HEADING = "### تقرير المتن الهجين"

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W_NS_MAP = {"w": _W_NS}
_W_FALSE_VALUES = frozenset({"0", "false", "off"})
_INLINE_BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")
_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")
_HTML_COMMENT_INLINE_RE = re.compile(r"<!--.*?-->\s*")
_BOLD_BLOCK_RE = re.compile(r"^\*\*(.+)\*\*$", re.DOTALL)
_BOLD_SPAN_RE = re.compile(r"(\*\*[^*]+\*\*)")


class DocxArchiveError(Exception):
    """Raised when a .docx archive is missing, unreadable, malformed, or invalid OOXML."""

    def __init__(self, message: str, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else None
        super().__init__(message)


@dataclass(frozen=True)
class InspectedRun:
    """Immutable OOXML run inspection snapshot."""

    text: str
    is_bold: bool
    has_b: bool
    has_b_cs: bool
    font_name: str | None
    font_size_pt: float | None
    has_rpr: bool
    has_rtl: bool
    bidi_lang: str | None
    color_val: str | None
    has_color_element: bool


@dataclass(frozen=True)
class InspectedParagraph:
    """Immutable OOXML paragraph inspection snapshot."""

    index: int
    text: str
    has_bidi: bool
    is_centered: bool
    manual_line_break_count: int
    runs: tuple[InspectedRun, ...]


@dataclass(frozen=True)
class InspectedSectionMargins:
    """Immutable OOXML section margins snapshot in inches."""

    section_index: int
    top_inches: float | None
    bottom_inches: float | None
    left_inches: float | None
    right_inches: float | None


@dataclass(frozen=True)
class InspectedDocument:
    """Immutable OOXML document inspection snapshot."""

    path: Path | None
    sections: tuple[InspectedSectionMargins, ...]
    paragraphs: tuple[InspectedParagraph, ...]


def _is_ooxml_flag_enabled(el: object | None) -> bool:
    """Returns True when an OOXML toggle element (e.g. w:b or w:bCs) is active."""
    if el is None:
        return False
    val = el.get(f"{{{_W_NS}}}val")  # type: ignore[union-attr]
    if val is None:
        return True
    return val.strip().lower() not in _W_FALSE_VALUES


def _parse_run_bold_flags(rpr_el: object | None) -> tuple[bool, bool, bool]:
    """Returns (is_bold, has_b, has_b_cs) from a w:rPr element."""
    if rpr_el is None:
        return False, False, False
    has_b = _is_ooxml_flag_enabled(rpr_el.find(f"{{{_W_NS}}}b"))  # type: ignore[union-attr]
    has_b_cs = _is_ooxml_flag_enabled(rpr_el.find(f"{{{_W_NS}}}bCs"))  # type: ignore[union-attr]
    return (has_b or has_b_cs), has_b, has_b_cs


def _format_archive_label(docx_source: Path | str | IO[bytes]) -> str:
    return str(docx_source) if isinstance(docx_source, (str, Path)) else "<stream>"


def _read_document_xml_root(docx_source: Path | str | IO[bytes]) -> ET.Element:
    """Opens a .docx zip archive and parses word/document.xml into an ElementTree root."""
    label = _format_archive_label(docx_source)
    if isinstance(docx_source, (str, Path)) and not Path(docx_source).is_file():
        raise DocxArchiveError(f"Cannot read .docx archive '{label}': file not found.", path=docx_source)

    try:
        with zipfile.ZipFile(docx_source) as archive:
            xml_bytes = archive.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError, UnicodeDecodeError, ValueError) as exc:
        path_arg = docx_source if isinstance(docx_source, (str, Path)) else None
        raise DocxArchiveError(f"Cannot read .docx archive '{label}': {exc}", path=path_arg) from exc

    if root.tag != f"{{{_W_NS}}}document":
        path_arg = docx_source if isinstance(docx_source, (str, Path)) else None
        raise DocxArchiveError(
            f"Invalid OOXML root tag '{root.tag}' in '{label}' (expected WordprocessingML document).",
            path=path_arg,
        )
    return root


def _open_docx_document(docx_source: Path | str | IO[bytes]) -> docx.document.Document:
    """Opens a .docx package via python-docx, raising DocxArchiveError on archive/XML failures."""
    label = _format_archive_label(docx_source)
    path_arg = docx_source if isinstance(docx_source, (str, Path)) else None
    if path_arg is not None and not Path(path_arg).is_file():
        raise DocxArchiveError(f"Cannot read .docx archive '{label}': file not found.", path=path_arg)

    source_arg: str | IO[bytes] = str(docx_source) if isinstance(docx_source, (str, Path)) else docx_source
    try:
        return docx.Document(source_arg)
    except (
        OSError,
        zipfile.BadZipFile,
        KeyError,
        OpcError,
        lxml.etree.LxmlError,
        ET.ParseError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise DocxArchiveError(f"Cannot read .docx archive '{label}': {exc}", path=path_arg) from exc


def strip_markdown_leakage(markdown_text: str) -> str:
    """Strips inline backticks wrapping Arabic text while preserving English/code spans (ADR-0003)."""
    return _INLINE_BACKTICK_SPAN_RE.sub(
        lambda match: match.group(1) if _ARABIC_CHAR_RE.search(match.group(1)) else match.group(0),
        markdown_text,
    )


def strip_hybrid_summary(markdown_text: str) -> str:
    """Strips the Dynamic Fallback Interleaving summary block from markdown text if present."""
    if HYBRID_SUMMARY_HEADING in markdown_text:
        return markdown_text.split(HYBRID_SUMMARY_HEADING)[0].strip()
    return markdown_text


def read_matn_source_content(path: Path | str) -> str:
    """Reads canonical Matn source content from a .docx or text/markdown file."""
    target = Path(path)
    if target.suffix.lower() == ".docx":
        doc = _open_docx_document(target)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return target.read_text(encoding="utf-8")


def _ensure_child(parent: object, tag_name: str) -> object:
    el = parent.find(qn(tag_name))  # type: ignore[union-attr]
    if el is None:
        el = OxmlElement(tag_name)
        parent.append(el)  # type: ignore[union-attr]
    return el


def _set_paragraph_rtl(p: object, align: str | None = None) -> None:
    """Configures a paragraph with RTL direction, optional alignment, and bidi language."""
    p_pr = p._p.get_or_add_pPr()  # type: ignore[union-attr]
    _ensure_child(p_pr, "w:bidi")
    if align:
        jc = _ensure_child(p_pr, "w:jc")
        jc.set(qn("w:val"), align)  # type: ignore[union-attr]

    p_rpr = _ensure_child(p_pr, "w:rPr")
    _ensure_child(p_rpr, "w:rtl")
    lang = _ensure_child(p_rpr, "w:lang")
    lang.set(qn("w:bidi"), DEFAULT_BIDI_LANG)  # type: ignore[union-attr]


def _set_run_font(
    run: object,
    font_name: str = DEFAULT_FONT_NAME,
    size_pt: int | float = DEFAULT_FONT_SIZE,
    bold: bool = False,
) -> None:
    """Applies Arabic typography, RTL flags, bidi language, and complex-script bolding."""
    run.font.name = font_name  # type: ignore[union-attr]
    run.font.size = Pt(size_pt)  # type: ignore[union-attr]
    r_pr = run._r.get_or_add_rPr()  # type: ignore[union-attr]

    _ensure_child(r_pr, "w:rtl")
    r_fonts = _ensure_child(r_pr, "w:rFonts")
    r_fonts.set(qn("w:cs"), font_name)  # type: ignore[union-attr]
    r_fonts.set(qn("w:ascii"), font_name)  # type: ignore[union-attr]
    r_fonts.set(qn("w:hAnsi"), font_name)  # type: ignore[union-attr]

    lang = _ensure_child(r_pr, "w:lang")
    lang.set(qn("w:bidi"), DEFAULT_BIDI_LANG)  # type: ignore[union-attr]

    if bold:
        run.bold = True  # type: ignore[union-attr]
        _ensure_child(r_pr, "w:bCs")
    else:
        run.bold = False  # type: ignore[union-attr]
        b_cs = r_pr.find(qn("w:bCs"))
        if b_cs is not None:
            r_pr.remove(b_cs)


def _add_styled_paragraph(
    doc: docx.document.Document,
    text: str,
    *,
    align: str | None = None,
    bold: bool = False,
) -> None:
    paragraph = doc.add_paragraph()
    _set_paragraph_rtl(paragraph, align=align)
    run = paragraph.add_run(text)
    _set_run_font(run, bold=bold)


def _append_mixed_line_paragraph(doc: docx.document.Document, line: str) -> None:
    paragraph = doc.add_paragraph()
    _set_paragraph_rtl(paragraph, align=None)
    for part in _BOLD_SPAN_RE.split(line):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            _set_run_font(run, bold=False)
        elif part.startswith("طالب:"):
            run_label = paragraph.add_run("طالب: ")
            _set_run_font(run_label, bold=False)
            rest_text = part[len("طالب:") :].strip()
            if rest_text:
                run_rest = paragraph.add_run(rest_text)
                _set_run_font(run_rest, bold=False)
        else:
            run = paragraph.add_run(part)
            _set_run_font(run, bold=False)


def create_docx(
    markdown_text: str,
    output_path: Path | str,
    template_path: Path | str | None = None,
    identity: LectureIdentity | None = None,
    *,
    workspace: WorkspaceConfig | None = None,
    catalog: RuleCatalog | None = None,
) -> Path:
    """Renders scholarly transcription markdown into a formatted RTL .docx document."""
    sanitized = strip_markdown_leakage(markdown_text)
    sanitized = strip_hybrid_summary(sanitized)

    active_workspace, active_catalog = resolve_runtime_context(
        workspace=workspace,
        catalog=catalog,
    )
    resolved_template = (
        Path(template_path)
        if template_path is not None
        else active_workspace.word_base_template
    )
    if resolved_template and resolved_template.exists():
        doc = _open_docx_document(resolved_template)
        for p_el in doc._body._element.xpath("./w:p"):
            doc._body._element.remove(p_el)
    else:
        doc = docx.Document()

    margin = Inches(DEFAULT_MARGIN_INCHES)
    for section in doc.sections:
        section.top_margin = margin
        section.bottom_margin = margin
        section.left_margin = margin
        section.right_margin = margin

    ident = lecture_identity.resolve_document_identity(
        sanitized,
        identity,
        routing_map=active_catalog.routing_map,
    )
    for header_line in ident.header_lines:
        _add_styled_paragraph(doc, header_line, align="center", bold=False)

    for lines in lecture_identity.strip_header_blocks(sanitized):
        cleaned_para = "\n".join(lines)
        para_matn_match = _BOLD_BLOCK_RE.match(cleaned_para)
        if para_matn_match and not re.search(r"\*\*[^*]+\*\*", para_matn_match.group(1)):
            matn_content = " ".join(
                ln.strip() for ln in para_matn_match.group(1).split("\n") if ln.strip()
            )
            _add_styled_paragraph(doc, matn_content, bold=True)
            continue

        # One Word paragraph (^p) per line, never manual line break (^l)
        for line in lines:
            if line.startswith("<!--") and line.endswith("-->"):
                continue

            cleaned_line = _HTML_COMMENT_INLINE_RE.sub("", line).strip()
            if not cleaned_line:
                continue

            matn_line_match = re.match(r"^\*\*(.+)\*\*$", cleaned_line)
            if matn_line_match:
                _add_styled_paragraph(doc, matn_line_match.group(1), bold=True)
                continue

            _append_mixed_line_paragraph(doc, cleaned_line)

    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(target_path))
    return target_path


def extract_text(docx_source: Path | str | IO[bytes]) -> str:
    """Extracts paragraphs from a .docx archive as Markdown, preserving bold Matn runs."""
    root = _read_document_xml_root(docx_source)
    paragraphs: list[str] = []

    for p in root.iterfind(".//w:p", _W_NS_MAP):
        para_parts: list[str] = []
        currently_bold = False

        for r in p.iterfind(".//w:r", _W_NS_MAP):
            is_bold, _, _ = _parse_run_bold_flags(r.find("w:rPr", _W_NS_MAP))
            run_text = "".join(node.text for node in r.iterfind(".//w:t", _W_NS_MAP) if node.text)
            if not run_text:
                continue

            if is_bold and not currently_bold:
                para_parts.append("**")
                currently_bold = True
            elif not is_bold and currently_bold:
                para_parts.append("**")
                currently_bold = False
            para_parts.append(run_text)

        if currently_bold:
            para_parts.append("**")

        para_text = "".join(para_parts)
        para_text = re.sub(r"\*\*([ \t]+)\*\*", r"\1", para_text)
        para_text = para_text.replace("****", "")
        paragraphs.append(para_text)

    return "\n\n".join(paragraphs).strip()


def _inspect_run(run: object) -> InspectedRun:
    r_pr = run._r.find(qn("w:rPr"))  # type: ignore[union-attr]
    is_bold, has_b, has_b_cs = _parse_run_bold_flags(r_pr)

    font_name = run.font.name  # type: ignore[union-attr]
    if r_pr is not None and not font_name:
        r_fonts = r_pr.find(qn("w:rFonts"))
        if r_fonts is not None:
            font_name = r_fonts.get(qn("w:cs")) or r_fonts.get(qn("w:ascii"))

    font_size_pt = run.font.size.pt if run.font.size is not None else None  # type: ignore[union-attr]
    has_rpr = r_pr is not None
    has_rtl = has_rpr and r_pr.find(qn("w:rtl")) is not None
    lang_el = r_pr.find(qn("w:lang")) if has_rpr else None
    bidi_lang = lang_el.get(qn("w:bidi")) if lang_el is not None else None
    color_el = r_pr.find(qn("w:color")) if has_rpr else None
    has_color_element = color_el is not None
    color_val = color_el.get(qn("w:val")) if color_el is not None else None

    return InspectedRun(
        text=run.text,  # type: ignore[union-attr]
        is_bold=is_bold,
        has_b=has_b,
        has_b_cs=has_b_cs,
        font_name=font_name,
        font_size_pt=font_size_pt,
        has_rpr=has_rpr,
        has_rtl=has_rtl,
        bidi_lang=bidi_lang,
        color_val=color_val,
        has_color_element=has_color_element,
    )


def inspect_docx(docx_source: Path | str | IO[bytes]) -> InspectedDocument:
    """Inspects OOXML sections, margins, paragraphs, runs, RTL, and bold attributes."""
    doc = _open_docx_document(docx_source)

    sections = tuple(
        InspectedSectionMargins(
            section_index=s_idx,
            top_inches=section.top_margin.inches if section.top_margin is not None else None,
            bottom_inches=section.bottom_margin.inches if section.bottom_margin is not None else None,
            left_inches=section.left_margin.inches if section.left_margin is not None else None,
            right_inches=section.right_margin.inches if section.right_margin is not None else None,
        )
        for s_idx, section in enumerate(doc.sections)
    )

    paragraphs: list[InspectedParagraph] = []
    for p_idx, paragraph in enumerate(doc.paragraphs):
        p_pr = paragraph._p.find(qn("w:pPr"))
        has_bidi = p_pr is not None and p_pr.find(qn("w:bidi")) is not None
        jc = p_pr.find(qn("w:jc")) if p_pr is not None else None
        is_centered = jc is not None and jc.get(qn("w:val")) == "center"
        manual_line_break_count = len(paragraph._p.findall(".//" + qn("w:br")))
        runs = tuple(_inspect_run(r) for r in paragraph.runs)
        paragraphs.append(
            InspectedParagraph(
                index=p_idx,
                text=paragraph.text,
                has_bidi=has_bidi,
                is_centered=is_centered,
                manual_line_break_count=manual_line_break_count,
                runs=runs,
            )
        )

    doc_path = Path(docx_source) if isinstance(docx_source, (str, Path)) else None
    return InspectedDocument(
        path=doc_path,
        sections=sections,
        paragraphs=tuple(paragraphs),
    )
