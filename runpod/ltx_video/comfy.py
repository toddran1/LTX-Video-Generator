import glob
import json
import os
import re
import socket
import subprocess
import sys
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
            [sys.executable, "main.py", "--listen", "127.0.0.1", "--port", str(self.port)],
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

    def queue_prompt(self, workflow, extra_data=None):
        payload = {"prompt": workflow}
        if extra_data:
            payload["extra_data"] = extra_data
        data = json.dumps(payload).encode("utf-8")
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

            error_message = self.latest_error_message(log_offset=log_offset)
            if error_message:
                raise gr.Error(error_message)

            percent, status = self.render_status(prompt_id, started_at, log_offset=log_offset)
            progress(percent, desc=status)
            time.sleep(3)

    def queue_state(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/queue") as response:
            return json.loads(response.read())

    def prompt_history(self, prompt_id):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/history/{prompt_id}") as response:
            history = json.loads(response.read())
        return history.get(str(prompt_id), {})

    def prompt_error(self, prompt_id):
        record = self.prompt_history(prompt_id)
        status = record.get("status", {})
        for message in status.get("messages", []):
            if not message or message[0] != "execution_error":
                continue
            details = message[1] if len(message) > 1 and isinstance(message[1], dict) else {}
            exception = (details.get("exception_message") or "").strip()
            node_type = details.get("node_type")
            if exception and node_type:
                return f"{node_type}: {exception}"
            if exception:
                return exception
        return None

    def latest_error_message(self, log_offset=0):
        text = self._recent_log_text(log_offset=log_offset)
        if not text:
            return None

        clean_text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text.replace("\x00", ""))
        patterns = [
            r"!!! Exception during processing !!!\s*(.+)",
            r"(CUDA error: .+)",
            r"(ValueError: .+)",
            r"(RuntimeError: .+)",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, clean_text)
            if matches:
                message = str(matches[-1]).strip().splitlines()[0]
                return f"ComfyUI generation failed: {message}"

        if "Exception in thread" in clean_text and "prompt_worker" in clean_text:
            return "ComfyUI generation failed: prompt worker crashed."
        return None

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
        status = self._render_phase_status(log_offset=log_offset)
        percent = status.get("percent", 0.2)
        message = status.get("message") or "Queued or loading workflow"
        message = f"{message} | elapsed {elapsed}; prompt {prompt_id}"

        return min(max(percent, 0.2), 0.9), message

    def _render_phase_status(self, log_offset=0):
        text = self._recent_log_text(log_offset=log_offset)
        if not text:
            return {"percent": 0.2, "message": "Queued or loading workflow"}

        clean_text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text.replace("\x00", ""))
        lines = [line.strip() for line in re.split(r"[\r\n]+", clean_text) if line.strip()]
        step_lines = [line for line in lines if re.search(r"\d+%\|.*\|\s*\d+/\d+\s*\[", line)]
        latest_step = step_lines[-1] if step_lines else None

        if "Prompt executed in" in clean_text:
            return {"percent": 0.9, "message": "Finalizing output"}
        if "Save Video" in clean_text or "VHS_VideoCombine" in clean_text or "Create Video" in clean_text:
            return {"percent": 0.86, "message": "Encoding and saving video"}
        if "Audio VAE Decode" in clean_text or "Requested to load AudioVAE" in clean_text:
            return {"percent": 0.82, "message": "Decoding audio"}
        if "VAE Decode" in clean_text or "VAEDecode" in clean_text:
            return {"percent": 0.78, "message": "Decoding video frames"}

        if latest_step:
            step_percent = self._step_percent(latest_step)
            step_count = self._step_count(latest_step)
            pass_index = self._sampling_pass_index(step_lines)
            total_passes = self._estimated_sampling_pass_count(step_lines)
            percent = 0.25
            if step_percent is not None:
                pass_span = 0.5 / max(total_passes, 1)
                percent = 0.25 + ((pass_index - 1) * pass_span) + (step_percent * pass_span)

            pass_label = f" pass {pass_index}/{total_passes}" if total_passes > 1 else ""
            if step_count:
                current, total = step_count
                message = f"Sampling{pass_label}: step {current}/{total}"
            else:
                message = f"Sampling{pass_label}: {latest_step}"
            return {"percent": percent, "message": message}

        if "Requested to load LTXAV" in clean_text:
            return {"percent": 0.18, "message": "Loading LTX video model"}
        if "Requested to load LTXAVTEModel" in clean_text or "CLIP/text encoder model load" in clean_text:
            return {"percent": 0.14, "message": "Loading text encoder"}
        if "VAE load device" in clean_text:
            return {"percent": 0.1, "message": "Loading VAE"}
        if "got prompt" in clean_text:
            return {"percent": 0.05, "message": "Prompt accepted by ComfyUI"}

        return {"percent": 0.2, "message": "Preparing generation"}

    def _recent_log_text(self, log_offset=0):
        if not os.path.exists(self.log_path):
            return None

        try:
            with open(self.log_path, "rb") as log_file:
                log_file.seek(0, os.SEEK_END)
                size = log_file.tell()
                start = max(int(log_offset or 0), size - 200_000, 0)
                log_file.seek(start)
                return log_file.read().decode("utf-8", errors="ignore")
        except OSError:
            return None

    def _step_percent(self, step_line):
        match = re.search(r"(\d+)%\|", step_line)
        if not match:
            return None
        return int(match.group(1)) / 100

    def _step_count(self, step_line):
        match = re.search(r"\|\s*(\d+)/(\d+)\s*\[", step_line)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    def _sampling_pass_index(self, step_lines):
        if not step_lines:
            return 1

        pass_index = 1
        previous_current = None
        for line in step_lines:
            step_count = self._step_count(line)
            if not step_count:
                continue
            current, _ = step_count
            if previous_current is not None and current < previous_current:
                pass_index += 1
            previous_current = current
        return pass_index

    def _estimated_sampling_pass_count(self, step_lines):
        totals = []
        for line in step_lines:
            step_count = self._step_count(line)
            if step_count:
                totals.append(step_count[1])
        if len(set(totals)) >= 2:
            return len(set(totals))
        return max(1, self._sampling_pass_index(step_lines))

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

    def latest_image(self, since=None):
        images = []
        for extension in ("png", "jpg", "jpeg", "webp"):
            images += glob.glob(f"{self.output_path}/**/*.{extension}", recursive=True)
            images += glob.glob(f"{self.output_path}/*.{extension}")
        if since is not None:
            images = [path for path in images if os.path.getctime(path) >= since]
        if not images:
            return None
        return max(images, key=os.path.getctime)


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
