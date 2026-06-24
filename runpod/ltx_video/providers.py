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
    def __init__(self, comfy, workflow_url, start_end_workflow=None):
        self.comfy = comfy
        self.workflow_url = workflow_url
        self.start_end_workflow = start_end_workflow

    def _resolve_path(self, path):
        if not path:
            return None
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if os.path.isabs(path):
            return path
        return os.path.join(PROJECT_ROOT, path)

    def _start_end_workflow_source(self):
        candidates = [
            os.environ.get("START_END_I2V_WORKFLOW_PATH"),
            self.start_end_workflow,
            "runpod/workflows/api/wan_first_last_frame_to_video_api.json",
            "/workspace/workflows/wan_first_last_frame_to_video_api.json",
        ]
        for candidate in candidates:
            source = self._resolve_path(candidate)
            if not source:
                continue
            if source.startswith("http://") or source.startswith("https://") or os.path.exists(source):
                return source
        return None

    def _copy_image_to_input(self, image_filepath, prefix):
        source_path = uploaded_path(image_filepath)
        if source_path is None:
            return None
        extension = os.path.splitext(source_path)[1] or ".png"
        filename = f"{prefix}_{int(time.time() * 1000)}{extension}"
        shutil.copy(source_path, os.path.join(self.comfy.input_path, filename))
        return filename

    def _set_input(self, workflow, node_id, input_name, value):
        node = workflow.get(str(node_id))
        if not node:
            raise gr.Error(f"Start/end image workflow is missing configured node {node_id}.")
        node.setdefault("inputs", {})[input_name] = value
        return True

    def _set_input_from_env(self, workflow, env_name, input_name, value):
        node_id = os.environ.get(env_name)
        if not node_id:
            return False
        return self._set_input(workflow, node_id, input_name, value)

    def _set_first_existing_input_from_env(self, workflow, env_name, input_names, value):
        node_id = os.environ.get(env_name)
        if not node_id:
            return False
        node = workflow.get(str(node_id))
        if not node:
            raise gr.Error(f"Start/end image workflow is missing configured node {node_id}.")
        inputs = node.setdefault("inputs", {})
        for input_name in input_names:
            if input_name in inputs:
                inputs[input_name] = value
                return True
        inputs[input_names[0]] = value
        return True

    def _node_text(self, node):
        meta = node.get("_meta", {}) if isinstance(node.get("_meta"), dict) else {}
        values = [
            node.get("class_type", ""),
            meta.get("title", ""),
            str(node.get("inputs", {}).get("image", "")),
        ]
        return " ".join(str(value).lower() for value in values)

    def _patch_load_image_by_hint(self, workflow, filename, hints):
        hint_terms = tuple(hints)
        for node in workflow.values():
            if node.get("class_type") != "LoadImage":
                continue
            if any(term in self._node_text(node) for term in hint_terms):
                node.setdefault("inputs", {})["image"] = filename
                return True
        return False

    def _patch_inputs_by_hint(self, workflow, input_name, value, hints):
        patched = False
        hint_terms = tuple(hints)
        for node in workflow.values():
            inputs = node.get("inputs", {})
            if input_name not in inputs:
                continue
            if any(term in self._node_text(node) for term in hint_terms):
                inputs[input_name] = value
                patched = True
        return patched

    def _patch_first_matching_input(self, workflow, input_name, value):
        for node in workflow.values():
            inputs = node.get("inputs", {})
            if input_name in inputs:
                inputs[input_name] = value
                return True
        return False

    def _frame_count(self, duration, fps=24):
        frames = max(9, int(round(float(duration) * fps)))
        remainder = (frames - 1) % 4
        if remainder:
            frames += 4 - remainder
        return frames

    def _generate_start_end_video(
        self,
        start_image_filepath,
        end_image_filepath,
        prompt,
        width,
        height,
        duration,
        seed,
        progress,
    ):
        workflow_source = self._start_end_workflow_source()
        if not workflow_source:
            raise gr.Error(
                "Start/End Image-to-Video needs an exported ComfyUI API workflow at "
                "`runpod/workflows/api/wan_first_last_frame_to_video_api.json` or "
                "`/workspace/workflows/wan_first_last_frame_to_video_api.json`."
            )

        if start_image_filepath is None:
            raise gr.Error("Upload a starting image.")
        if end_image_filepath is None:
            raise gr.Error("Upload an ending image.")

        workflow = load_workflow(workflow_source)
        start_name = self._copy_image_to_input(start_image_filepath, "start_end_i2v_start")
        end_name = self._copy_image_to_input(end_image_filepath, "start_end_i2v_end")
        video_width = max(256, round(width / 16) * 16)
        video_height = max(256, round(height / 16) * 16)
        fps = int(os.environ.get("START_END_I2V_FPS", "24"))
        frame_count = self._frame_count(duration, fps=fps)

        start_patched = self._set_input_from_env(
            workflow, "START_END_I2V_START_IMAGE_NODE", "image", start_name
        ) or self._patch_load_image_by_hint(
            workflow, start_name, ("start", "first", "begin", "initial")
        )
        end_patched = self._set_input_from_env(
            workflow, "START_END_I2V_END_IMAGE_NODE", "image", end_name
        ) or self._patch_load_image_by_hint(
            workflow, end_name, ("end", "last", "final")
        )
        if not start_patched or not end_patched:
            raise gr.Error(
                "The start/end workflow must contain two LoadImage nodes titled or named for start/first "
                "and end/last, or set START_END_I2V_START_IMAGE_NODE and START_END_I2V_END_IMAGE_NODE."
            )

        self._set_input_from_env(workflow, "START_END_I2V_PROMPT_NODE", "text", prompt) or self._patch_inputs_by_hint(
            workflow, "text", prompt, ("positive", "prompt")
        )
        self._set_input_from_env(workflow, "START_END_I2V_WIDTH_NODE", "width", video_width) or self._patch_first_matching_input(
            workflow, "width", video_width
        )
        self._set_input_from_env(workflow, "START_END_I2V_HEIGHT_NODE", "height", video_height) or self._patch_first_matching_input(
            workflow, "height", video_height
        )
        self._set_first_existing_input_from_env(
            workflow, "START_END_I2V_LENGTH_NODE", ("length", "num_frames"), frame_count
        ) or self._patch_first_matching_input(
            workflow, "length", frame_count
        ) or self._patch_first_matching_input(
            workflow, "num_frames", frame_count
        )
        self._set_first_existing_input_from_env(
            workflow, "START_END_I2V_SEED_NODE", ("noise_seed", "seed"), int(seed)
        ) or self._patch_first_matching_input(
            workflow, "noise_seed", int(seed)
        ) or self._patch_first_matching_input(
            workflow, "seed", int(seed)
        )
        self._set_input_from_env(workflow, "START_END_I2V_FPS_NODE", "frame_rate", fps) or self._patch_first_matching_input(
            workflow, "frame_rate", fps
        )
        prefix = f"start_end_i2v_{int(time.time() * 1000)}"
        self._set_input_from_env(
            workflow, "START_END_I2V_OUTPUT_NODE", "filename_prefix", prefix
        ) or self._patch_first_matching_input(workflow, "filename_prefix", prefix)

        progress(0.2, desc="Queuing start/end image-to-video generation...")
        started_at = time.time()
        log_offset = self.comfy.log_offset()
        prompt_id = self.comfy.queue_prompt(workflow)["prompt_id"]
        self.comfy.wait_for_prompt(prompt_id, progress, log_offset=log_offset)

        video = self.comfy.latest_video(since=started_at)
        if video is None:
            raise gr.Error("ComfyUI finished but no MP4 output was found.")

        progress(1.0, desc="Done")
        return video

    def generate(self, mode, image_filepath, end_image_filepath, prompt, width, height, duration, seed, progress):
        if not prompt or not prompt.strip():
            raise gr.Error("Enter a prompt.")

        progress(0, desc="Starting ComfyUI...")
        self.comfy.ensure_running()
        os.makedirs(self.comfy.input_path, exist_ok=True)

        if mode == "Start/End Image-to-Video":
            return self._generate_start_end_video(
                start_image_filepath=image_filepath,
                end_image_filepath=end_image_filepath,
                prompt=prompt,
                width=width,
                height=height,
                duration=duration,
                seed=seed,
                progress=progress,
            )

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
        workflow["184"]["inputs"]["vae_name"] = "vae/ltx-2.3-22b-dev_video_vae.safetensors"
        workflow["196"]["inputs"]["vae_name"] = "vae/ltx-2.3-22b-dev_audio_vae.safetensors"
        workflow["346"]["inputs"]["clip_name1"] = "gemma-3-12b-it-q4_0_s.gguf"
        workflow["346"]["inputs"]["clip_name2"] = "text_encoders/ltx-2.3-22b-dev_embeddings_connectors.safetensors"
        workflow["345"]["inputs"]["unet_name"] = "ltx-2.3-22b-dev-Q4_K_M.gguf"

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


class InsightFaceSwapProvider:
    def __init__(self, output_path, model_root=None, swapper_path=None):
        self.output_path = output_path
        self.model_root = model_root or os.environ.get(
            "INSIGHTFACE_MODEL_ROOT",
            "/workspace/ComfyUI/models/insightface",
        )
        self.swapper_path = swapper_path or os.environ.get("INSWAPPER_MODEL_PATH")
        self._face_analyzer = None
        self._swapper = None

    @property
    def label(self):
        return "InsightFace Face Swap"

    def _providers(self):
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]

    def _load_models(self):
        if self._face_analyzer is not None and self._swapper is not None:
            return self._face_analyzer, self._swapper

        swapper_path = self.swapper_path
        if not swapper_path:
            candidates = [
                os.path.join(self.model_root, "inswapper_128.onnx"),
                os.path.join(self.model_root, "models", "inswapper_128.onnx"),
            ]
            swapper_path = next((path for path in candidates if os.path.exists(path)), candidates[0])

        if not os.path.exists(swapper_path):
            raise gr.Error(
                f"Missing face swap model at {swapper_path}. "
                "Run `bash runpod/setup_insightface_swap.sh` on the pod."
            )

        try:
            from insightface.app import FaceAnalysis
            from insightface.model_zoo import get_model
        except ImportError as error:
            raise gr.Error(
                "InsightFace face swap dependencies are not installed. "
                "Run `bash runpod/setup_insightface_swap.sh` on the pod."
            ) from error

        providers = self._providers()
        try:
            face_analyzer = FaceAnalysis(name="buffalo_l", root=self.model_root, providers=providers)
            face_analyzer.prepare(ctx_id=0, det_size=(640, 640))
            swapper = get_model(swapper_path, providers=providers)
        except Exception:
            providers = ["CPUExecutionProvider"]
            face_analyzer = FaceAnalysis(name="buffalo_l", root=self.model_root, providers=providers)
            face_analyzer.prepare(ctx_id=-1, det_size=(640, 640))
            swapper = get_model(swapper_path, providers=providers)

        self._face_analyzer = face_analyzer
        self._swapper = swapper
        return self._face_analyzer, self._swapper

    def _resolve_reference_files(self, reference_files, reference_mode, reference_index):
        reference_files = [uploaded_path(path) for path in (reference_files or [])]
        reference_files = [path for path in reference_files if path]
        if not reference_files or reference_mode == "none":
            return []

        if reference_mode == "specific":
            selected_index = max(1, int(reference_index or 1)) - 1
            selected_index = min(selected_index, len(reference_files) - 1)
            return [reference_files[selected_index]]

        if reference_mode == "all":
            return reference_files

        return [reference_files[0]]

    def _largest_face(self, faces):
        def area(face):
            x1, y1, x2, y2 = face.bbox
            return max(0, x2 - x1) * max(0, y2 - y1)

        return max(faces, key=area)

    def _expanded_bbox(self, bbox, image_shape, scale):
        x1, y1, x2, y2 = [float(value) for value in bbox]
        width = x2 - x1
        height = y2 - y1
        center_x = x1 + width / 2
        center_y = y1 + height / 2
        side = max(width, height) * scale
        half = side / 2
        image_height, image_width = image_shape[:2]
        left = max(0, int(round(center_x - half)))
        top = max(0, int(round(center_y - half)))
        right = min(image_width, int(round(center_x + half)))
        bottom = min(image_height, int(round(center_y + half)))
        return left, top, right, bottom

    def _reinforce_source_face(self, result, source_image, source_face, target_face, alpha):
        if alpha <= 0:
            return result

        import cv2
        import numpy as np

        source_box = self._expanded_bbox(source_face.bbox, source_image.shape, 1.15)
        target_box = self._expanded_bbox(target_face.bbox, result.shape, 1.35)
        sx1, sy1, sx2, sy2 = source_box
        tx1, ty1, tx2, ty2 = target_box
        target_width = tx2 - tx1
        target_height = ty2 - ty1
        if target_width <= 0 or target_height <= 0 or sx2 <= sx1 or sy2 <= sy1:
            return result

        source_crop = source_image[sy1:sy2, sx1:sx2]
        if source_crop.size == 0:
            return result

        source_crop = cv2.resize(source_crop, (target_width, target_height), interpolation=cv2.INTER_LANCZOS4)
        target_region = result[ty1:ty2, tx1:tx2]

        mask = np.zeros((target_height, target_width), dtype=np.float32)
        center = (target_width // 2, target_height // 2)
        axes = (max(1, int(target_width * 0.38)), max(1, int(target_height * 0.46)))
        cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, -1)
        feather = max(9, (min(target_width, target_height) // 10) | 1)
        mask = cv2.GaussianBlur(mask, (feather, feather), 0)
        mask = mask[..., None] * float(alpha)

        blended = source_crop.astype(np.float32) * mask + target_region.astype(np.float32) * (1.0 - mask)
        result = result.copy()
        result[ty1:ty2, tx1:tx2] = np.clip(blended, 0, 255).astype(np.uint8)
        return result

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
        progress(0, desc="Loading face swap models...")
        resolved_references = self._resolve_reference_files(reference_files, reference_mode, reference_index)
        if len(resolved_references) < 2:
            raise gr.Error(
                "InsightFace Face Swap needs two references: source face first, target body/composition second."
            )

        source_path = resolved_references[0]
        target_path = resolved_references[1]

        try:
            import cv2
        except ImportError as error:
            raise gr.Error(
                "OpenCV is not installed for the face swap backend. "
                "Run `bash runpod/setup_insightface_swap.sh` on the pod."
            ) from error

        analyzer, swapper = self._load_models()
        target_image = cv2.imread(target_path)
        source_image = cv2.imread(source_path)
        if target_image is None:
            raise gr.Error("Could not read the target body/composition image.")
        if source_image is None:
            raise gr.Error("Could not read the source face image.")

        progress(0.25, desc="Detecting faces...")
        target_faces = analyzer.get(target_image)
        source_faces = analyzer.get(source_image)
        if not target_faces:
            raise gr.Error("No face was detected in the target body/composition image.")
        if not source_faces:
            raise gr.Error("No face was detected in the source identity image.")

        progress(0.55, desc="Swapping source face onto target...")
        target_face = self._largest_face(target_faces)
        source_face = self._largest_face(source_faces)
        result = swapper.get(target_image, target_face, source_face, paste_back=True)
        reinforce_alpha = float(cfg) if cfg is not None else float(os.environ.get("FACE_SWAP_REINFORCE_ALPHA", "0.18"))
        if reinforce_alpha <= 0:
            reinforce_alpha = 0.0
        reinforce_alpha = min(reinforce_alpha, 0.5)
        result = self._reinforce_source_face(result, source_image, source_face, target_face, reinforce_alpha)

        progress(0.85, desc="Saving image...")
        output_dir = os.path.join(self.output_path, "image_generation")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"insightface_swap_{int(time.time() * 1000)}.png")
        cv2.imwrite(output_file, result)

        progress(1.0, desc="Done")
        return output_file
