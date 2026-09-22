import sys
import os
import re
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def count_words(text: str) -> int:
    return len(text.strip().split())

def find_sentence_boundaries(text: str):
    """
    Finds positions of sentence-ending punctuation or natural Arabic speech pauses.
    """
    pattern = re.compile(r'([.؟!:\n]|\bطالب:)\s*')
    boundaries = [m.end() for m in pattern.finditer(text)]
    if not boundaries or boundaries[-1] != len(text):
        boundaries.append(len(text))
    return boundaries

def smart_chunk_text(text: str, target_words: int = 1300, min_words: int = 1000, max_words: int = 1600) -> list:
    """
    Splits text into chunks of target_words at natural sentence boundaries.
    Guarantees no word truncation and clean sentence boundaries.
    """
    text = text.strip()
    if not text:
        return []

    words = text.split()
    total_words = len(words)
    if total_words <= max_words:
        return [text]

    boundaries = find_sentence_boundaries(text)
    chunks = []
    current_start = 0
    
    while current_start < len(text):
        remaining_text = text[current_start:]
        remaining_words = count_words(remaining_text)
        
        if remaining_words <= max_words:
            chunks.append(remaining_text.strip())
            break
            
        best_split_pos = None
        best_word_diff = float('inf')
        
        for pos in boundaries:
            if pos <= current_start:
                continue
            candidate = text[current_start:pos]
            c_words = count_words(candidate)
            
            if c_words < min_words:
                continue
            
            diff = abs(c_words - target_words)
            if diff < best_word_diff:
                best_word_diff = diff
                best_split_pos = pos
                
            if c_words >= max_words:
                break
                
        if not best_split_pos:
            for pos in boundaries:
                if pos > current_start:
                    candidate = text[current_start:pos]
                    c_words = count_words(candidate)
                    diff = abs(c_words - target_words)
                    if diff < best_word_diff:
                        best_word_diff = diff
                        best_split_pos = pos
                    if c_words > target_words:
                        break
                        
        if not best_split_pos or best_split_pos <= current_start:
            candidate_words = remaining_text.split()[:target_words]
            chunk_str = " ".join(candidate_words)
            chunks.append(chunk_str.strip())
            current_start += len(chunk_str)
        else:
            chunk_str = text[current_start:best_split_pos].strip()
            chunks.append(chunk_str)
            current_start = best_split_pos

    return chunks

def chunk_file(file_path: str, output_dir: str = None, target_words: int = 1300):
    src_path = Path(file_path)
    if not src_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
        
    content = src_path.read_text(encoding='utf-8')
    chunks = smart_chunk_text(content, target_words=target_words)
    
    if output_dir is None:
        output_dir = src_path.parent / f"{src_path.stem}_مقاطع"
    else:
        output_dir = Path(output_dir)
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    created_files = []
    for idx, chunk in enumerate(chunks, 1):
        chunk_file = output_dir / f"{src_path.stem}_جزء_{idx:02d}.txt"
        chunk_file.write_text(chunk, encoding='utf-8')
        created_files.append((chunk_file, count_words(chunk)))
        
    print(f"Successfully split into {len(chunks)} chunks in: {output_dir}")
    for f, cnt in created_files:
        print(f"  - {f.name}: {cnt} words")
    return created_files

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py scripts/chunk_transcript.py <input_transcript_file> [target_words]")
        sys.exit(1)
        
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 1300
    chunk_file(sys.argv[1], target_words=target)
