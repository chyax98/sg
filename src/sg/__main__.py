#!/usr/bin/env python -W ignore::DeprecationWarning
"""Entry point for python -m sg."""
import warnings
warnings.filterwarnings("ignore")

from sg.cli import cli  # noqa: E402

if __name__ == "__main__":
    cli()
