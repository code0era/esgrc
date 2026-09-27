"""
pipeline/scripts/text_report_combiner.py
Combine multiple text report files into one MASTER report.

CLI usage:
    python text_report_combiner.py \
        --inputs file1.txt file2.txt file3.txt \
        --output MASTER.txt \
        --label "ESGRC Module Unified Report"

Importable usage:
    from pipeline.scripts.text_report_combiner import combine_reports
    combine_reports(input_paths=["a.txt","b.txt"], output_path="MASTER.txt", label="...")
"""
import argparse
import logging
import os
from typing import List

logger = logging.getLogger(__name__)

SECTION_SEPARATOR = "\n\n" + "=" * 80 + "\n\n"

# FLOOR guard (log-only). An input section whose stripped content is shorter than
# this is treated as empty/near-empty - a script that ran but wrote no data. And a
# master whose total populated content is below the skeleton floor is almost
# certainly a data-population failure (headers/methodology, no numbers) - the exact
# failure that ships a client an empty report. These only WARN; combining still
# succeeds so nothing breaks.
_EMPTY_SECTION_CHARS = 50
_SKELETON_FLOOR_CHARS = 200


def combine_reports(
    input_paths: List[str],
    output_path: str,
    label: str = "Combined Report",
) -> None:
    """
    Combine multiple text report files into one file.

    Each section is preceded by a header:
        === {filename} ===

    Args:
        input_paths: List of absolute or relative paths to .txt files.
        output_path: Path where the combined output will be written.
        label:       Label used in the master file header.

    Raises:
        ValueError:       input_paths is empty.
        FileNotFoundError: any input file does not exist.
    """
    if not input_paths:
        raise ValueError("combine_reports: input_paths must not be empty.")

    # Validate all inputs exist before writing anything
    for path in input_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(f"combine_reports: input file not found: {path}")

    sections: List[str] = []
    empty_inputs: List[str] = []
    total_content_chars = 0

    for path in input_paths:
        filename = os.path.basename(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()

        if len(content) < _EMPTY_SECTION_CHARS:
            empty_inputs.append(filename)
        total_content_chars += len(content)

        section = f"=== {filename} ===\n\n{content}"
        sections.append(section)

    # FLOOR guard - surface a data-population failure in the logs (never raises).
    if empty_inputs:
        logger.warning(
            "combine_reports: %d/%d input section(s) empty/near-empty (<%d chars): %s - "
            "an analytics script may have run on empty/invalid input.",
            len(empty_inputs), len(sections), _EMPTY_SECTION_CHARS, ", ".join(empty_inputs),
        )
    if total_content_chars < _SKELETON_FLOOR_CHARS:
        logger.warning(
            "combine_reports: master '%s' has only %d chars of populated data across %d "
            "section(s) - possible DATA-POPULATION FAILURE (skeleton report). Check the "
            "upstream analytics inputs before this is sent to Claude / the client.",
            os.path.basename(output_path), total_content_chars, len(sections),
        )

    # Build the master document
    header = (
        f"{'=' * 80}\n"
        f"MASTER REPORT: {label}\n"
        f"Total sections: {len(sections)}\n"
        f"{'=' * 80}"
    )

    full_content = header + SECTION_SEPARATOR + SECTION_SEPARATOR.join(sections)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine multiple text report files into one MASTER file."
    )
    parser.add_argument(
        "--inputs", nargs="+", required=True,
        help="List of input .txt file paths"
    )
    parser.add_argument(
        "--output", required=True,
        help="Output file path for the combined report"
    )
    parser.add_argument(
        "--label", default="Combined Report",
        help="Label for the master report header"
    )
    args = parser.parse_args()
    combine_reports(
        input_paths=args.inputs,
        output_path=args.output,
        label=args.label,
    )
    print(f"Combined {len(args.inputs)} reports → {args.output}")


if __name__ == "__main__":
    main()
