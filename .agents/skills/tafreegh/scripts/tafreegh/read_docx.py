"""Thin CLI entrypoint for reading .docx files via the Word OOXML Gateway."""

from __future__ import annotations

import sys

from . import word_gateway

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 1:
        print("Usage: py .agents/skills/tafreegh/scripts/read_docx.py <path_to_docx>")
        return 1
    try:
        print(word_gateway.extract_text(args[0]))
    except word_gateway.DocxArchiveError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
