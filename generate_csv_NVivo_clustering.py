import os
import pandas as pd
import argparse
import re


def extract_codes_and_quotes(codes_dir, sentences):
    code_names = []
    quotes = []

    for filename in os.listdir(codes_dir):
        if filename == ".DS_Store":
            continue

        text_file_path = os.path.join(codes_dir, filename)
        code = filename[:-4]

        skip_first_line = True
        current_line = ""

        with open(text_file_path, "r") as f:
            for line in f:
                if skip_first_line:
                    skip_first_line = False
                    continue

                line = line.strip()

                if line.startswith("Reference"):
                    if current_line == "":
                        continue
                    quotes.append(current_line)
                    code_names.append(code)
                    current_line = ""
                else:
                    current_line = current_line + line

        code_names.append(code)
        quotes.append(current_line)

    return code_names, quotes



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

    # Read sentences from input file
    print(f"Reading sentences from: {args.input_sentences}")
    with open(args.input_sentences, "r") as f:
        sentences = [line.strip() for line in f if line.strip()]
    print(f"Read {len(sentences)} sentences.")

    # All sentences have a primary key at the end. Extract it, and make dictionary mapping key to sentence.
    sentence_key_map = {}
    pattern = r"\((\d+)\)\s*$"
    pattern_for_sub = re.compile(r"\s*\(\d+\)\s*$")
    all_keys = []
    for sentence in sentences:
        key = re.search(pattern, sentence).group(1)
        # cleaned = pattern_for_sub.sub("", sentence)
        sentence_key_map[key] = sentence    
        all_keys.append(key)

    # All quotes that do not belong to 
    # Extract codes and quotes from NVivo Codes directory
    print(f"Reading codes from: {args.codes_dir}")
    code_names, quotes = extract_codes_and_quotes(args.codes_dir, sentences)
    print(f"Extracted {len(quotes)} muddy cards across {len(set(code_names))} codes.")

    # Get all the strings that do have a manual code.
    quotes_with_code = []
    i = 0
    for sentence in quotes:
        i+=1
        key = re.search(pattern, sentence).group(1)
        quotes_with_code.append(key)

    # If a string does not have a manual code, make it it's own cluster by taking first 25 characters
    for k in all_keys:
        if k not in quotes_with_code:
            code_names.append(sentence_key_map[k][:40])
            quotes.append(sentence_key_map[k])
   
    # Save the manual codes to csv
    data = {
        "Code_Name" : code_names,
        "Quote": quotes
    }
    df = pd.DataFrame(data)
    df.to_csv(args.csv_output, index = False)



if __name__ == "__main__":
    main()
