import os
import pysrt
import tempfile
import argparse
import random
from moviepy import VideoFileClip
from Katna.video import Video
from Katna.writer import KeyFrameDiskWriter
from PIL import Image
import numpy as np

def srt_time_to_seconds(srt_time):
    return (
        srt_time.hours * 3600
        + srt_time.minutes * 60
        + srt_time.seconds
        + srt_time.milliseconds / 1000
    )

def process_subtitle_chunk(clip, sub, chunk_index, output_dir, frames_to_extract=5):
    chunk_folder_name = f"chunk_{chunk_index:03d}"
    chunk_folder = os.path.join(output_dir, chunk_folder_name)
    os.makedirs(chunk_folder, exist_ok=True)

    keyframes_folder = os.path.join(chunk_folder, "keyframes")
    os.makedirs(keyframes_folder, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        temp_chunk_path = tmp.name

    clip.write_videofile(
        temp_chunk_path,
        codec="libx264",
        audio_codec="aac",
    )

    vd = Video()
    disk_writer = KeyFrameDiskWriter(location=keyframes_folder)

    try:
        extracted = vd.extract_video_keyframes(
            no_of_frames=frames_to_extract,
            file_path=temp_chunk_path,
            writer=disk_writer,
        )
        if len(os.listdir(keyframes_folder)) == 0:
            print(f"Fallback: Extracting random frame for chunk {chunk_index}")

            # Load the temporary video chunk
            chunk_clip = VideoFileClip(temp_chunk_path)
            duration = chunk_clip.duration

            if duration > 0:
                random_time = random.uniform(0, duration)
                frame = chunk_clip.get_frame(random_time)
                image = Image.fromarray(np.uint8(frame))
                fallback_frame_path = os.path.join(keyframes_folder, f"fallback_frame.jpg")
                image.save(fallback_frame_path)
                print(f"Saved fallback frame at {fallback_frame_path}")

            chunk_clip.close()
    finally:
        if os.path.exists(temp_chunk_path):
            os.remove(temp_chunk_path)

    info_path = os.path.join(chunk_folder, "_info.txt")
    with open(info_path, "w", encoding="utf-8") as info_file:
        info_file.write(f"{sub.start} --> {sub.end}\n")
        info_file.write(sub.text.strip() + "\n")

def process_video_with_srt(video_path, srt_path, output_dir, frames_to_extract=5):
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    video_output_folder = os.path.join(output_dir, base_name)
    os.makedirs(video_output_folder, exist_ok=True)

    subs = pysrt.open(srt_path)
    video = VideoFileClip(video_path)

    for i, sub in enumerate(subs, start=1):
        start_time = srt_time_to_seconds(sub.start)
        end_time = srt_time_to_seconds(sub.end)

        chunk_clip = video.subclipped(start_time, end_time)

        process_subtitle_chunk(
            clip=chunk_clip,
            sub=sub,
            chunk_index=i,
            output_dir=video_output_folder,
            frames_to_extract=frames_to_extract,
        )

    video.close()
    print(f"Finished processing: {video_path}")


def batch_process_videos(input_dir, output_dir="output", frames_to_extract=5):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    files = os.listdir(input_dir)
    video_files = [f for f in files if f.lower().endswith(".mp4")]

    for video_file in video_files:
        base_name = os.path.splitext(video_file)[0]
        srt_file = base_name + ".srt"

        video_path = os.path.join(input_dir, video_file)
        srt_path = os.path.join(input_dir, srt_file)

        if not os.path.exists(srt_path):
            print(f"Skipping '{video_file}': No matching .srt found.")
            continue

        process_video_with_srt(
            video_path=video_path,
            srt_path=srt_path,
            output_dir=output_dir,
            frames_to_extract=frames_to_extract,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process videos and extract keyframes by subtitle chunks.")
    parser.add_argument("--input_dir", type=str, default="lectures", help="Input directory containing .mp4 and .srt files")
    parser.add_argument("--output_dir", type=str, default="frames", help="Directory to save output")
    parser.add_argument("--frames", type=int, default=10, help="Number of keyframes to extract per chunk")

    args = parser.parse_args()

    batch_process_videos(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        frames_to_extract=args.frames,
    )



