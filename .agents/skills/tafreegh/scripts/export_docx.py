"""CLI entrypoint for exporting Tafreegh markdown transcripts to Word."""

import sys

from tafreegh.export_docx import main

if __name__ == "__main__":
    sys.exit(main())
