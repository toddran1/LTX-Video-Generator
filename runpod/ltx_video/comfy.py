import glob
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request

import gradio as gr


class ComfyClient:
    def __init__(self, comfy_path, port):
        self.comfy_path = comfy_path
        self.port = int(port)
        self.output_path = os.path.join(comfy_path, "output")
        self.input_path = os.path.join(comfy_path, "input")

    def is_running(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            return sock.connect_ex(("127.0.0.1", self.port)) == 0

    def boot(self):
        if not os.path.exists(self.comfy_path):
            raise RuntimeError(
                f"ComfyUI was not found at {self.comfy_path}. Run runpod/setup_ltx23.sh first."
            )

        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
        subprocess.Popen(
            ["python", "main.py", "--listen", "127.0.0.1", "--port", str(self.port)],
            cwd=self.comfy_path,
        )

        start_time = time.time()
        while not self.is_running():
            if time.time() - start_time > 180:
                raise RuntimeError("ComfyUI failed to start within 3 minutes.")
            time.sleep(2)

    def ensure_running(self):
        if not self.is_running():
            self.boot()

    def queue_prompt(self, workflow):
        data = json.dumps({"prompt": workflow}).encode("utf-8")
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/prompt", data=data)
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"ComfyUI API error: {error.read().decode()}") from error

    def wait_for_prompt(self, prompt_id, progress):
        while True:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/history/{prompt_id}"
                ) as response:
                    history = json.loads(response.read())
                if str(prompt_id) in history:
                    return history[str(prompt_id)]

                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/queue") as response:
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

    def latest_video(self, since=None):
        videos = glob.glob(f"{self.output_path}/**/*.mp4", recursive=True)
        videos += glob.glob(f"{self.output_path}/*.mp4")
        if since is not None:
            videos = [path for path in videos if os.path.getctime(path) >= since]
        if not videos:
            return None
        return max(videos, key=os.path.getctime)


def load_workflow_from_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def load_workflow(path_or_url):
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return load_workflow_from_url(path_or_url)
    with open(path_or_url, "r", encoding="utf-8") as workflow_file:
        return json.load(workflow_file)

