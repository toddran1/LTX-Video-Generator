import json
import math
import os
import shutil
import subprocess
import time

from PIL import Image


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
MIN_COMFY_AUDIO_SECONDS = 1.0


class MediaValidationError(ValueError):
    pass


def require_binary(name):
    if shutil.which(name) is None:
        raise RuntimeError(f"Required binary '{name}' was not found. Re-run setup.")


def ffprobe_video(path):
    require_binary("ffprobe")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        path,
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def _ratio_to_float(value):
    if not value or value == "0/0":
        return 0.0
    numerator, denominator = value.split("/", 1)
    denominator_value = float(denominator)
    if denominator_value == 0:
        return 0.0
    return float(numerator) / denominator_value


def video_info(path):
    data = ffprobe_video(path)
    video_stream = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"), None)
    audio_stream = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"), None)
    if video_stream is None:
        raise MediaValidationError("Input file does not contain a video stream.")

    duration = float(video_stream.get("duration") or data.get("format", {}).get("duration") or 0)
    return {
        "duration": duration,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "fps": _ratio_to_float(video_stream.get("avg_frame_rate")),
        "codec": video_stream.get("codec_name", "unknown"),
        "has_audio": audio_stream is not None,
        "audio_duration": float(audio_stream.get("duration") or 0) if audio_stream else 0,
        "format": data.get("format", {}).get("format_name", "unknown"),
    }


def validate_video(path, max_duration=60):
    if not path:
        raise MediaValidationError("Upload an input video.")
    if not os.path.exists(path):
        raise MediaValidationError("Input video was not found on disk.")

    extension = os.path.splitext(path)[1].lower()
    if extension not in SUPPORTED_VIDEO_EXTENSIONS:
        raise MediaValidationError(
            f"Unsupported video type '{extension}'. Use mp4, mov, mkv, or webm."
        )

    info = video_info(path)
    if info["duration"] <= 0:
        raise MediaValidationError("Could not determine input video duration.")
    if info["duration"] > max_duration:
        raise MediaValidationError(
            f"Input video is {info['duration']:.1f}s. Maximum supported duration is {max_duration}s."
        )
    if info["width"] <= 0 or info["height"] <= 0:
        raise MediaValidationError("Could not determine input video resolution.")
    if info["fps"] <= 0:
        raise MediaValidationError("Could not determine input video frame rate.")
    return info


def copy_video_for_audio_workflow(source_video, destination, info):
    """Copy a video for ComfyUI workflows that require an audio stream."""
    duration = float(info.get("duration") or 0)
    audio_duration = float(info.get("audio_duration") or 0)
    if info.get("has_audio") and audio_duration >= MIN_COMFY_AUDIO_SECONDS:
        shutil.copy(source_video, destination)
        return destination

    require_binary("ffmpeg")
    audio_duration = max(duration, MIN_COMFY_AUDIO_SECONDS)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        source_video,
        "-f",
        "lavfi",
        "-t",
        f"{audio_duration:.3f}",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        destination,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return destination


def extract_first_frame(source_video, destination):
    require_binary("ffmpeg")
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        source_video,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        destination,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return destination


def mux_original_audio(generated_video, source_video, output_dir):
    info = video_info(source_video)
    if not info["has_audio"]:
        return generated_video

    require_binary("ffmpeg")
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(generated_video))[0]
    output_path = os.path.join(output_dir, f"{base}_original_audio_{int(time.time())}.mp4")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        generated_video,
        "-i",
        source_video,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        output_path,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return output_path


def upscale_video(source_video, output_dir, width, height):
    require_binary("ffmpeg")
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(source_video))[0]
    output_path = os.path.join(output_dir, f"{base}_{width}x{height}_{int(time.time())}.mp4")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        source_video,
        "-vf",
        f"scale={width}:{height}:flags=lanczos",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        output_path,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return output_path


def build_reference_montage(reference_paths, destination):
    if not reference_paths:
        raise MediaValidationError("Upload one or more reference images.")

    images = []
    for path in reference_paths:
        with Image.open(path) as image:
            images.append(image.convert("RGB"))

    tile_size = 512
    columns = 1 if len(images) == 1 else 2
    rows = math.ceil(len(images) / columns)
    canvas = Image.new("RGB", (columns * tile_size, rows * tile_size), "black")

    for index, image in enumerate(images):
        image = image.copy()
        image.thumbnail((tile_size, tile_size), Image.Resampling.LANCZOS)
        x = (index % columns) * tile_size + (tile_size - image.width) // 2
        y = (index // columns) * tile_size + (tile_size - image.height) // 2
        canvas.paste(image, (x, y))

    os.makedirs(os.path.dirname(destination), exist_ok=True)
    canvas.save(destination, format="PNG")
    return destination
