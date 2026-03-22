#!/usr/bin/env python
"""Entry point wrapper to suppress warnings."""
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)


def main():
    from sg.cli import cli
    cli()


if __name__ == "__main__":
    main()
