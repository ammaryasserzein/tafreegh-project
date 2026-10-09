import os
import glob
import re
import datetime
from pathlib import Path
import read_docx
from diff_cues import detect_new_student_cues, format_cue_report

ONEDRIVE_BASE = r"C:\Users\L\OneDrive\1. دوري"
# Hardcoding the project root to avoid Arabic character mangling bugs in Python's resolve()
PROJECT_ROOT = Path(r"C:\Users\L\Documents\Tafreegh_Project")
TRAINING_DATA_DIR = PROJECT_ROOT / "04_Training_Data"
# AI baseline files (_AI.md) may live in either directory
AI_OUTPUTS_DIR = PROJECT_ROOT / "03_AI_Outputs"
RAW_INPUTS_DIR = PROJECT_ROOT / "02_Raw_Inputs"


def _find_ai_baseline(date_str: str, subject: str, filename_stem: str) -> Path | None:
    """Search for the corresponding _AI.md baseline file in known directories."""
    candidate_name = f"{date_str}_{subject}_AI.md"
    candidate_name_stem = f"{filename_stem}_AI.md"
    for directory in (AI_OUTPUTS_DIR, RAW_INPUTS_DIR):
        for candidate in (directory / candidate_name_stem, directory / candidate_name):
            if candidate.exists():
                return candidate
    # Fallback: search by date prefix in both dirs
    for directory in (AI_OUTPUTS_DIR, RAW_INPUTS_DIR):
        if directory.exists():
            for f in directory.iterdir():
                if f.name.startswith(date_str) and f.name.endswith("_AI.md"):
                    return f
    return None


def main():
    if not TRAINING_DATA_DIR.exists():
        TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # We are looking for C:\Users\L\OneDrive\1. دوري\[Subject]\(تم التسليم)\*.docx
    search_pattern_1 = os.path.join(ONEDRIVE_BASE, "**", "(تم التسليم)", "*.docx")
    search_pattern_2 = os.path.join(ONEDRIVE_BASE, "**", "تم التسليم", "*.docx")
    docx_files = glob.glob(search_pattern_1, recursive=True) + glob.glob(search_pattern_2, recursive=True)
    
    if not docx_files:
        print("No files found to process.")
        return

    from diff_cues import detect_new_student_cues, format_cue_report, CueResult
    
    overall_result = CueResult(inserted=[], removed=[])

    for docx_path in docx_files:
        print(f"Processing {docx_path}...")
        
        p = Path(docx_path)
        subject_folder = p.parent.parent.name
        
        # Clean subject name: remove prefix numbers like "1. " or "2. "
        subject = re.sub(r'^\d+\.\s*', '', subject_folder)
        
        # Extract date from filename if it's in the format YYYY-MM-DD
        filename_stem = p.stem
        date_match = re.search(r'\d{4}-\d{2}-\d{2}', filename_stem)
        
        if date_match:
            date_str = date_match.group(0)
            md_filename = f"{date_str}_{subject}.md"
        else:
            # Fallback to file modification date
            mtime = os.path.getmtime(docx_path)
            date_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
            md_filename = f"{date_str}_{subject}_{filename_stem}.md"
        
        md_filepath = TRAINING_DATA_DIR / md_filename
        
        # Skip if already processed
        if md_filepath.exists():
            print(f"Skipping {docx_path} - already processed as {md_filename}")
            continue
        
        # Extract text
        text = read_docx.extract_text(docx_path)
        if text.startswith("Error reading docx:"):
            print(f"Failed to read {docx_path}: {text}")
            continue
            
        # Write to md file
        with open(md_filepath, 'w', encoding='utf-8') as f:
            f.write(text)
            
        print(f"Saved extracted text to {md_filepath} (Original docx kept safe in OneDrive)")

        # --- Diff Loop: detect new student cue candidates ---
        ai_baseline = _find_ai_baseline(date_str, subject, filename_stem)
        if ai_baseline:
            ai_text = ai_baseline.read_text(encoding='utf-8')
            result = detect_new_student_cues(ai_text, text)
            if result.inserted:
                overall_result.inserted.extend(result.inserted)
                print(f"  ↳ Found {len(result.inserted)} candidate cue(s) from diff with {ai_baseline.name}")
            if result.removed:
                overall_result.removed.extend(result.removed)
                print(f"  ↳ Found {len(result.removed)} removed cue(s) from diff with {ai_baseline.name}")
        else:
            print(f"  ↳ No AI baseline (_AI.md) found for {md_filename} — skipping diff analysis")

    # Print consolidated cue report
    if overall_result.inserted or overall_result.removed:
        print("\n" + format_cue_report(overall_result))


if __name__ == "__main__":
    main()
