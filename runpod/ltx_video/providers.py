import os
import shutil
import time

import gradio as gr
from PIL import Image

from .comfy import load_workflow
from .media import MediaValidationError, mux_original_audio, validate_video


def uploaded_path(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("path") or value.get("name")
    return getattr(value, "path", None) or getattr(value, "name", None)


class LtxTextImageProvider:
    def __init__(self, comfy, workflow_url):
        self.comfy = comfy
        self.workflow_url = workflow_url

    def generate(self, mode, image_filepath, prompt, width, height, duration, seed, progress):
        if not prompt or not prompt.strip():
            raise gr.Error("Enter a prompt.")

        progress(0, desc="Starting ComfyUI...")
        self.comfy.ensure_running()
        os.makedirs(self.comfy.input_path, exist_ok=True)

        video_width = max(256, round(width / 32) * 32)
        video_height = max(256, round(height / 32) * 32)
        workflow = load_workflow(self.workflow_url)

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
                os.path.join(self.comfy.input_path, dummy_name)
            )
            workflow["167"]["inputs"]["image"] = dummy_name
        else:
            if image_filepath is None:
                raise gr.Error("Upload an image for Image-to-Video.")
            workflow["290"]["inputs"]["value"] = False
            filename = os.path.basename(image_filepath)
            shutil.copy(image_filepath, os.path.join(self.comfy.input_path, filename))
            workflow["167"]["inputs"]["image"] = filename

        progress(0.2, desc="Queuing generation...")
        started_at = time.time()
        prompt_id = self.comfy.queue_prompt(workflow)["prompt_id"]
        self.comfy.wait_for_prompt(prompt_id, progress)

        video = self.comfy.latest_video(since=started_at)
        if video is None:
            raise gr.Error("ComfyUI finished but no MP4 output was found.")

        progress(1.0, desc="Done")
        return video


class ComfyVideoToVideoProvider:
    def __init__(self, comfy, backend_config):
        self.comfy = comfy
        self.config = backend_config

    @property
    def label(self):
        return self.config.get("label", self.config["id"])

    def _workflow_source(self):
        workflow = self.config.get("workflow", {})
        return workflow.get("path") or workflow.get("url")

    def _copy_to_input(self, path, prefix):
        extension = os.path.splitext(path)[1].lower()
        filename = f"{prefix}_{int(time.time() * 1000)}{extension}"
        destination = os.path.join(self.comfy.input_path, filename)
        shutil.copy(path, destination)
        return filename

    def _apply_patch(self, workflow, patch, value):
        node_id = str(patch["node"])
        input_name = patch["input"]
        if node_id not in workflow:
            raise gr.Error(f"Workflow is missing node {node_id} for backend {self.config['id']}.")
        workflow[node_id].setdefault("inputs", {})[input_name] = value

    def _apply_patch_group(self, workflow, group_name, value):
        patches = self.config.get("patches", {}).get(group_name, [])
        for patch in patches:
            self._apply_patch(workflow, patch, value)

    def generate(
        self,
        input_video,
        prompt,
        reference_files,
        target_width,
        target_height,
        seed,
        preserve_audio,
        progress,
    ):
        if not prompt or not prompt.strip():
            raise gr.Error("Enter a video-to-video prompt.")

        input_video = uploaded_path(input_video)
        reference_files = [uploaded_path(path) for path in (reference_files or [])]
        reference_files = [path for path in reference_files if path]

        source = self._workflow_source()
        if not source:
            raise gr.Error(
                f"{self.label} is registered but has no workflow JSON configured. "
                "Add a ComfyUI API workflow path or URL in runpod/model_manifest.json."
            )

        max_duration = int(self.config.get("limits", {}).get("max_duration_seconds", 60))
        try:
            info = validate_video(input_video, max_duration=max_duration)
        except MediaValidationError as error:
            raise gr.Error(str(error)) from error

        progress(0, desc="Starting ComfyUI...")
        self.comfy.ensure_running()
        os.makedirs(self.comfy.input_path, exist_ok=True)

        progress(0.1, desc="Preparing video-to-video inputs...")
        try:
            workflow = load_workflow(source)
        except FileNotFoundError as error:
            ui_source = self.config.get("workflow", {}).get("ui_source_url")
            message = (
                f"{self.label} needs an API workflow JSON at {source}. "
                "Run setup_v2v_ltx23.sh to download the source workflow, open it in ComfyUI, "
                "export it as API JSON, and save it to that path."
            )
            if ui_source:
                message += f" Source workflow: {ui_source}"
            raise gr.Error(message) from error
        except ValueError as error:
            raise gr.Error(
                f"{self.label} is pointed at a ComfyUI editor workflow. Export it as API JSON "
                "from ComfyUI and update runpod/model_manifest.json to the API JSON path."
            ) from error
        video_name = self._copy_to_input(input_video, "v2v_input")
        reference_names = []
        for index, reference_path in enumerate(reference_files or []):
            if reference_path:
                reference_names.append(self._copy_to_input(reference_path, f"v2v_ref_{index}"))

        self._apply_patch_group(workflow, "prompt", prompt)
        self._apply_patch_group(workflow, "video", video_name)
        self._apply_patch_group(workflow, "reference_images", reference_names)
        self._apply_patch_group(workflow, "width", max(256, round(target_width / 32) * 32))
        self._apply_patch_group(workflow, "height", max(256, round(target_height / 32) * 32))
        self._apply_patch_group(workflow, "fps", round(info["fps"], 3))
        self._apply_patch_group(workflow, "seed", int(seed))
        for patch in self.config.get("static_patches", []):
            self._apply_patch(workflow, patch, patch.get("value"))

        progress(0.2, desc="Queuing video-to-video generation...")
        started_at = time.time()
        prompt_id = self.comfy.queue_prompt(workflow)["prompt_id"]
        self.comfy.wait_for_prompt(prompt_id, progress)

        video = self.comfy.latest_video(since=started_at)
        if video is None:
            raise gr.Error("ComfyUI finished but no MP4 output was found.")

        if preserve_audio:
            progress(0.95, desc="Muxing original audio...")
            mux_dir = os.path.join(self.comfy.output_path, "muxed")
            video = mux_original_audio(video, input_video, mux_dir)

        progress(1.0, desc="Done")
        return video
