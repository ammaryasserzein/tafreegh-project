from __future__ import annotations

import sys
import re
import shutil
from pathlib import Path
from dataclasses import dataclass

from . import lecture_identity, word_gateway
from .arabic_normalizer import normalize_arabic
from .lecture_identity import LectureIdentity
from .matn_matcher import (
    MatchMode,
    MatnMatchResult,
    SequentialMatnMatcher,
    generate_fallback_summary,
)
from .workspace_catalog import RuleCatalog, WorkspaceConfig, resolve_runtime_context

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def format_thousands(text: str) -> str:
    """Formats numbers like 30000 to 30 ألف and 5000 to 5 آلاف"""
    def replacer(match):
        num = int(match.group(1))
        if 3 <= num <= 10:
            return f"{num} آلاف"
        elif num == 1:
            return "ألف"
        elif num == 2:
            return "ألفين"
        else:
            return f"{num} ألف"
    return re.sub(r'\b(\d+)000\b', replacer, text)


def archive_processed_inputs(
    identity: LectureIdentity,
    project_root: Path | None = None,
    *,
    workspace: WorkspaceConfig | None = None,
    catalog: RuleCatalog | None = None,
) -> dict:
    """
    Moves matching raw inputs and matn sources into processed/ subfolders,
    and removes reproducible chunk folders (_مقاطع/).
    03_AI_Outputs remains flat and untouched.
    """
    ident = identity
    active_workspace, active_catalog = resolve_runtime_context(
        workspace=workspace,
        catalog=catalog,
        project_root=project_root,
    )
    matn_dir = active_workspace.matn_sources_dir
    raw_dir = active_workspace.raw_inputs_dir

    matn_processed = matn_dir / "processed"
    raw_processed = raw_dir / "processed"
    matn_processed.mkdir(parents=True, exist_ok=True)
    raw_processed.mkdir(parents=True, exist_ok=True)

    archived_matn = []
    archived_raw = []
    deleted_chunks = []

    if matn_dir.exists():
        for item in matn_dir.iterdir():
            if item.is_file() and ident.matches(item.name, routing_map=active_catalog.routing_map):
                dest = matn_processed / item.name
                shutil.move(str(item), str(dest))
                archived_matn.append(dest)

    if raw_dir.exists():
        for item in raw_dir.iterdir():
            if ident.matches(item.name, routing_map=active_catalog.routing_map):
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
        "deleted_chunk_dirs": deleted_chunks,
    }


def verify_isolated_segment(text: str, *, catalog: RuleCatalog | None = None) -> bool:
    """Strict verification for isolated fallback segments.
    Returns True if segment passes strict verification (pure Classical Arabic),
    False if it contains dialect markers indicating Sheikh's commentary.
    """
    if not text:
        return False
    active_catalog = catalog if catalog is not None else RuleCatalog.load()
    words = re.findall(r'\b\w+\b', normalize_arabic(text))
    for w in words:
        if w in active_catalog.dialect_markers:
            return False
    return True


def find_matching_matn_source(
    identity: LectureIdentity,
    project_root: Path | None = None,
    *,
    workspace: WorkspaceConfig | None = None,
    catalog: RuleCatalog | None = None,
) -> Path | None:
    """
    Locates a matching canonical Matn source file in 01_Matn_Sources/
    or 01_Matn_Sources/processed/ (if reprocessing).
    """
    ident = identity
    active_workspace, active_catalog = resolve_runtime_context(
        workspace=workspace,
        catalog=catalog,
        project_root=project_root,
    )
    matn_dir = active_workspace.matn_sources_dir
    if not matn_dir.exists():
        return None

    # Check unarchived sources first
    for item in matn_dir.iterdir():
        if item.is_file() and ident.matches(item.name, routing_map=active_catalog.routing_map):
            return item

    # Check processed/ subdirectory if reprocessing
    processed_dir = matn_dir / "processed"
    if processed_dir.exists():
        for item in processed_dir.iterdir():
            if item.is_file() and ident.matches(item.name, routing_map=active_catalog.routing_map):
                return item

    return None


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


def _format_segment_output(
    res: MatnMatchResult,
    is_standalone: bool = True,
    *,
    catalog: RuleCatalog | None = None,
) -> list[str] | str:
    """Formats matched matn segment for markdown output based on match mode and context."""
    clean_text = res.text.strip()
    if res.mode == MatchMode.PRIMARY:
        return [f"**({clean_text})**"] if is_standalone else f"**({clean_text})**"

    is_valid = res.is_sandwiched or verify_isolated_segment(res.text, catalog=catalog)
    if is_standalone:
        if is_valid:
            return ["<!-- fallback -->", f"**({clean_text})**"]
        return [f"({clean_text})"]
    else:
        if is_valid:
            return f"<!-- fallback --> **({clean_text})**"
        return f"({clean_text})"


def interleave_matn_segments(
    markdown_text: str,
    matcher: SequentialMatnMatcher,
    *,
    catalog: RuleCatalog | None = None,
) -> str:
    """
    Processes candidate matn segments through SequentialMatnMatcher,
    formatting primary matches as vowelized canonical text,
    and fallback matches with <!-- fallback --> comments.
    Applies context-dependent Conservative Doubt (sandwiched vs isolated).
    """
    active_catalog = catalog if catalog is not None else RuleCatalog.load()
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
                    new_lines.extend(
                        _format_segment_output(standalone_cand.result, is_standalone=True, catalog=active_catalog)
                    )
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
                        new_lines.extend(
                            _format_segment_output(next_cand.result, is_standalone=True, catalog=active_catalog)
                        )
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
                        rep = _format_segment_output(c.result, is_standalone=False, catalog=active_catalog)
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
    original_md_path: Path | None = None,
    keyword: str | None = None,
    date: str | None = None,
    base_onedrive: Path | None = None,
    project_root: Path | None = None,
    matn_source_path: Path | None = None,
    identity: LectureIdentity | None = None,
    overwrite: bool = False,
    *,
    workspace: WorkspaceConfig | None = None,
    catalog: RuleCatalog | None = None,
) -> dict:
    """
    Exports a .docx to OneDrive and saves the AI baseline .md into 03_AI_Outputs.
    Strips raw NotebookLM source tags and standardizes the 3-line header.
    Interleaves canonical Matn alignment via SequentialMatnMatcher if available.
    On confirmed export, atomically archives input files into processed/.
    """
    active_workspace, active_catalog = resolve_runtime_context(
        workspace=workspace,
        catalog=catalog,
        project_root=project_root,
        onedrive_base=base_onedrive,
    )
    markdown_text = word_gateway.strip_hybrid_summary(markdown_text)
    path_ident = (
        LectureIdentity.from_filename(
            Path(original_md_path).name,
            routing_map=active_catalog.routing_map,
        )
        if original_md_path
        else None
    )
    cli_override = LectureIdentity(date=date, keyword=keyword) if (date or keyword) else None
    effective_override = identity.merge(cli_override) if identity else cli_override
    ident = lecture_identity.resolve_document_identity(
        markdown_text,
        effective_override,
        path_identity=path_ident,
        routing_map=active_catalog.routing_map,
    )

    clean_md = lecture_identity.apply_transcript_header(markdown_text, ident)
    clean_md = format_thousands(clean_md)

    # 1. Matn Matching & Interleaving
    target_matn_file = matn_source_path or find_matching_matn_source(
        identity=ident,
        workspace=active_workspace,
        catalog=active_catalog,
    )
    matcher = None
    if target_matn_file and Path(target_matn_file).exists():
        matn_content = word_gateway.read_matn_source_content(target_matn_file)
        matcher = SequentialMatnMatcher(matn_content)
        clean_md = interleave_matn_segments(clean_md, matcher, catalog=active_catalog)

    # 2. Target OneDrive path (docx)
    used_keyword = ident.keyword or ident.subject_name or "عام"
    onedrive_dir = active_catalog.resolve_onedrive_folder(
        used_keyword,
        active_workspace.onedrive_base,
    )
    if ident.date:
        docx_filename = f"{ident.date}.docx"
    elif ident.resolved_stem:
        docx_filename = f"{ident.resolved_stem}.docx"
    else:
        docx_filename = f"{ident.lecture_number or 'تاريخ_غير_محدد'}.docx"

    onedrive_file = onedrive_dir / docx_filename

    if onedrive_file.exists() and not overwrite:
        base_stem = f"{onedrive_file.stem} #AI"
        onedrive_file = onedrive_file.with_name(f"{base_stem}{onedrive_file.suffix}")
        counter = 1
        while onedrive_file.exists():
            onedrive_file = onedrive_file.with_name(f"{base_stem} ({counter}){onedrive_file.suffix}")
            counter += 1

    word_gateway.create_docx(
        clean_md,
        onedrive_file,
        identity=ident,
        workspace=active_workspace,
        catalog=active_catalog,
    )

    # 3. Target Project path (md)
    project_dir = active_workspace.ai_outputs_dir
    project_dir.mkdir(parents=True, exist_ok=True)

    subject_part = ident.subject_name or used_keyword
    subject_clean = re.sub(r'[\\/*?:"<>|()]', "", subject_part).strip().replace(" ", "_")

    if ident.date:
        project_file = project_dir / f"{ident.date}_{subject_clean}_AI.md"
    elif ident.resolved_stem:
        project_file = project_dir / f"{ident.resolved_stem}_AI.md"
    else:
        project_file = project_dir / f"{ident.lecture_number}_{subject_clean}_AI.md"

    ai_md_content = clean_md
    if matcher and matcher.history:
        summary_report = generate_fallback_summary(matcher)
        ai_md_content = f"{clean_md}\n\n{summary_report}\n"
    project_file.write_text(ai_md_content, encoding='utf-8')

    # 4. Atomic archiving
    archived_info = None
    if onedrive_file.exists() and project_file.exists():
        archived_info = archive_processed_inputs(
            identity=ident,
            workspace=active_workspace,
            catalog=active_catalog,
        )

    return {
        "onedrive_file": onedrive_file,
        "project_file": project_file,
        "archived": archived_info,
        "matcher": matcher,
    }


# Backwards compatibility alias
export_dual_copies = export_documents


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for exporting Tafreegh markdown to OneDrive docx and baseline markdown."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Export Tafreegh markdown transcript to OneDrive .docx and 03_AI_Outputs baseline."
    )
    parser.add_argument("md_path", type=Path, help="Path to markdown transcript.")
    parser.add_argument("keyword", nargs="?", default=None, help="Optional subject keyword.")
    parser.add_argument("date", nargs="?", default=None, help="Optional lecture date or number.")
    parser.add_argument("matn_source_path", nargs="?", default=None, help="Optional path to matn source.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing OneDrive .docx in place.")

    args = parser.parse_args(argv)
    if not args.md_path.exists():
        print(f"Error: File not found: {args.md_path}")
        return 1

    content = args.md_path.read_text(encoding="utf-8")
    try:
        results = export_documents(
            content,
            args.md_path,
            keyword=args.keyword,
            date=args.date,
            matn_source_path=args.matn_source_path,
            overwrite=args.overwrite,
        )
    except word_gateway.DocxArchiveError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"✓ OneDrive docx exported: {results['onedrive_file']}")
    print(f"✓ Project baseline MD saved: {results['project_file']}")
    if results.get("archived"):
        print(f"✓ Archived inputs: {len(results['archived']['matn_files'])} matn, {len(results['archived']['raw_files'])} raw")
    if results.get("matcher"):
        print(f"✓ Matn matching: {len(results['matcher'].history)} segments processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
