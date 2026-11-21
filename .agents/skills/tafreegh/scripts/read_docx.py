"""CLI entrypoint for DOCX text extraction."""

import sys

from tafreegh.read_docx import main

if __name__ == "__main__":
    sys.exit(main())
