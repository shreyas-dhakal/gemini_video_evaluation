import os
import base64
import toml
import openai
import json
import time
from collections import defaultdict

config = toml.load("secrets.toml")
os.environ["OPENAI_API_KEY"] = config["OPENAI_API_KEY"]

def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def ask_logo_position(frame_b64, logo_b64):
    for attempt in range(3):
        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": [
                        {
                            "type": "text",
                            "text": (
                                "Does the keyframe image contain the same logo as the reference image? "
                                "If yes, give its position: top-left, bottom-right, center, etc. "
                                "If no logo is found, reply only 'No'."
                            )
                        },
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}" }},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{logo_b64}" }}
                    ]}
                ],
                max_tokens=100,
            )
            content = response.choices[0].message.content.strip()
            if content.lower() == "no":
                return None
            return content
        except Exception as e:
            print(f"⚠️ Error on attempt {attempt + 1}: {e}")
            time.sleep(2)
    return None

logo_folder = "logo"
logo_images = {}
for logo_file in os.listdir(logo_folder):
    if logo_file.lower().endswith((".jpg", ".jpeg", ".png")):
        logo_path = os.path.join(logo_folder, logo_file)
        logo_images[logo_file] = encode_image(logo_path)

frames_root = "frames"
final_results = []


for video_name in sorted(os.listdir(frames_root)):
    video_path = os.path.join(frames_root, video_name)
    if not os.path.isdir(video_path):
        continue

    print(f"Processing video: {video_name}")

    for chunk_name in sorted(os.listdir(video_path)):
        chunk_path = os.path.join(video_path, chunk_name)
        keyframe_dir = os.path.join(chunk_path, "keyframes")
        transcript_path = os.path.join(chunk_path, "_info.txt")

        chunk_result = {
            "video": video_name,
            "timestamp": "",
            "logo_position": None,
        }

        if not os.path.isdir(keyframe_dir):
            continue

        if os.path.exists(transcript_path):
            with open(transcript_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    chunk_result["timestamp"] = lines[0].strip()

        found = False
        for frame_file in sorted(os.listdir(keyframe_dir)):
            if not frame_file.lower().endswith((".jpg", ".jpeg", ".png")):
                continue

            frame_path = os.path.join(keyframe_dir, frame_file)
            frame_b64 = encode_image(frame_path)

            for logo_name, logo_b64 in logo_images.items():
                position = ask_logo_position(frame_b64, logo_b64)
                if position:
                    chunk_result["logo_position"] = position
                    found = True
                    break

            if found:
                break

        if chunk_result["logo_position"] != "No.":
            final_results.append(chunk_result)

video_results = defaultdict(list)
for result in final_results:
    video_results[result["video"]].append(result)

output_folder = "logo_reports"
os.makedirs(output_folder, exist_ok=True)

for video_name, chunks in video_results.items():
    safe_name = video_name.replace(" ", "_").replace("/", "_")
    output_path = os.path.join(output_folder, f"{safe_name}_logo_results.json")
    with open(output_path, "w") as f:
        json.dump(chunks, f, indent=2)
    print(f"Saved logo results for `{video_name}` to `{output_path}`")

print(f"Completed. {len(video_results)} video report(s) saved in `{output_folder}`.")




