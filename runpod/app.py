import glob
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

import gradio as gr
from PIL import Image


COMFY_PATH = os.environ.get("COMFY_PATH", "/workspace/ComfyUI")
OUTPUT_PATH = os.path.join(COMFY_PATH, "output")
INPUT_PATH = os.path.join(COMFY_PATH, "input")
COMFY_PORT = int(os.environ.get("COMFY_PORT", "8188"))
GRADIO_PORT = int(os.environ.get("GRADIO_PORT", "7860"))
WORKFLOW_URL = os.environ.get(
    "WORKFLOW_URL",
    "https://raw.githubusercontent.com/AICHUCKY/Comfyui-Workflows/AICHUCKY-patch-1/Ltx2.3%20.json",
)


def is_server_running(port=COMFY_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def boot_server():
    if not os.path.exists(COMFY_PATH):
        raise RuntimeError(
            f"ComfyUI was not found at {COMFY_PATH}. Run runpod/setup_ltx23.sh first."
        )

    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    subprocess.Popen(
        ["python", "main.py", "--listen", "127.0.0.1", "--port", str(COMFY_PORT)],
        cwd=COMFY_PATH,
    )

    start_time = time.time()
    while not is_server_running():
        if time.time() - start_time > 180:
            raise RuntimeError("ComfyUI failed to start within 3 minutes.")
        time.sleep(2)


def load_workflow():
    request = urllib.request.Request(WORKFLOW_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def queue_prompt(workflow):
    data = json.dumps({"prompt": workflow}).encode("utf-8")
    request = urllib.request.Request(f"http://127.0.0.1:{COMFY_PORT}/prompt", data=data)
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"ComfyUI API error: {error.read().decode()}") from error


def get_latest_video():
    videos = glob.glob(f"{OUTPUT_PATH}/**/*.mp4", recursive=True)
    videos += glob.glob(f"{OUTPUT_PATH}/*.mp4")
    if not videos:
        return None
    return max(videos, key=os.path.getctime)


def wait_for_prompt(prompt_id, progress):
    while True:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{COMFY_PORT}/history/{prompt_id}"
            ) as response:
                history = json.loads(response.read())
            if str(prompt_id) in history:
                return

            with urllib.request.urlopen(f"http://127.0.0.1:{COMFY_PORT}/queue") as response:
                queue = json.loads(response.read())
            running = queue.get("queue_running", [])
            pending = queue.get("queue_pending", [])
            if not any(str(job[1]) == str(prompt_id) for job in running + pending):
                raise gr.Error("Generation failed or the ComfyUI worker crashed.")
        except gr.Error:
            raise
        except Exception:
            pass

        progress(0.5, desc="Rendering video...")
        time.sleep(3)


def generate_video(mode, image_filepath, prompt, width, height, duration, seed, progress=gr.Progress()):
    progress(0, desc="Starting ComfyUI...")
    if not is_server_running():
        boot_server()

    os.makedirs(INPUT_PATH, exist_ok=True)

    video_width = max(256, round(width / 32) * 32)
    video_height = max(256, round(height / 32) * 32)
    workflow = load_workflow()

    workflow["292"]["inputs"]["value"] = video_width
    workflow["293"]["inputs"]["value"] = video_height
    workflow["285"]["inputs"]["value"] = 24
    workflow["121"]["inputs"]["text"] = prompt
    workflow["291"]["inputs"]["value"] = duration
    workflow["137"]["inputs"]["sampler_name"] = "lcm"
    workflow["360"]["inputs"]["sigmas"] = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
    workflow["129"]["inputs"]["cfg"] = 1.0
    workflow["115"]["inputs"]["noise_seed"] = int(seed)
    workflow["138"]["inputs"]["sampler_name"] = "euler_cfg_pp"
    workflow["359"]["inputs"]["sigmas"] = "0.85, 0.7250, 0.4219, 0.0"
    workflow["103"]["inputs"]["cfg"] = 1.0
    workflow["114"]["inputs"]["noise_seed"] = int(seed) + 1

    progress(0.1, desc="Preparing inputs...")
    if mode == "Text-to-Video":
        workflow["290"]["inputs"]["value"] = True
        dummy_name = "dummy_t2v.jpg"
        Image.new("RGB", (video_width, video_height), "black").save(
            os.path.join(INPUT_PATH, dummy_name)
        )
        workflow["167"]["inputs"]["image"] = dummy_name
    else:
        if image_filepath is None:
            raise gr.Error("Upload an image for Image-to-Video.")
        workflow["290"]["inputs"]["value"] = False
        filename = os.path.basename(image_filepath)
        shutil.copy(image_filepath, os.path.join(INPUT_PATH, filename))
        workflow["167"]["inputs"]["image"] = filename

    progress(0.2, desc="Queuing generation...")
    prompt_id = queue_prompt(workflow)["prompt_id"]
    wait_for_prompt(prompt_id, progress)

    video = get_latest_video()
    if video is None:
        raise gr.Error("ComfyUI finished but no MP4 output was found.")

    progress(1.0, desc="Done")
    return video


with gr.Blocks(theme=gr.themes.Monochrome()) as demo:
    gr.Markdown("# LTX 2.3 Video Generator")
    gr.Markdown("Generate text-to-video or image-to-video clips on your Runpod A100.")
    with gr.Row():
        with gr.Column(scale=1):
            mode_selector = gr.Radio(
                ["Text-to-Video", "Image-to-Video"],
                value="Text-to-Video",
                label="Generation Mode",
            )
            image_input = gr.Image(type="filepath", label="Starting Image", visible=False)
            prompt_input = gr.Textbox(label="Prompt", placeholder="A cinematic shot...", lines=3)
            with gr.Row():
                width_slider = gr.Slider(minimum=256, maximum=1920, step=32, value=832, label="Width")
                height_slider = gr.Slider(minimum=256, maximum=1080, step=32, value=480, label="Height")
            with gr.Row():
                duration_slider = gr.Slider(minimum=1, maximum=10, step=1, value=3, label="Duration")
                seed_input = gr.Number(value=43, label="Seed", precision=0)
            generate_btn = gr.Button("Generate Video", variant="primary")
        with gr.Column(scale=1):
            video_output = gr.Video(label="Generated Output")

    def update_visibility(mode):
        return gr.update(visible=(mode == "Image-to-Video"))

    mode_selector.change(fn=update_visibility, inputs=mode_selector, outputs=image_input)
    generate_btn.click(
        fn=generate_video,
        inputs=[
            mode_selector,
            image_input,
            prompt_input,
            width_slider,
            height_slider,
            duration_slider,
            seed_input,
        ],
        outputs=video_output,
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=GRADIO_PORT, share=False)
