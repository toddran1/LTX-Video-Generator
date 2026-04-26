import glob
import json
import os
import re
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
        self.log_path = os.environ.get(
            "COMFY_LOG_PATH",
            os.path.join(comfy_path, "comfyui.log"),
        )

    def is_running(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            return sock.connect_ex(("127.0.0.1", self.port)) == 0

    def boot(self):
        if not os.path.exists(self.comfy_path):
            raise RuntimeError(
                f"ComfyUI was not found at {self.comfy_path}. Run runpod/setup_ltx23.sh first."
            )

        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        log_file = open(self.log_path, "a", encoding="utf-8")
        subprocess.Popen(
            ["python", "main.py", "--listen", "127.0.0.1", "--port", str(self.port)],
            cwd=self.comfy_path,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
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

    def log_offset(self):
        if not os.path.exists(self.log_path):
            return 0
        try:
            return os.path.getsize(self.log_path)
        except OSError:
            return 0

    def wait_for_prompt(self, prompt_id, progress, log_offset=0):
        started_at = time.time()
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

            percent, status = self.render_status(prompt_id, started_at, log_offset=log_offset)
            progress(percent, desc=status)
            time.sleep(3)

    def queue_state(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/queue") as response:
            return json.loads(response.read())

    def interrupt(self):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/interrupt",
            data=b"{}",
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return response.read().decode("utf-8", errors="ignore")

    def render_status(self, prompt_id, started_at, log_offset=0):
        elapsed = self._format_duration(time.time() - started_at)
        latest_step = self._latest_step_line(log_offset=log_offset)
        percent = 0.5
        message = f"Rendering video... elapsed {elapsed}; prompt {prompt_id}"

        if latest_step:
            step_percent = self._step_percent(latest_step)
            if step_percent is not None:
                percent = 0.2 + (step_percent * 0.7)
            message = f"{latest_step} | elapsed {elapsed}; prompt {prompt_id}"

        return min(max(percent, 0.2), 0.9), message

    def _latest_step_line(self, log_offset=0):
        if not os.path.exists(self.log_path):
            return None

        try:
            with open(self.log_path, "rb") as log_file:
                log_file.seek(0, os.SEEK_END)
                size = log_file.tell()
                start = max(int(log_offset or 0), size - 200_000, 0)
                log_file.seek(start)
                text = log_file.read().decode("utf-8", errors="ignore")
        except OSError:
            return None

        text = text.replace("\x00", "")
        candidates = re.split(r"[\r\n]+", text)
        for line in reversed(candidates):
            cleaned = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line).strip()
            if re.search(r"\d+%\|.*\|\s*\d+/\d+\s*\[", cleaned):
                return cleaned
        return None

    def _step_percent(self, step_line):
        match = re.search(r"(\d+)%\|", step_line)
        if not match:
            return None
        return int(match.group(1)) / 100

    def _format_duration(self, seconds):
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

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
        workflow = load_workflow_from_url(path_or_url)
    else:
        if not os.path.exists(path_or_url):
            raise FileNotFoundError(path_or_url)
        with open(path_or_url, "r", encoding="utf-8") as workflow_file:
            workflow = json.load(workflow_file)

    if isinstance(workflow, dict) and "nodes" in workflow:
        raise ValueError(
            "This is a ComfyUI editor workflow. Export it as API JSON before using it "
            "with the Runpod backend."
        )
    return workflow
