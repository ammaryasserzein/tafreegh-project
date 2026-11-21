"""CLI entrypoint for verifying exported Tafreegh Word documents."""

import sys

from tafreegh.verify_docx import main

if __name__ == "__main__":
    sys.exit(main())
