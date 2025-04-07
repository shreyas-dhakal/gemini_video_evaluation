import os
import re
import json
import toml
import argparse
import base64
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, as_completed

config = toml.load("secrets.toml")
genai.configure(api_key=config["GEMINI_API_KEY"])

parser = argparse.ArgumentParser(description="Generate instructional quality reports from video chunk folders.")
parser.add_argument("--input_dir", type=str, default="frames", help="Path to parent input directory (e.g., 'output')")
parser.add_argument("--output_dir", type=str, default="reports", help="Path to parent output directory (e.g., 'reports')")
args = parser.parse_args()

parent_input_dir = args.input_dir
parent_report_dir = args.output_dir
os.makedirs(parent_report_dir, exist_ok=True)

def parse_time_to_seconds(timestr):
    timestr = timestr.replace(',', '.')
    h, m, s = timestr.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)

def parse_timestamp_range(range_str):
    left, right = range_str.split('-->')
    start_sec = parse_time_to_seconds(left.strip())
    end_sec = parse_time_to_seconds(right.strip())
    return start_sec, end_sec

def load_keyframe_images(directory, max_images=5):
    if not os.path.exists(directory):
        return []
    image_files = sorted(
        [f for f in os.listdir(directory) if f.lower().endswith(('.jpg', '.jpeg'))]
    )[:max_images]

    images = []
    for f in image_files:
        with open(os.path.join(directory, f), "rb") as img_file:
            images.append({
                "mime_type": "image/jpeg",
                "data": img_file.read()
            })
    return images


def generate_instructional_quality_report(subtitles, images, timestamp_range):
    model = genai.GenerativeModel("gemini-2.5-pro-exp-03-25")
    prompt = (
        "You are an expert video quality analyst.\n"
        "Evaluate the given video chunk using keyframe images and subtitles. Use these categories:\n"
        "1) Signaling\n2) Weeding\n3) Matching Modality\n4) Visual Quality\n"
        "5) Consistency\n6) Accessibility\n7) Technical Quality\n\n"
        "Score each category from 1 to 3 and give detailed improvement suggestions.\n\n"
        "Return ONLY valid JSON in this format:\n"
        "{ \"summary\": \"...\", \"evaluation\": { \"Signaling\": {\"score\": ..., \"comment\": \"...\"}, ... }, \"timestamp\": \"...\" }"
    )

    try:
        response = model.generate_content([
            prompt,
            f"Subtitles:\n{subtitles}",
            *images
        ])
        raw_content = response.text.strip()

        if raw_content.startswith("```json"):
            raw_content = re.sub(r"^```json\s*", "", raw_content)
            raw_content = re.sub(r"\s*```$", "", raw_content)

        report_json = json.loads(raw_content)
        report_json["timestamp"] = timestamp_range
        return json.dumps(report_json, indent=2)

    except Exception as e:
        raise RuntimeError(f"Gemini generation error: {e}")

def generate_suggestions_for_whole_video(report_data):
    model = genai.GenerativeModel("gemini-2.5-pro-exp-03-25")
    prompt = (
        "You are a video quality expert. Based on the following chunk evaluations (score 1-3), identify which chunks need improvement.\n\n"
        "Return a JSON array with:\n"
        "- 'timestamp': timestamp of the chunk\n"
        "- 'suggestion': very specific suggestions for improvement\n\n"
        "Only include chunks that scored low or need work."
    )

    try:
        response = model.generate_content([
            prompt,
            f"{json.dumps(report_data)}"
        ])
        raw_output = response.text.strip()

        if raw_output.startswith("```json"):
            raw_output = re.sub(r"^```json\s*", "", raw_output)
            raw_output = re.sub(r"\s*```$", "", raw_output)

        return json.loads(raw_output)

    except Exception as e:
        raise RuntimeError(f"Gemini suggestion generation error: {e}")


# Process each chunk folder (info.txt + keyframes)
def process_chunk_folder(chunk_folder):
    chunk_name = os.path.basename(chunk_folder)
    info_path = os.path.join(chunk_folder, "_info.txt")
    keyframe_dir = os.path.join(chunk_folder, "keyframes")

    if not os.path.exists(info_path):
        return {"status": "error", "chunk_name": chunk_name, "message": "_info.txt missing"}

    try:
        with open(info_path, "r", encoding="utf-8") as f:
            lines = f.read().strip().splitlines()

        if len(lines) < 2:
            raise ValueError("Not enough data in _info.txt")

        timestamp_range = lines[0].strip()
        subtitles_text = " ".join(line.strip() for line in lines[1:])
        start_sec, end_sec = parse_timestamp_range(timestamp_range)
        images = load_keyframe_images(keyframe_dir)

        if not images:
            raise FileNotFoundError("No keyframes found")

        report_body = generate_instructional_quality_report(
            subtitles=subtitles_text,
            images=images,
            timestamp_range=timestamp_range
        )

        return {
            "status": "success",
            "chunk_name": chunk_name,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "timestamp_range": timestamp_range,
            "report_body": report_body
        }

    except Exception as e:
        return {"status": "error", "chunk_name": chunk_name, "message": str(e)}


# Main Runner
if __name__ == "__main__":
    video_folders = sorted(
        [
            os.path.join(parent_input_dir, f)
            for f in os.listdir(parent_input_dir)
            if os.path.isdir(os.path.join(parent_input_dir, f))
        ]
    )

    for video_dir in video_folders:
        video_id = os.path.basename(video_dir)
        report_output_dir = os.path.join(parent_report_dir, video_id)
        single_report_path = os.path.join(report_output_dir, f"{video_id}_individual_report.json")
        suggestions_output_path = os.path.join(report_output_dir, f"combined_report_{video_id}.json")
        os.makedirs(report_output_dir, exist_ok=True)

        print(f"\nProcessing {video_id}...")

        all_entries = os.listdir(video_dir)
        chunk_folders = sorted(
            [
                os.path.join(video_dir, d)
                for d in all_entries
                if d.lower().startswith("chunk_") and os.path.isdir(os.path.join(video_dir, d))
            ]
        )

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(process_chunk_folder, folder) for folder in chunk_folders]
            for future in as_completed(futures):
                result = future.result()
                if result["status"] == "error":
                    print(f"Error in {result['chunk_name']}: {result['message']}")
                else:
                    print(f"Done: {result['chunk_name']}")
                results.append(result)

        successful_results = [r for r in results if r["status"] == "success"]
        successful_results.sort(key=lambda r: r["start_sec"])
        combined_json = [json.loads(item["report_body"]) for item in successful_results]

        with open(single_report_path, "w", encoding="utf-8") as out_file:
            json.dump(combined_json, out_file, indent=2)
        print(f"Report saved: {single_report_path}")

        try:
            suggestions = generate_suggestions_for_whole_video(combined_json)
            with open(suggestions_output_path, "w", encoding="utf-8") as out_file:
                json.dump(suggestions, out_file, indent=2)
            print(f"Suggestions saved: {suggestions_output_path}")
        except Exception as e:
            print(f"Failed to generate suggestions for {video_id}: {e}")
