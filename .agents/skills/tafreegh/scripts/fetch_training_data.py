"""CLI entrypoint for fetching reviewed training data from OneDrive."""

import sys

from tafreegh.fetch_training_data import main

if __name__ == "__main__":
    sys.exit(main())
