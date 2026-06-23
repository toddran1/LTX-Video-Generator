import os
import shutil
import time

import gradio as gr
from PIL import Image

from .comfy import load_workflow
from .media import (
    MediaValidationError,
    build_reference_montage,
    copy_video_for_audio_workflow,
    extract_first_frame,
    mux_original_audio,
    upscale_video,
    validate_video,
)


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


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
        log_offset = self.comfy.log_offset()
        prompt_id = self.comfy.queue_prompt(workflow)["prompt_id"]
        self.comfy.wait_for_prompt(prompt_id, progress, log_offset=log_offset)

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

    def _output_resolution(self, output_resolution):
        resolutions = {
            "480p": (848, 480),
            "720p": (1280, 720),
            "1080p": (1920, 1080),
        }
        return resolutions.get(output_resolution, resolutions["720p"])

    def _resolve_path(self, path):
        if not path:
            return None
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if os.path.isabs(path):
            return path
        return os.path.join(PROJECT_ROOT, path)

    def _workflow_source(self):
        workflow = self.config.get("workflow", {})
        for key in ("repo_path", "path", "url"):
            source = self._resolve_path(workflow.get(key))
            if not source:
                continue
            if source.startswith("http://") or source.startswith("https://") or os.path.exists(source):
                return source
        return self._resolve_path(workflow.get("repo_path") or workflow.get("path") or workflow.get("url"))

    def _copy_to_input(self, path, prefix, extension=None):
        extension = extension or os.path.splitext(path)[1].lower()
        filename = f"{prefix}_{int(time.time() * 1000)}{extension}"
        destination = os.path.join(self.comfy.input_path, filename)
        shutil.copy(path, destination)
        return filename

    def _copy_video_to_input(self, path, info):
        extension = os.path.splitext(path)[1].lower()
        if not info.get("has_audio"):
            extension = ".mp4"
        filename = f"v2v_input_{int(time.time() * 1000)}{extension}"
        destination = os.path.join(self.comfy.input_path, filename)
        copy_video_for_audio_workflow(path, destination, info)
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

    def _apply_slot_patch(self, workflow, slot, value):
        patches = slot.get("patches") if isinstance(slot, dict) else None
        if patches:
            for patch in patches:
                self._apply_patch(workflow, patch, value)
            return
        self._apply_patch(workflow, slot, value)

    def _replace_node_references(self, workflow, source_node_id, replacement):
        for node in workflow.values():
            inputs = node.get("inputs", {})
            for key, value in list(inputs.items()):
                if isinstance(value, list) and value and str(value[0]) == str(source_node_id):
                    inputs[key] = list(replacement)

    def _prefer_loader(self, workflow, preferred_class_type, fallback_class_types):
        preferred_id = None
        fallback_ids = []
        fallback_types = set(fallback_class_types)
        for node_id, node in workflow.items():
            class_type = node.get("class_type")
            if class_type == preferred_class_type:
                preferred_id = node_id
            elif class_type in fallback_types:
                fallback_ids.append(node_id)

        if preferred_id is None:
            return

        replacement = [str(preferred_id), 0]
        for fallback_id in fallback_ids:
            self._replace_node_references(workflow, fallback_id, replacement)

    def _next_node_id(self, workflow):
        numeric_ids = [int(node_id) for node_id in workflow.keys() if str(node_id).isdigit()]
        return str(max(numeric_ids, default=0) + 1)

    def _insert_load_image_reference(self, workflow, image_name):
        reference_config = self.config.get("reference_image")
        if not reference_config:
            return False

        set_node_id = str(reference_config.get("set_node"))
        if set_node_id not in workflow:
            raise gr.Error(
                f"Workflow is missing reference image node {set_node_id} "
                f"for backend {self.config['id']}."
            )

        if reference_config.get("mode") == "load_image_input":
            input_name = reference_config.get("input", "image")
            workflow[set_node_id].setdefault("inputs", {})[input_name] = image_name
            return True

        loader_node_id = self._next_node_id(workflow)
        workflow[loader_node_id] = {
            "inputs": {
                "image": image_name,
            },
            "class_type": "LoadImage",
            "_meta": {
                "title": "Reference Image Loader",
            },
        }

        inputs = workflow[set_node_id].setdefault("inputs", {})
        input_name = reference_config.get("input")
        if input_name:
            inputs[input_name] = [loader_node_id, 0]
            return True

        for key, value in list(inputs.items()):
            if isinstance(value, list):
                inputs[key] = [loader_node_id, 0]
                return True

        inputs["image"] = [loader_node_id, 0]
        return True

    def _remove_passthrough_node(self, workflow, class_type, input_name):
        for node_id, node in list(workflow.items()):
            if node.get("class_type") != class_type:
                continue

            source = node.get("inputs", {}).get(input_name)
            if not source:
                continue

            for other_node in workflow.values():
                inputs = other_node.get("inputs", {})
                for key, value in list(inputs.items()):
                    if isinstance(value, list) and value and str(value[0]) == str(node_id):
                        inputs[key] = source
            workflow.pop(node_id, None)

    def _remove_nodes_by_class_type(self, workflow, class_types):
        remove_types = set(class_types)
        for node_id, node in list(workflow.items()):
            if node.get("class_type") in remove_types:
                workflow.pop(node_id, None)

    def _prepare_workflow_for_api(self, workflow):
        self._prefer_loader(workflow, "UnetLoaderGGUF", ["UNETLoader"])
        self._prefer_loader(workflow, "DualCLIPLoaderGGUF", ["DualCLIPLoader"])
        self._remove_passthrough_node(workflow, "LTX2SamplingPreviewOverride", "model")
        self._remove_nodes_by_class_type(workflow, ["easy showAnything"])

    def _set_optional_input(self, workflow, node_id, input_name, value):
        node = workflow.get(str(node_id))
        if not node:
            return False
        node.setdefault("inputs", {})[input_name] = value
        return True

    def _reference_image_name(self, input_video, reference_names):
        if reference_names:
            return reference_names[0]

        reference_config = self.config.get("reference_image", {})
        if reference_config.get("fallback") != "first_frame":
            return None

        filename = f"v2v_first_frame_{int(time.time() * 1000)}.jpg"
        destination = os.path.join(self.comfy.input_path, filename)
        extract_first_frame(input_video, destination)
        return filename

    def _resolve_reference_files(self, reference_files, reference_mode, reference_index):
        reference_files = [path for path in (reference_files or []) if path]
        if not reference_files:
            return []

        if reference_mode == "specific":
            selected_index = max(1, int(reference_index or 1)) - 1
            selected_index = min(selected_index, len(reference_files) - 1)
            return [reference_files[selected_index]]

        if reference_mode == "montage":
            montage_path = os.path.join(
                self.comfy.input_path,
                f"v2v_reference_montage_{int(time.time() * 1000)}.png",
            )
            build_reference_montage(reference_files, montage_path)
            return [montage_path]

        return [reference_files[0]]

    def generate(
        self,
        input_video,
        prompt,
        reference_files,
        reference_mode,
        reference_index,
        target_width,
        target_height,
        output_resolution,
        seed,
        preserve_audio,
        retake_full_video,
        retake_start,
        retake_end,
        transform_strength,
        prompt_cfg,
        nag_scale,
        progress,
        job_id=None,
        on_queued=None,
        on_completed=None,
        on_failed=None,
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
        reference_files = self._resolve_reference_files(reference_files, reference_mode, reference_index)

        progress(0.1, desc="Preparing video-to-video inputs...")
        try:
            workflow = load_workflow(source)
        except FileNotFoundError as error:
            workflow_config = self.config.get("workflow", {})
            ui_source = (
                workflow_config.get("source_repo_path")
                or workflow_config.get("ui_source_path")
                or workflow_config.get("ui_source_url")
            )
            message = (
                f"{self.label} needs an API workflow JSON at {source}. "
                "Open the source workflow in ComfyUI, export it as API JSON, "
                "and save it to the configured repo_path or /workspace fallback path."
            )
            if ui_source:
                message += f" Source workflow: {ui_source}"
            raise gr.Error(message) from error
        except ValueError as error:
            raise gr.Error(
                f"{self.label} is pointed at a ComfyUI editor workflow. Export it as API JSON "
                "from ComfyUI and update runpod/model_manifest.json to the API JSON path."
            ) from error
        self._prepare_workflow_for_api(workflow)
        video_name = self._copy_video_to_input(input_video, info)
        reference_names = []
        for index, reference_path in enumerate(reference_files or []):
            if reference_path:
                reference_names.append(self._copy_to_input(reference_path, f"v2v_ref_{index}"))

        self._apply_patch_group(workflow, "prompt", prompt)
        self._apply_patch_group(workflow, "video", video_name)
        self._apply_patch_group(workflow, "reference_images", reference_names)
        reference_image_name = self._reference_image_name(input_video, reference_names)
        if reference_image_name:
            self._insert_load_image_reference(workflow, reference_image_name)
            self._set_optional_input(workflow, "438", "bypass", False)
        else:
            self._set_optional_input(workflow, "438", "bypass", True)
            self._set_optional_input(workflow, "545", "strength", 0.25)
        base_width = max(256, round(target_width / 16) * 16)
        base_height = max(256, round(target_height / 16) * 16)
        self._apply_patch_group(workflow, "width", base_width)
        self._apply_patch_group(workflow, "height", base_height)
        self._apply_patch_group(workflow, "fps", round(info["fps"], 3))
        self._apply_patch_group(workflow, "seed", int(seed))
        if retake_full_video:
            self._apply_patch_group(workflow, "retake_start", 0.0)
            self._apply_patch_group(workflow, "retake_end", round(info["duration"], 3))
        else:
            start_seconds = max(0.0, float(retake_start))
            end_seconds = min(float(retake_end), info["duration"])
            if end_seconds <= start_seconds:
                raise gr.Error("Retake end must be greater than retake start.")
            self._apply_patch_group(workflow, "retake_start", start_seconds)
            self._apply_patch_group(workflow, "retake_end", round(end_seconds, 3))
        self._apply_patch_group(workflow, "transform_strength", float(transform_strength))
        self._apply_patch_group(workflow, "prompt_cfg", float(prompt_cfg))
        self._apply_patch_group(workflow, "nag_scale", float(nag_scale))
        for patch in self.config.get("static_patches", []):
            self._apply_patch(workflow, patch, patch.get("value"))

        progress(0.2, desc="Queuing video-to-video generation...")
        started_at = time.time()
        log_offset = self.comfy.log_offset()
        prompt_id = self.comfy.queue_prompt(workflow)["prompt_id"]
        if on_queued:
            on_queued(
                prompt_id=prompt_id,
                started_at=started_at,
                log_offset=log_offset,
                source_video=input_video,
                reference_files=reference_files,
            )
        self.comfy.wait_for_prompt(prompt_id, progress, log_offset=log_offset)

        video = self.comfy.latest_video(since=started_at)
        if video is None:
            if on_failed:
                on_failed("ComfyUI finished but no MP4 output was found.")
            raise gr.Error("ComfyUI finished but no MP4 output was found.")

        output_width, output_height = self._output_resolution(output_resolution)
        if (output_width, output_height) != (base_width, base_height):
            progress(
                0.9,
                desc=f"Upscaling rendered video to {output_resolution} ({output_width}x{output_height})...",
            )
            upscale_dir = os.path.join(self.comfy.output_path, "upscaled")
            video = upscale_video(video, upscale_dir, output_width, output_height)

        if preserve_audio:
            progress(0.95, desc="Muxing original audio...")
            mux_dir = os.path.join(self.comfy.output_path, "muxed")
            video = mux_original_audio(video, input_video, mux_dir)

        if on_completed:
            on_completed(
                output_path=video,
                completed_at=time.time(),
                prompt_id=prompt_id,
            )
        progress(1.0, desc="Done")
        return video


class ComfyImageProvider:
    def __init__(self, comfy, backend_config):
        self.comfy = comfy
        self.config = backend_config

    @property
    def label(self):
        return self.config.get("label", self.config["id"])

    def _resolve_path(self, path):
        if not path:
            return None
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if os.path.isabs(path):
            return path
        return os.path.join(PROJECT_ROOT, path)

    def _workflow_source(self):
        workflow = self.config.get("workflow", {})
        for key in ("repo_path", "path", "url"):
            source = self._resolve_path(workflow.get(key))
            if not source:
                continue
            if source.startswith("http://") or source.startswith("https://") or os.path.exists(source):
                return source
        return self._resolve_path(workflow.get("repo_path") or workflow.get("path") or workflow.get("url"))

    def _extra_data(self):
        auth = self.config.get("auth", {})
        extra_data = {}

        api_key_env = auth.get("comfy_org_api_key_env")
        if api_key_env:
            api_key = os.environ.get(api_key_env)
            if not api_key:
                raise gr.Error(
                    f"{self.label} requires `{api_key_env}` to be set for Comfy Org API access."
                )
            extra_data["api_key_comfy_org"] = api_key

        auth_token_env = auth.get("comfy_org_auth_token_env")
        if auth_token_env:
            auth_token = os.environ.get(auth_token_env)
            if not auth_token:
                raise gr.Error(
                    f"{self.label} requires `{auth_token_env}` to be set for Comfy Org auth."
                )
            extra_data["auth_token_comfy_org"] = auth_token

        return extra_data or None

    def _copy_to_input(self, path, prefix, extension=None):
        extension = extension or os.path.splitext(path)[1].lower()
        filename = f"{prefix}_{int(time.time() * 1000)}{extension}"
        destination = os.path.join(self.comfy.input_path, filename)
        shutil.copy(path, destination)
        return filename

    def _apply_patch(self, workflow, patch, value):
        node_id = str(patch["node"])
        input_name = patch["input"]
        if node_id not in workflow:
            raise gr.Error(f"Workflow is missing node {node_id} for image backend {self.config['id']}.")
        workflow[node_id].setdefault("inputs", {})[input_name] = value

    def _apply_patch_group(self, workflow, group_name, value):
        patches = self.config.get("patches", {}).get(group_name, [])
        for patch in patches:
            self._apply_patch(workflow, patch, value)

    def _apply_slot_patch(self, workflow, slot, value):
        patches = slot.get("patches") if isinstance(slot, dict) else None
        if patches:
            for patch in patches:
                self._apply_patch(workflow, patch, value)
            return
        self._apply_patch(workflow, slot, value)

    def _next_node_id(self, workflow):
        numeric_ids = [int(node_id) for node_id in workflow.keys() if str(node_id).isdigit()]
        return str(max(numeric_ids, default=0) + 1)

    def _insert_load_image(self, workflow, image_name):
        loader_node_id = self._next_node_id(workflow)
        workflow[loader_node_id] = {
            "inputs": {
                "image": image_name,
            },
            "class_type": "LoadImage",
            "_meta": {
                "title": "Image Generation Reference Loader",
            },
        }
        return loader_node_id

    def _resolve_reference_files(self, reference_files, reference_mode, reference_index):
        reference_files = [path for path in (reference_files or []) if path]
        if not reference_files or reference_mode == "none":
            return []

        if reference_mode == "specific":
            selected_index = max(1, int(reference_index or 1)) - 1
            selected_index = min(selected_index, len(reference_files) - 1)
            return [reference_files[selected_index]]

        if reference_mode == "montage":
            montage_path = os.path.join(
                self.comfy.input_path,
                f"image_reference_montage_{int(time.time() * 1000)}.png",
            )
            build_reference_montage(reference_files, montage_path)
            return [montage_path]

        if reference_mode == "all":
            return reference_files

        return [reference_files[0]]

    def _apply_reference_images(self, workflow, reference_names, reference_mode):
        reference_config = self.config.get("reference_images", {})
        min_reference_images = int(reference_config.get("min_images", 0) or 0)
        if min_reference_images and len(reference_names) < min_reference_images:
            if min_reference_images == 1:
                raise gr.Error(f"{self.label} requires at least one reference image.")
            raise gr.Error(
                f"{self.label} requires at least {min_reference_images} reference images."
            )

        if not reference_names:
            return

        mode = reference_config.get("mode", "single_load_image")

        if reference_mode == "all" and mode not in {"load_image_nodes", "load_image_inputs"}:
            raise gr.Error(
                f"{self.label} does not expose separate multi-reference image inputs. "
                "Use first, specific, or montage reference handling for this backend."
            )

        if mode == "disabled":
            raise gr.Error(f"{self.label} is configured without reference image support.")

        if mode == "single_load_image_input":
            self._apply_patch(
                workflow,
                {
                    "node": reference_config["set_node"],
                    "input": reference_config.get("input", "image"),
                },
                reference_names[0],
            )
            return

        if mode == "single_load_image":
            loader_node_id = self._insert_load_image(workflow, reference_names[0])
            self._apply_patch(
                workflow,
                {
                    "node": reference_config["set_node"],
                    "input": reference_config.get("input", "image"),
                },
                [loader_node_id, 0],
            )
            return

        slots = reference_config.get("slots", [])
        if not slots:
            raise gr.Error(f"{self.label} has no reference image slots configured.")

        for index, image_name in enumerate(reference_names):
            if index >= len(slots):
                break
            slot = slots[index]
            if mode == "load_image_inputs":
                value = image_name
            else:
                loader_node_id = self._insert_load_image(workflow, image_name)
                value = [loader_node_id, 0]
            self._apply_slot_patch(workflow, slot, value)

    def generate(
        self,
        prompt,
        negative_prompt,
        reference_files,
        reference_mode,
        reference_index,
        width,
        height,
        steps,
        cfg,
        denoise,
        seed,
        progress,
    ):
        if not prompt or not prompt.strip():
            raise gr.Error("Enter an image prompt.")

        if not self.config.get("patches", {}).get("prompt"):
            raise gr.Error(
                f"{self.label} needs prompt node patches in runpod/model_manifest.json "
                "before it can be used."
            )

        source = self._workflow_source()
        if not source:
            raise gr.Error(
                f"{self.label} is registered but has no workflow JSON configured. "
                "Add a ComfyUI API workflow path or URL in runpod/model_manifest.json."
            )

        progress(0, desc="Starting ComfyUI...")
        self.comfy.ensure_running()
        os.makedirs(self.comfy.input_path, exist_ok=True)
        reference_files = [uploaded_path(path) for path in (reference_files or [])]
        reference_files = [path for path in reference_files if path]
        reference_files = self._resolve_reference_files(reference_files, reference_mode, reference_index)

        progress(0.1, desc="Preparing image generation workflow...")
        try:
            workflow = load_workflow(source)
        except FileNotFoundError as error:
            workflow_config = self.config.get("workflow", {})
            ui_source = (
                workflow_config.get("source_repo_path")
                or workflow_config.get("ui_source_path")
                or workflow_config.get("ui_source_url")
            )
            message = (
                f"{self.label} needs an API workflow JSON at {source}. "
                "Export a ComfyUI image workflow as API JSON and save it to the configured path."
            )
            if ui_source:
                message += f" Source workflow: {ui_source}"
            raise gr.Error(message) from error
        except ValueError as error:
            raise gr.Error(
                f"{self.label} is pointed at a ComfyUI editor workflow. Export it as API JSON "
                "from ComfyUI and update runpod/model_manifest.json."
            ) from error

        reference_names = []
        for index, reference_path in enumerate(reference_files):
            reference_names.append(self._copy_to_input(reference_path, f"image_ref_{index}"))

        width = max(256, round(width / 16) * 16)
        height = max(256, round(height / 16) * 16)
        self._apply_patch_group(workflow, "prompt", prompt)
        self._apply_patch_group(workflow, "negative_prompt", negative_prompt or "")
        self._apply_patch_group(workflow, "width", width)
        self._apply_patch_group(workflow, "height", height)
        self._apply_patch_group(workflow, "steps", int(steps))
        self._apply_patch_group(workflow, "cfg", float(cfg))
        self._apply_patch_group(workflow, "denoise", float(denoise))
        self._apply_patch_group(workflow, "seed", int(seed))
        self._apply_reference_images(workflow, reference_names, reference_mode)
        for patch in self.config.get("static_patches", []):
            self._apply_patch(workflow, patch, patch.get("value"))

        progress(0.2, desc="Queuing image generation...")
        started_at = time.time()
        log_offset = self.comfy.log_offset()
        prompt_id = self.comfy.queue_prompt(
            workflow,
            extra_data=self._extra_data(),
        )["prompt_id"]
        self.comfy.wait_for_prompt(prompt_id, progress, log_offset=log_offset)

        image = self.comfy.latest_image(since=started_at)
        if image is None:
            prompt_error = self.comfy.prompt_error(prompt_id)
            if prompt_error:
                raise gr.Error(f"{self.label} failed: {prompt_error}")
            raise gr.Error("ComfyUI finished but no image output was found.")

        progress(1.0, desc="Done")
        return image
