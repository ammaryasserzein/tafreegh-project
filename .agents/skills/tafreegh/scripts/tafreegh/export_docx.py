from __future__ import annotations

import re
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from . import lecture_identity, word_gateway
from .arabic_normalizer import normalize_arabic, strip_tashkeel
from .lecture_identity import LectureIdentity, sanitize_filename_token
from .matn_matcher import (
    MatchMode,
    MatnMatchResult,
    SequentialMatnMatcher,
    generate_fallback_summary,
)
from .workspace_catalog import RuleCatalog, WorkspaceConfig, resolve_runtime_context

_FALLBACK_COMMENT = "<!-- fallback -->"
_BOLD_LINE_RE = re.compile(r"^\*\*(.+)\*\*$")
_BOLD_SPAN_RE = re.compile(r"\*\*(.+?)\*\*")
_ARABIC_WORD_RE = re.compile(r"[\u0600-\u06FF\w]+")


class ArchiveSummary(TypedDict):
    """Summary of archived processed input files and removed chunk directories."""

    matn_files: list[Path]
    raw_files: list[Path]
    deleted_chunk_dirs: list[Path]


class PublicationOutcome(TypedDict):
    """Result returned after running publication deliverables and optional archival."""

    onedrive_file: Path
    project_file: Path
    archived: ArchiveSummary | None
    matcher: SequentialMatnMatcher | None


def format_thousands(text: str) -> str:
    """Formats numbers like 30000 to 30 ألف and 5000 to 5 آلاف."""

    def replacer(match: re.Match[str]) -> str:
        num = int(match.group(1))
        if 3 <= num <= 10:
            return f"{num} آلاف"
        if num == 1:
            return "ألف"
        if num == 2:
            return "ألفين"
        return f"{num} ألف"

    return re.sub(r"\b(\d+)000\b", replacer, text)


def archive_processed_inputs(
    identity: LectureIdentity,
    project_root: Path | None = None,
    *,
    workspace: WorkspaceConfig | None = None,
    catalog: RuleCatalog | None = None,
) -> ArchiveSummary:
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

    archived_matn: list[Path] = []
    archived_raw: list[Path] = []
    deleted_chunks: list[Path] = []

    if matn_dir.exists():
        for item in matn_dir.iterdir():
            if item.is_file() and ident.matches(item.name, routing_map=active_catalog.routing_map):
                matn_processed.mkdir(parents=True, exist_ok=True)
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
                    raw_processed.mkdir(parents=True, exist_ok=True)
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
    normalized_markers = {
        normalize_arabic(strip_tashkeel(marker)) for marker in active_catalog.dialect_markers
    }
    plain = normalize_arabic(strip_tashkeel(text))
    for word in _ARABIC_WORD_RE.findall(plain):
        if word in normalized_markers or word in active_catalog.dialect_markers:
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
    if inner.startswith("(") and inner.endswith(")"):
        return inner[1:-1].strip()
    return inner


def _is_verified_segment(res: MatnMatchResult, catalog: RuleCatalog) -> bool:
    """Returns True when a segment is safe to preserve as bold Matn."""
    if res.mode == MatchMode.PRIMARY or res.is_sandwiched or res.is_source_anchored:
        return True
    return verify_isolated_segment(res.text, catalog=catalog)


def _format_standalone_segment(res: MatnMatchResult, catalog: RuleCatalog) -> list[str]:
    """Formats a standalone Matn paragraph line for markdown output."""
    clean_text = res.text.strip()
    if res.mode == MatchMode.PRIMARY:
        return [f"**({clean_text})**"]
    if _is_verified_segment(res, catalog):
        return [_FALLBACK_COMMENT, f"**({clean_text})**"]
    return [f"({clean_text})"]


def _format_inline_segment(res: MatnMatchResult, catalog: RuleCatalog) -> str:
    """Formats an inline Matn span for markdown output."""
    clean_text = res.text.strip()
    if res.mode == MatchMode.PRIMARY:
        return f"**({clean_text})**"
    if _is_verified_segment(res, catalog):
        return f"{_FALLBACK_COMMENT} **({clean_text})**"
    return f"({clean_text})"


def _scan_matn_candidates(paragraphs: list[str]) -> list[_CandidateItem]:
    """Extracts standalone and inline bold Matn candidates in sequential document order."""
    candidates: list[_CandidateItem] = []
    for p_idx, para in enumerate(paragraphs):
        lines = para.split("\n")
        skip_next = False

        for l_idx, line in enumerate(lines):
            if skip_next:
                skip_next = False
                continue

            stripped = line.strip()
            if not stripped:
                continue

            if stripped == _FALLBACK_COMMENT and l_idx + 1 < len(lines):
                next_stripped = lines[l_idx + 1].strip()
                matn_m = _BOLD_LINE_RE.match(next_stripped)
                if matn_m:
                    candidates.append(
                        _CandidateItem(
                            para_idx=p_idx,
                            line_idx=l_idx + 1,
                            is_standalone=True,
                            has_preceding_fallback_line=True,
                            inline_span=None,
                            cand_query=_extract_candidate_query(matn_m.group(1)),
                        )
                    )
                    skip_next = True
                    continue

            matn_m = _BOLD_LINE_RE.match(stripped)
            if matn_m:
                candidates.append(
                    _CandidateItem(
                        para_idx=p_idx,
                        line_idx=l_idx,
                        is_standalone=True,
                        has_preceding_fallback_line=False,
                        inline_span=None,
                        cand_query=_extract_candidate_query(matn_m.group(1)),
                    )
                )
                continue

            for im in _BOLD_SPAN_RE.finditer(line):
                candidates.append(
                    _CandidateItem(
                        para_idx=p_idx,
                        line_idx=l_idx,
                        is_standalone=False,
                        has_preceding_fallback_line=False,
                        inline_span=(im.start(), im.end()),
                        cand_query=_extract_candidate_query(im.group(1)),
                    )
                )
    return candidates


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
    paragraphs = markdown_text.split("\n\n")
    candidates = _scan_matn_candidates(paragraphs)

    for candidate in candidates:
        candidate.result = matcher.match_segment(candidate.cand_query)

    matcher.resolve_sandwiched_fallbacks()

    standalone_by_pos: dict[tuple[int, int], _CandidateItem] = {}
    inline_by_pos: dict[tuple[int, int], list[_CandidateItem]] = defaultdict(list)
    for candidate in candidates:
        key = (candidate.para_idx, candidate.line_idx)
        if candidate.is_standalone:
            standalone_by_pos[key] = candidate
        else:
            inline_by_pos[key].append(candidate)

    new_paragraphs: list[str] = []
    for p_idx, para in enumerate(paragraphs):
        lines = para.split("\n")
        new_lines: list[str] = []
        l_idx = 0

        while l_idx < len(lines):
            line = lines[l_idx]
            standalone_cand = standalone_by_pos.get((p_idx, l_idx))
            if standalone_cand is not None:
                if standalone_cand.result is not None:
                    new_lines.extend(_format_standalone_segment(standalone_cand.result, active_catalog))
                l_idx += 1
                continue

            if line.strip() == _FALLBACK_COMMENT and l_idx + 1 < len(lines):
                next_cand = standalone_by_pos.get((p_idx, l_idx + 1))
                if next_cand is not None and next_cand.has_preceding_fallback_line:
                    if next_cand.result is not None:
                        new_lines.extend(_format_standalone_segment(next_cand.result, active_catalog))
                    l_idx += 2
                    continue

            line_cands = inline_by_pos.get((p_idx, l_idx))
            if line_cands:
                cur_line = line
                for candidate in sorted(
                    line_cands,
                    key=lambda item: item.inline_span[0] if item.inline_span else 0,
                    reverse=True,
                ):
                    if candidate.inline_span is None:
                        continue
                    start, end = candidate.inline_span
                    rep = (
                        _format_inline_segment(candidate.result, active_catalog)
                        if candidate.result is not None
                        else cur_line[start:end]
                    )
                    cur_line = cur_line[:start] + rep + cur_line[end:]
                new_lines.append(cur_line)
                l_idx += 1
                continue

            new_lines.append(line)
            l_idx += 1

        new_paragraphs.append("\n".join(new_lines))

    return "\n\n".join(new_paragraphs)


@dataclass(frozen=True)
class PreparedTranscript:
    """Standardized, rounded, and Matn-interleaved transcript ready for delivery."""

    identity: LectureIdentity
    clean_markdown: str
    matcher: SequentialMatnMatcher | None = None


@dataclass(frozen=True)
class RenderedDeliverables:
    """Paths and matcher state produced by emitting OneDrive and baseline outputs."""

    onedrive_file: Path
    project_file: Path
    matcher: SequentialMatnMatcher | None = None


class PublicationOrchestrator:
    """Coordinates transcript preparation, dual deliverable emission, and input archiving."""

    def __init__(
        self,
        workspace: WorkspaceConfig | None = None,
        catalog: RuleCatalog | None = None,
        *,
        project_root: Path | None = None,
        onedrive_base: Path | None = None,
    ) -> None:
        self.workspace, self.catalog = resolve_runtime_context(
            workspace=workspace,
            catalog=catalog,
            project_root=project_root,
            onedrive_base=onedrive_base,
        )

    def prepare_transcript(
        self,
        markdown_text: str,
        original_md_path: Path | None = None,
        matn_source_path: Path | str | None = None,
        identity: LectureIdentity | None = None,
    ) -> PreparedTranscript:
        """Strip leaked Arabic backticks and fallback summaries, standardize headers, round thousands, and interleave Matn."""
        sanitized_markdown = word_gateway.strip_markdown_leakage(markdown_text)
        sanitized_markdown = word_gateway.strip_hybrid_summary(sanitized_markdown)
        path_ident = (
            LectureIdentity.from_filename(
                Path(original_md_path).name,
                routing_map=self.catalog.routing_map,
            )
            if original_md_path
            else None
        )
        ident = lecture_identity.resolve_document_identity(
            sanitized_markdown,
            identity,
            path_identity=path_ident,
            routing_map=self.catalog.routing_map,
        )

        clean_md = lecture_identity.apply_transcript_header(sanitized_markdown, ident)
        clean_md = format_thousands(clean_md)

        target_matn_file: Path | None = None
        if matn_source_path is not None:
            explicit_path = Path(matn_source_path)
            if not explicit_path.exists():
                raise FileNotFoundError(f"Canonical Matn source not found: {explicit_path}")
            target_matn_file = explicit_path
        else:
            target_matn_file = find_matching_matn_source(
                identity=ident,
                workspace=self.workspace,
                catalog=self.catalog,
            )

        matcher: SequentialMatnMatcher | None = None
        if target_matn_file is not None and target_matn_file.exists():
            matn_content = word_gateway.read_matn_source_content(target_matn_file)
            matcher = SequentialMatnMatcher(matn_content)
            clean_md = interleave_matn_segments(clean_md, matcher, catalog=self.catalog)

        return PreparedTranscript(
            identity=ident,
            clean_markdown=clean_md,
            matcher=matcher,
        )

    def _resolve_onedrive_output_path(
        self,
        identity: LectureIdentity,
        *,
        overwrite: bool,
    ) -> Path:
        """Resolve collision-safe OneDrive deliverable path for identity."""
        used_keyword = identity.keyword or identity.subject_name or "عام"
        onedrive_dir = self.catalog.resolve_onedrive_folder(
            used_keyword,
            self.workspace.onedrive_base,
        )
        docx_filename = f"{identity.date}.docx" if identity.date else f"{identity.resolved_stem}.docx"
        onedrive_file = onedrive_dir / docx_filename

        if onedrive_file.exists() and not overwrite:
            base_stem = f"{onedrive_file.stem} #AI"
            onedrive_file = onedrive_file.with_name(f"{base_stem}{onedrive_file.suffix}")
            counter = 1
            while onedrive_file.exists():
                onedrive_file = onedrive_file.with_name(
                    f"{base_stem} ({counter}){onedrive_file.suffix}"
                )
                counter += 1
        return onedrive_file

    def _resolve_ai_output_path(self, identity: LectureIdentity) -> Path:
        """Resolve the 03_AI_Outputs baseline markdown path for identity."""
        project_dir = self.workspace.ai_outputs_dir
        project_dir.mkdir(parents=True, exist_ok=True)
        used_keyword = identity.keyword or identity.subject_name or "عام"
        subject_clean = sanitize_filename_token(identity.subject_name or used_keyword)
        if identity.date:
            return project_dir / f"{identity.date}_{subject_clean}_AI.md"
        return project_dir / f"{identity.resolved_stem}_AI.md"

    def emit_deliverables(
        self,
        prepared: PreparedTranscript,
        *,
        overwrite: bool = False,
    ) -> RenderedDeliverables:
        """Render the OneDrive Word document and AI outputs baseline without mutating input folders."""
        ident = prepared.identity
        onedrive_file = self._resolve_onedrive_output_path(ident, overwrite=overwrite)
        word_gateway.create_docx(
            prepared.clean_markdown,
            onedrive_file,
            identity=ident,
            workspace=self.workspace,
            catalog=self.catalog,
        )

        project_file = self._resolve_ai_output_path(ident)
        ai_md_content = prepared.clean_markdown
        if prepared.matcher and prepared.matcher.history:
            summary_report = generate_fallback_summary(prepared.matcher)
            ai_md_content = f"{prepared.clean_markdown}\n\n{summary_report}\n"
        project_file.write_text(ai_md_content, encoding="utf-8")

        return RenderedDeliverables(
            onedrive_file=onedrive_file,
            project_file=project_file,
            matcher=prepared.matcher,
        )

    def archive_inputs(self, identity: LectureIdentity) -> ArchiveSummary:
        """Archive processed raw inputs and Matn sources and remove chunk folders."""
        return archive_processed_inputs(
            identity=identity,
            workspace=self.workspace,
            catalog=self.catalog,
        )

    def publish(
        self,
        markdown_text: str,
        original_md_path: Path | None = None,
        matn_source_path: Path | str | None = None,
        identity: LectureIdentity | None = None,
        overwrite: bool = False,
        *,
        archive: bool = True,
    ) -> PublicationOutcome:
        """Run transcript preparation, deliverable emission, and optional atomic archiving."""
        prepared = self.prepare_transcript(
            markdown_text,
            original_md_path=original_md_path,
            matn_source_path=matn_source_path,
            identity=identity,
        )
        rendered = self.emit_deliverables(prepared, overwrite=overwrite)
        archived_info: ArchiveSummary | None = None
        if archive and rendered.onedrive_file.exists() and rendered.project_file.exists():
            archived_info = self.archive_inputs(prepared.identity)

        return {
            "onedrive_file": rendered.onedrive_file,
            "project_file": rendered.project_file,
            "archived": archived_info,
            "matcher": rendered.matcher,
        }


def _build_cli_identity_override(keyword: str | None, date: str | None) -> LectureIdentity | None:
    """Convert raw CLI keyword/date strings into an immutable LectureIdentity override."""
    if not date and not keyword:
        return None
    if date and str(date).strip().isdigit():
        return LectureIdentity(lecture_number=str(date).strip(), keyword=keyword)
    return LectureIdentity(date=date, keyword=keyword)


def export_documents(
    markdown_text: str,
    original_md_path: Path | None = None,
    keyword: str | None = None,
    date: str | None = None,
    base_onedrive: Path | None = None,
    project_root: Path | None = None,
    matn_source_path: Path | str | None = None,
    identity: LectureIdentity | None = None,
    overwrite: bool = False,
    *,
    workspace: WorkspaceConfig | None = None,
    catalog: RuleCatalog | None = None,
) -> PublicationOutcome:
    """
    Exports transcript deliverables via PublicationOrchestrator and archives inputs.
    """
    orchestrator = PublicationOrchestrator(
        workspace=workspace,
        catalog=catalog,
        project_root=project_root,
        onedrive_base=base_onedrive,
    )
    cli_override = _build_cli_identity_override(keyword, date)
    effective_override = identity.merge(cli_override) if identity else cli_override
    return orchestrator.publish(
        markdown_text,
        original_md_path=original_md_path,
        matn_source_path=matn_source_path,
        identity=effective_override,
        overwrite=overwrite,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for exporting Tafreegh markdown to OneDrive docx and baseline markdown."""
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Export Tafreegh markdown transcript to OneDrive .docx and 03_AI_Outputs baseline."
    )
    parser.add_argument("md_path", type=Path, help="Path to markdown transcript.")
    parser.add_argument("keyword", nargs="?", default=None, help="Optional subject keyword.")
    parser.add_argument("date", nargs="?", default=None, help="Optional lecture date or number.")
    parser.add_argument("matn_source_path", nargs="?", type=Path, default=None, help="Optional path to matn source.")
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
    except (word_gateway.DocxArchiveError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"✓ OneDrive docx exported: {results['onedrive_file']}")
    print(f"✓ Project baseline MD saved: {results['project_file']}")
    archived = results["archived"]
    if archived:
        print(f"✓ Archived inputs: {len(archived['matn_files'])} matn, {len(archived['raw_files'])} raw")
    matcher = results["matcher"]
    if matcher:
        print(f"✓ Matn matching: {len(matcher.history)} segments processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
