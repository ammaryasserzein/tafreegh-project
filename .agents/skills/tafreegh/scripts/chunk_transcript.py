"""CLI entrypoint for transcript chunking."""

import sys

from tafreegh.chunk_transcript import main

if __name__ == "__main__":
    sys.exit(main())
