"""Unified Diff Loop Analyzer for OneDrive reviewed deliverables and training ingestion."""

from __future__ import annotations

import datetime
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .diff_cues import CueResult, detect_new_student_cues, format_cue_report
from .diff_inline_matn import MatnDiffItem, classify_matn_diffs, format_matn_diff_report
from .export_docx import find_matching_matn_source
from .lecture_identity import LectureIdentity
from .word_gateway import DocxArchiveError, extract_text, read_matn_source_content
from .workspace_catalog import RuleCatalog, WorkspaceConfig, resolve_runtime_context

_DELIVERED_FOLDER_NAMES = frozenset({"(تم التسليم)", "تم التسليم"})
_SUBJECT_PREFIX_RE = re.compile(r"^\d+\.\s*")


@dataclass(frozen=True)
class LectureDiffAnalysis:
    """Ingestion and Diff Loop classification outcome for a single reviewed deliverable."""

    docx_path: Path
    markdown_path: Path
    identity: LectureIdentity
    skipped_existing: bool = False
    read_error: str | None = None
    ai_baseline_path: Path | None = None
    matn_source_path: Path | None = None
    cues: CueResult = field(default_factory=CueResult)
    matn_diffs: tuple[MatnDiffItem, ...] = ()


@dataclass(frozen=True)
class DiffLoopRunResult:
    """Consolidated outcome across all scanned deliverables in a Diff Loop run."""

    scanned_count: int = 0
    extracted_paths: tuple[Path, ...] = ()
    skipped_paths: tuple[Path, ...] = ()
    failed_paths: tuple[tuple[Path, str], ...] = ()
    analyses: tuple[LectureDiffAnalysis, ...] = ()
    consolidated_cues: CueResult = field(default_factory=CueResult)
    consolidated_matn_diffs: tuple[MatnDiffItem, ...] = ()

    def format_report(self) -> str:
        """Format per-deliverable logs and consolidated cue + inline Matn diff reports."""
        if self.scanned_count == 0:
            return "No files found to process."

        lines: list[str] = []
        for analysis in self.analyses:
            lines.extend(_format_analysis_lines(analysis))

        cue_report = format_cue_report(self.consolidated_cues)
        if cue_report:
            lines.extend(["", cue_report])

        if any(a.ai_baseline_path is not None for a in self.analyses):
            lines.extend(["", format_matn_diff_report(list(self.consolidated_matn_diffs))])

        return "\n".join(lines).strip()


def _format_analysis_lines(analysis: LectureDiffAnalysis) -> list[str]:
    """Render concise per-deliverable log lines for CLI reporting."""
    lines = [f"Processing {analysis.docx_path}..."]
    if analysis.skipped_existing:
        lines.append(f"Skipping {analysis.docx_path} - already processed as {analysis.markdown_path.name}")
        return lines
    if analysis.read_error is not None:
        lines.append(f"Failed to read {analysis.docx_path}: {analysis.read_error}")
        return lines

    lines.append(f"Saved extracted text to {analysis.markdown_path} (Original docx kept safe in OneDrive)")
    if analysis.ai_baseline_path is None:
        lines.append(
            f"  ↳ No AI baseline (_AI.md) found for {analysis.markdown_path.name} — skipping diff analysis"
        )
        return lines

    if analysis.matn_source_path is not None:
        lines.append(f"  ↳ Paired canonical Matn source: {analysis.matn_source_path.name}")
    if analysis.cues.inserted:
        lines.append(
            f"  ↳ Found {len(analysis.cues.inserted)} candidate cue(s) from diff with {analysis.ai_baseline_path.name}"
        )
    if analysis.cues.removed:
        lines.append(
            f"  ↳ Found {len(analysis.cues.removed)} removed cue(s) from diff with {analysis.ai_baseline_path.name}"
        )
    if analysis.matn_diffs:
        lines.append(
            f"  ↳ Classified {len(analysis.matn_diffs)} inline Matn diff(s) against {analysis.ai_baseline_path.name}"
        )
    return lines


def _candidate_baseline_names(identity: LectureIdentity, subject: str) -> list[str]:
    """Build exact `_AI.md` filename candidates in priority order."""
    candidates: list[str] = []
    if identity.stem:
        candidates.append(f"{identity.stem}_AI.md")
    if identity.resolved_stem:
        candidates.append(f"{identity.resolved_stem}_AI.md")
    resolved_subject = identity.subject_name or subject
    if identity.date and resolved_subject:
        candidates.append(f"{identity.date}_{resolved_subject}_AI.md")
    elif identity.date:
        candidates.append(f"{identity.date}_AI.md")
    return list(dict.fromkeys(candidates))


class DiffLoopAnalyzer:
    """Unified Diff Loop orchestrator over explicit WorkspaceConfig and RuleCatalog."""

    def __init__(
        self,
        workspace: WorkspaceConfig | None = None,
        catalog: RuleCatalog | None = None,
    ) -> None:
        self.workspace, self.catalog = resolve_runtime_context(
            workspace=workspace,
            catalog=catalog,
        )

    def _baseline_search_dirs(self) -> tuple[Path, Path]:
        return (self.workspace.ai_outputs_dir, self.workspace.raw_inputs_dir)

    def find_ai_baseline(self, identity: LectureIdentity, subject: str = "") -> Path | None:
        """Locate the corresponding `_AI.md` baseline using exact, identity, and date matching."""
        search_dirs = [d for d in self._baseline_search_dirs() if d.exists()]
        candidates = _candidate_baseline_names(identity, subject)

        for directory in search_dirs:
            for c_name in candidates:
                candidate = directory / c_name
                if candidate.exists():
                    return candidate

        for directory in search_dirs:
            for entry in sorted(directory.iterdir()):
                if entry.name.endswith("_AI.md") and identity.matches(
                    entry.name,
                    routing_map=self.catalog.routing_map,
                ):
                    return entry

        if identity.date:
            for directory in search_dirs:
                for entry in sorted(directory.iterdir()):
                    if entry.name.startswith(identity.date) and entry.name.endswith("_AI.md"):
                        return entry

        return None

    def find_matn_source(self, identity: LectureIdentity) -> Path | None:
        """Locate the canonical Matn source matching the reviewed deliverable identity."""
        return find_matching_matn_source(
            identity,
            workspace=self.workspace,
            catalog=self.catalog,
        )

    def scan_deliverables(self) -> list[Path]:
        """Find reviewed `.docx` deliverables under OneDrive `(تم التسليم)` folders."""
        onedrive_base = self.workspace.onedrive_base
        if not onedrive_base.exists():
            return []
        return sorted(
            path
            for path in onedrive_base.rglob("*.docx")
            if path.is_file() and path.parent.name in _DELIVERED_FOLDER_NAMES
        )

    def _resolve_deliverable_target(self, docx_path: Path) -> tuple[LectureIdentity, str, Path]:
        subject = _SUBJECT_PREFIX_RE.sub("", docx_path.parent.parent.name)
        identity = LectureIdentity.from_filename(
            docx_path.name,
            fallback_subject=subject,
            routing_map=self.catalog.routing_map,
        )
        if identity.date:
            md_filename = f"{identity.date}_{subject}.md"
        elif identity.lecture_number:
            md_filename = f"{identity.resolved_stem}.md"
        else:
            mtime = os.path.getmtime(docx_path)
            date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            md_filename = f"{date_str}_{subject}_{docx_path.stem}.md"
            identity = identity.merge(LectureIdentity(date=date_str))

        return identity, subject, self.workspace.training_data_dir / md_filename

    def analyze_docx(self, docx_path: Path | str) -> LectureDiffAnalysis:
        """Extract one reviewed `.docx`, pair baseline/Matn source, and classify diffs."""
        self.workspace.training_data_dir.mkdir(parents=True, exist_ok=True)
        target_path = Path(docx_path)
        identity, subject, md_filepath = self._resolve_deliverable_target(target_path)

        if md_filepath.exists():
            return LectureDiffAnalysis(
                docx_path=target_path,
                markdown_path=md_filepath,
                identity=identity,
                skipped_existing=True,
            )

        try:
            text = extract_text(target_path)
        except DocxArchiveError as exc:
            return LectureDiffAnalysis(
                docx_path=target_path,
                markdown_path=md_filepath,
                identity=identity,
                read_error=str(exc),
            )

        md_filepath.write_text(text, encoding="utf-8")

        ai_baseline = self.find_ai_baseline(identity, subject=subject)
        if ai_baseline is None:
            return LectureDiffAnalysis(
                docx_path=target_path,
                markdown_path=md_filepath,
                identity=identity,
            )

        ai_text = ai_baseline.read_text(encoding="utf-8")
        cues = detect_new_student_cues(ai_text, text)
        matn_source_path = self.find_matn_source(identity)
        matn_source_text = read_matn_source_content(matn_source_path) if matn_source_path else None
        matn_diffs = tuple(classify_matn_diffs(ai_text, text, matn_source=matn_source_text))

        return LectureDiffAnalysis(
            docx_path=target_path,
            markdown_path=md_filepath,
            identity=identity,
            ai_baseline_path=ai_baseline,
            matn_source_path=matn_source_path,
            cues=cues,
            matn_diffs=matn_diffs,
        )

    def run(self) -> DiffLoopRunResult:
        """Scan OneDrive reviewed folders, extract new deliverables, and consolidate Diff Loop findings."""
        self.workspace.training_data_dir.mkdir(parents=True, exist_ok=True)
        deliverables = self.scan_deliverables()
        if not deliverables:
            return DiffLoopRunResult()

        extracted: list[Path] = []
        skipped: list[Path] = []
        failed: list[tuple[Path, str]] = []
        analyses: list[LectureDiffAnalysis] = []
        all_inserted = []
        all_removed = []
        all_matn_diffs: list[MatnDiffItem] = []

        for docx_path in deliverables:
            analysis = self.analyze_docx(docx_path)
            analyses.append(analysis)
            if analysis.skipped_existing:
                skipped.append(docx_path)
                continue
            if analysis.read_error is not None:
                failed.append((docx_path, analysis.read_error))
                continue

            extracted.append(analysis.markdown_path)
            all_inserted.extend(analysis.cues.inserted)
            all_removed.extend(analysis.cues.removed)
            all_matn_diffs.extend(analysis.matn_diffs)

        return DiffLoopRunResult(
            scanned_count=len(deliverables),
            extracted_paths=tuple(extracted),
            skipped_paths=tuple(skipped),
            failed_paths=tuple(failed),
            analyses=tuple(analyses),
            consolidated_cues=CueResult(inserted=all_inserted, removed=all_removed),
            consolidated_matn_diffs=tuple(all_matn_diffs),
        )


def main(
    *,
    workspace: WorkspaceConfig | None = None,
    catalog: RuleCatalog | None = None,
) -> int:
    """Run the unified Diff Loop Analyzer and print the consolidated report."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    analyzer = DiffLoopAnalyzer(workspace=workspace, catalog=catalog)
    result = analyzer.run()
    report = result.format_report()
    if report:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
