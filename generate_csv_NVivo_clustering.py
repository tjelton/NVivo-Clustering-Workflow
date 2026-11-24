"""
Generate a CSV of clusters from NVivo code exports.

Each NVivo code (exported as one .txt file per code) is a cluster. Inside an export,
every block of coded text sits under a "Reference N - x% Coverage" header. A reference
can hold a single response or a block of consecutive responses (one per line), so every
line under a reference is treated as its own response. Each response is identified by
the primary key in brackets at the end of its line, e.g. "nothing (105)".

Responses in the sorted text file that are not in any code become their own
single-response (singleton) cluster.
"""

import argparse
import os
import re
import sys
from collections import defaultdict

import pandas as pd

# Primary key in brackets at the end of a response, e.g. "nothing (105)".
KEY_PATTERN = re.compile(r"\((\d+)\)\s*$")

# Header NVivo writes above each block of coded text, e.g. "Reference 3 - 1.28% Coverage".
REFERENCE_HEADER = re.compile(r"^Reference \d+ - [\d.]+% Coverage$")

# NVivo exports straight quotes as curly ones. Undo that before comparing text.
QUOTE_NORMALISATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})

SINGLETON_NAME_LENGTH = 40


def read_sentences(path):
    """Return {key: sentence} for the sorted text file that was imported into NVivo."""
    sentences = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            match = KEY_PATTERN.search(line)
            if match is None:
                sys.exit(f"Error: line {line_number} of '{path}' does not end with a key like (N): {line!r}")
            key = match.group(1)
            if key in sentences:
                sys.exit(f"Error: key ({key}) appears more than once in '{path}'.")
            sentences[key] = line
    return sentences


def extract_codes_and_keys(codes_dir):
    """
    Read every NVivo code export in codes_dir.

    Returns (assignments, problems, reference_counts):
      assignments      -- list of (code_name, key, nvivo_line), one per response
      problems         -- lines that could not be matched to a response
      reference_counts -- (total references, references holding more than one response)
    """
    assignments = []
    problems = []
    total_references = 0
    multi_line_references = 0

    for filename in sorted(os.listdir(codes_dir)):
        if not filename.endswith(".txt"):
            continue

        code = filename[:-4]
        with open(os.path.join(codes_dir, filename), "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()

        responses_in_reference = 0

        # The first line is NVivo's summary ("Files\\... - § 3 references coded ..."), so skip it.
        for line in lines[1:] + ["Reference 0 - 0% Coverage"]:  # sentinel closes the last reference
            line = line.strip()
            if not line:
                continue

            if REFERENCE_HEADER.match(line):
                if responses_in_reference > 0:
                    total_references += 1
                    if responses_in_reference > 1:
                        multi_line_references += 1
                responses_in_reference = 0
                continue

            match = KEY_PATTERN.search(line)
            if match is None:
                problems.append(
                    f'Code "{code}": line does not end with a key like (N). The highlight in NVivo '
                    f"probably stopped before the end of the line, or a response was split over "
                    f"two lines: {line!r}"
                )
                continue

            assignments.append((code, match.group(1), line))
            responses_in_reference += 1

    return assignments, problems, (total_references, multi_line_references)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a CSV of codes and sentences from NVivo exports."
    )
    parser.add_argument(
        "input_sentences",
        help="Path to the input file containing sentences (one per line).",
    )
    parser.add_argument(
        "--codes-dir",
        default="Codes",
        help="Directory containing NVivo code text files (default: Codes).",
    )
    parser.add_argument(
        "--csv-output",
        default="codes_and_quotes.csv",
        help="Path to write the output CSV file (default: codes_and_quotes.csv).",
    )
    args = parser.parse_args()

    print(f"Reading sentences from: {args.input_sentences}")
    sentences = read_sentences(args.input_sentences)
    print(f"Read {len(sentences)} sentences.")

    print(f"Reading codes from: {args.codes_dir}")
    assignments, problems, (total_references, multi_line_references) = extract_codes_and_keys(args.codes_dir)

    # Check every coded response exists in the sorted file and is in exactly one code.
    codes_by_key = defaultdict(list)
    for code, key, nvivo_line in assignments:
        codes_by_key[key].append(code)
        if key not in sentences:
            problems.append(f'Code "{code}": key ({key}) is not in {args.input_sentences}: {nvivo_line!r}')

    for key, codes in codes_by_key.items():
        if len(codes) > 1 and key in sentences:
            listed = ", ".join(f'"{c}"' for c in codes)
            problems.append(
                f"Response ({key}) is in more than one code ({listed}). Each response must be in "
                f"exactly one code: {sentences[key]!r}"
            )

    if problems:
        print(f"\nFound {len(problems)} problem(s) in the NVivo codes. Fix these in NVivo, re-export, and re-run:\n")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)

    # A coded line that differs from the sorted file usually means only part of the line was highlighted.
    partial = [
        (code, line, sentences[key])
        for code, key, line in assignments
        if line.translate(QUOTE_NORMALISATION) != sentences[key].translate(QUOTE_NORMALISATION)
    ]
    if partial:
        print(
            f"\nWarning: {len(partial)} coded line(s) do not exactly match the sorted file. The full "
            f"sentence from the sorted file is used in the CSV, but check the highlight in NVivo:"
        )
        for code, line, sentence in partial:
            print(f'  - Code "{code}": NVivo has {line!r}, sorted file has {sentence!r}')

    print(
        f"Extracted {len(assignments)} responses from {total_references} references "
        f"({multi_line_references} holding more than one response) across "
        f"{len({code for code, _, _ in assignments})} codes."
    )

    # The CSV always uses the sentence from the sorted file, so it is the same for every annotator.
    code_names = [code for code, _, _ in assignments]
    quotes = [sentences[key] for _, key, _ in assignments]

    # Each response that is not in a code becomes its own cluster, named after its first 40 characters.
    used_names = set(code_names)
    uncoded = [key for key in sentences if key not in codes_by_key]
    for key in uncoded:
        name = sentences[key][:SINGLETON_NAME_LENGTH]
        if name in used_names:  # stop two singletons that start the same way merging into one cluster
            name = f"{name} ({key})"
        used_names.add(name)
        code_names.append(name)
        quotes.append(sentences[key])
    print(f"{len(uncoded)} responses were not in any code and became singleton clusters.")

    df = pd.DataFrame({"Code_Name": code_names, "Quote": quotes})
    df.to_csv(args.csv_output, index=False)
    print(f"Wrote {len(df)} rows to {args.csv_output}")


if __name__ == "__main__":
    main()
