#!/usr/bin/env python
"""Entry point wrapper to suppress warnings."""
import os
import warnings

# Suppress deprecation warnings before any imports
# These warnings come from upstream dependencies (websockets, uvicorn) and don't affect functionality
os.environ.setdefault("PYTHONWARNINGS", "ignore::DeprecationWarning")
warnings.filterwarnings("ignore", category=DeprecationWarning)


def main():
    from sg.cli import cli
    cli()


if __name__ == "__main__":
    main()
