import glob

def combine_text_reports(output_file="MASTER_CONSOLIDATED_REPORT.txt"):
    # 1. Grab all .txt files in the current folder
    files = glob.glob("*.txt")
    
    # 2. Filter out the output file itself if it already exists
    files = [f for f in files if f != output_file]
    
    if not files:
        print("No text files found to combine.")
        return

    print(f"Combining {len(files)} files sequentially...")

    with open(output_file, "w", encoding="utf-8") as outfile:
        # Global header to orient the LLM
        outfile.write("SYSTEM NOTE: The following content is a sequence of multiple reports.\n")
        outfile.write("Each section starts with a clear 'REPORT HEADER' identifying the source file.\n\n")

        for file_path in sorted(files): # Sorted ensures a predictable sequence
            outfile.write(f"{'='*60}\n")
            outfile.write(f"REPORT HEADER: {file_path}\n")
            outfile.write(f"{'='*60}\n\n")

            try:
                # Primary attempt with UTF-8
                try:
                    with open(file_path, "r", encoding="utf-8") as infile:
                        outfile.write(infile.read())
                except UnicodeDecodeError:
                    # Fallback for files with special characters (like the 0xb2 error)
                    with open(file_path, "r", encoding="latin-1") as infile:
                        outfile.write(infile.read())
                
                # Add spacing before the next header
                outfile.write("\n\n")
                print(f"Successfully added: {file_path}")
                
            except Exception as e:
                print(f"Error processing {file_path}: {e}")

    print(f"\nSUCCESS! All content combined into: {output_file}")

if __name__ == "__main__":
    combine_text_reports()