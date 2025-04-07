# %%
import os
import re
import argparse
from typing import List, Tuple

def normalize_text(txt: str) -> str:
    """
    Normalize text so that common punctuation and whitespace differences
    don't break matching.
    """
    txt = txt.replace("“", '"').replace("”", '"')
    txt = txt.replace("‘", "'").replace("’", "'")
    txt = txt.replace("—", "-").replace("–", "-")
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()

def parse_srt_time(timestr: str) -> float:
    """Convert 'HH:MM:SS,mmm' -> total seconds as float."""
    hours, minutes, seconds_milli = timestr.split(':')
    seconds, millis = seconds_milli.split(',')
    total_seconds = int(hours)*3600 + int(minutes)*60 + int(seconds) + float(millis)/1000
    return total_seconds

def format_srt_time(total_seconds: float) -> str:
    """Convert total seconds (float) -> 'HH:MM:SS,mmm' string."""
    hours = int(total_seconds // 3600)
    remainder = total_seconds % 3600
    minutes = int(remainder // 60)
    seconds = int(remainder % 60)
    millis = int(round((total_seconds - int(total_seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

def parse_srt(srt_path: str) -> List[Tuple[int, float, float, str]]:
    """
    Parse an SRT file into a list of tuples:
      (block_index, start_time_seconds, end_time_seconds, text_combined).
    """
    blocks = []
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    raw_blocks = re.split(r'\n\s*\n', content)
    for block in raw_blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        # First line: block index
        index_str = lines[0].strip()
        if not index_str.isdigit():
            continue
        block_index = int(index_str)

        # Second line: "HH:MM:SS,mmm --> HH:MM:SS,mmm"
        time_line = lines[1].strip()
        start_str, _, end_str = time_line.split()
        start_seconds = parse_srt_time(start_str)
        end_seconds = parse_srt_time(end_str)

        # Remaining lines: subtitle text
        subtitle_lines = lines[2:]
        combined_text = " ".join(ln.strip() for ln in subtitle_lines).strip()

        blocks.append((block_index, start_seconds, end_seconds, combined_text))
    return blocks

def load_paragraphs_from_docx(docx_path: str) -> List[str]:
    """Load paragraphs from a DOCX file."""
    from docx import Document
    doc = Document(docx_path)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return paragraphs

def merge_srt_by_paragraph(
    srt_blocks: List[Tuple[int, float, float, str]],
    paragraphs: List[str]
) -> List[Tuple[int, float, float, str]]:
    """
    Merge SRT blocks so each paragraph from `paragraphs` is a single block.
    Once the normalized text matches exactly, finalize that paragraph.
    """
    merged = []
    current_index = 1
    srt_i = 0
    n_srt = len(srt_blocks)

    for paragraph in paragraphs:
        paragraph_norm = normalize_text(paragraph)

        accumulated_text = ""
        start_time = None
        end_time = None

        start_srt_i = srt_i

        while srt_i < n_srt:
            _, block_start, block_end, block_text = srt_blocks[srt_i]

            if start_time is None:
                start_time = block_start
            end_time = block_end

            if accumulated_text:
                accumulated_text += " " + block_text
            else:
                accumulated_text = block_text

            accum_norm = normalize_text(accumulated_text)

            if accum_norm == paragraph_norm:
                merged.append((current_index, start_time, end_time, paragraph))
                current_index += 1
                srt_i += 1
                break
            elif paragraph_norm.startswith(accum_norm):
                srt_i += 1
            else:
                srt_i = start_srt_i
                break

    return merged

def write_srt(
    merged_blocks: List[Tuple[int, float, float, str]],
    output_path: str
):
    """Write the merged SRT blocks to a file in standard SRT format."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for idx, start_sec, end_sec, text in merged_blocks:
            f.write(f"{idx}\n")
            f.write(f"{format_srt_time(start_sec)} --> {format_srt_time(end_sec)}\n")
            f.write(text.strip() + "\n\n")

def process_folder(folder_path: str):
    """
    For each matching .srt/.docx pair in `folder_path`, merge them and overwrite
    the original .srt with the merged content.
    """
    all_files = os.listdir(folder_path)
    srt_files = {f for f in all_files if f.lower().endswith(".srt")}
    docx_files = {f for f in all_files if f.lower().endswith(".docx")}

    for srt_file in srt_files:
        base_name, _ = os.path.splitext(srt_file)
        docx_candidate = base_name + ".docx"
        if docx_candidate in docx_files:
            srt_path = os.path.join(folder_path, srt_file)
            docx_path = os.path.join(folder_path, docx_candidate)

            # 1) Parse
            srt_blocks = parse_srt(srt_path)
            paragraphs = load_paragraphs_from_docx(docx_path)

            # 2) Merge
            merged_blocks = merge_srt_by_paragraph(srt_blocks, paragraphs)

            # 3) Overwrite the original .srt
            write_srt(merged_blocks, srt_path)
            print(f"Overwrote '{srt_file}' with merged blocks: {len(merged_blocks)}")

def main():
    parser = argparse.ArgumentParser(description="Merge SRT by matching paragraphs in DOCX, overwriting original SRT files.")
    parser.add_argument(
        "--input-folder",
        "-i",
        required=True,
        help="Folder containing matching .srt and .docx files"
    )
    args = parser.parse_args()

    process_folder(args.input_folder)

if __name__ == "__main__":
    main()



