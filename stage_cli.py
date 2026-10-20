"""Command-line options shared by the stage scripts.

Every stage that reads and writes a CSV takes --input and --output, so running
a stage on a sample never requires editing config.py. Has no dependency on the
tavily package.
"""

from __future__ import annotations

import argparse


def build_parser(
    description: str, default_input: str, default_output: str
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--input", dest="input_csv", default=default_input,
        help=f"input CSV (default: {default_input})",
    )
    parser.add_argument(
        "--output", dest="output_csv", default=default_output,
        help=f"output CSV (default: {default_output})",
    )
    return parser
