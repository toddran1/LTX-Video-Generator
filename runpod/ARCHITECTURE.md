# Video Generation Architecture

This project keeps the working LTX 2.3 text-to-video and image-to-video path intact while adding a provider layer for future workflows.

## Goals

- Preserve the current LTX 2.3 behavior.
- Add video-to-video without tying the app to one hard-coded workflow forever.
- Keep model files, outputs, caches, and temporary data out of git.
- Make Runpod network storage explicit and reproducible.
- Allow later providers for upscaling, interpolation, identity preservation, multi-pass refinement, and alternate model backends.

## Runtime Layout

Recommended persistent layout when using Runpod network storage:

```text
/workspace/ComfyUI/models
/workspace/hf-cache
/workspace/ComfyUI
/workspace/outputs
/workspace/tmp
```

Current compatibility layout:

```text
/workspace/modal-notebook
/workspace/ComfyUI
/opt/venvs/ltx23
```

The Python virtualenv stays on local container disk at `/opt/venvs/ltx23` because thousands of small package files are slow on network storage. Model weights and generated outputs should live on persistent storage.

## Provider Layer

The Gradio app delegates generation to providers:

```text
runpod/app.py
  -> ltx_video.providers.LtxTextImageProvider
  -> ltx_video.providers.ComfyVideoToVideoProvider
  -> ltx_video.comfy.ComfyClient
```

`LtxTextImageProvider` owns the existing LTX text/image workflow. Its node IDs and sampler settings are unchanged from the working implementation.

`ComfyVideoToVideoProvider` is manifest-driven. It accepts:

- input video
- prompt
- optional reference images
- target width and height
- seed
- audio passthrough flag

It validates video metadata with `ffprobe`, copies inputs into ComfyUI's input directory, patches a configured ComfyUI API workflow JSON, queues the prompt, waits for completion, and optionally remuxes the original audio with `ffmpeg`.

## Model Manifest

`runpod/model_manifest.json` declares:

- storage layout
- model set estimates
- concrete model paths for the current LTX stack
- enabled backends
- workflow patch maps for configurable ComfyUI providers

The app currently has two video-to-video backends:

- `wan21_fun_control_v2v`: stronger prompt/reference driven transformation using Wan 2.1 Fun Control.
- `ltx23_v2v_retake`: LTX-native retake/edit workflow for lighter changes.

`ltx23_v2v_retake` is based on the RuneXX community LTX 2.3 ReTake workflow source on Hugging Face:

```text
https://huggingface.co/RuneXX/LTX-2.3-Workflows
```

The source file is a ComfyUI editor workflow. The app queues ComfyUI API JSON, so the source workflow must be exported once as API JSON.

Repo-tracked source workflows live here:

```text
runpod/workflows/source/
```

Repo-tracked API workflows live here:

```text
runpod/workflows/api/
```

Each backend can prefer a repo-tracked API workflow and fall back to persistent pod storage. The LTX ReTake backend prefers:

```text
runpod/workflows/api/ltx23_v2v_retake_api.json
```

If the repo-tracked API workflow is missing, the backend falls back to:

```text
/workspace/workflows/ltx23_v2v_retake_api.json
```

The backend remains workflow-configurable:

```json
{
  "id": "ltx23_v2v_retake",
  "type": "video_to_video",
  "workflow": {
    "repo_path": "runpod/workflows/api/ltx23_v2v_retake_api.json",
    "path": "/workspace/workflows/ltx23_v2v_retake_api.json"
  },
  "patches": {
    "prompt": [],
    "video": [],
    "reference_images": [],
    "width": [],
    "height": [],
    "fps": [],
    "seed": [],
    "retake_start": [],
    "retake_end": [],
    "transform_strength": [],
    "prompt_cfg": [],
    "nag_scale": []
  }
}
```

To activate a concrete ComfyUI v2v workflow, export the workflow as API JSON, place it under persistent storage or this repo, then add the node patch mappings. Example shape:

```json
"workflow": {
  "path": "/workspace/workflows/my-v2v-api.json"
},
"patches": {
  "prompt": [{"node": "12", "input": "text"}],
  "video": [{"node": "34", "input": "video"}],
  "reference_images": [{"node": "56", "input": "images"}],
  "width": [{"node": "78", "input": "width"}],
  "height": [{"node": "78", "input": "height"}],
  "fps": [{"node": "90", "input": "fps"}],
  "seed": [{"node": "91", "input": "seed"}],
  "retake_start": [{"node": "92", "input": "value"}],
  "retake_end": [{"node": "93", "input": "value"}],
  "transform_strength": [{"node": "94", "input": "denoise"}],
  "prompt_cfg": [{"node": "95", "input": "cfg"}],
  "nag_scale": [{"node": "96", "input": "nag_scale"}]
}
```

Use `runpod/inspect_workflow.py` to inspect either editor workflow JSON or API workflow JSON while building these mappings. For local visual editing, use `docs/local-comfy-workflow-editing.md`.

This keeps the app independent of one node graph and lets multiple v2v backends coexist.

The LTX ReTake backend supports one reference image by overriding the workflow's `ref_image` channel at runtime:

```json
"reference_image": {
  "set_node": "438",
  "input": "image"
}
```

When a user uploads a reference image, the provider inserts a ComfyUI `LoadImage` API node and routes it into `LTXVImgToVideoInplace.image`. Without an uploaded reference image, the provider bypasses the first-frame guide and reduces the last-frame guide to avoid the static first-frame behavior seen in testing.

The Wan Fun Control backend uses a different reference strategy:

```json
"reference_image": {
  "mode": "load_image_input",
  "set_node": "52",
  "input": "image",
  "fallback": "first_frame"
}
```

`mode: load_image_input` means the provider patches the existing `LoadImage.image` widget directly instead of inserting another image loader node. `fallback: first_frame` means a prompt-only video-to-video request still has a valid Wan start/reference image by extracting frame 0 from the input video with `ffmpeg`.

## Initial Video-To-Video Integration Strategy

Use a ComfyUI workflow that supports video loading, prompt conditioning, optional reference image conditioning, and video saving.

The current strategy is:

- Use Wan 2.1 Fun Control for stronger prompt/reference driven transformation and style conversion tests.
- Keep LTX 2.3 ReTake for lighter retake/editing workflows where preserving the source structure matters more than changing the whole visual style.

The first Wan API workflow is derived from the official ComfyUI Wan 2.1 Fun Control custom-node example and replaces the example WebP output with `VHS_VideoCombine` MP4 output so the existing app can detect and optionally remux audio.

The initial Wan backend is capped to 81 loaded frames by static workflow patch. That is intentional for early A100 testing. Full 60 second 720p support should be implemented as chunked generation plus stitch/remux, rather than trying to push every frame through one ComfyUI prompt.

The app does not add prompt filtering or app-level topic restrictions. Model behavior depends on the chosen backend and weights.

## Audio

Most visual generation workflows do not synthesize final audio. The app therefore supports an optional default path:

1. Generate transformed visual video.
2. Detect whether the source video has audio.
3. Remux source audio into the generated MP4 with `ffmpeg -shortest`.

This preserves the source audio when possible without forcing every model backend to support audio natively.

## Validation And Errors

Video-to-video validates:

- file exists
- extension is `mp4`, `mov`, `mkv`, or `webm`
- video stream exists
- duration is 60 seconds or less
- resolution and frame rate can be read

Errors are surfaced as Gradio messages with enough detail to fix missing models, unsupported media, or unconfigured workflows.

## Future Backends

Add a backend by:

1. Installing required custom nodes and models in setup scripts.
2. Adding model estimates and paths to `runpod/model_manifest.json`.
3. Exporting the ComfyUI workflow as API JSON.
4. Adding a backend entry with workflow path/URL and patch mappings.
5. Testing with `tail -f runpod/ui.log` and `nvidia-smi`.

Future provider types can be added for:

- upscaling
- interpolation
- face/identity consistency
- multi-stage pipelines
- non-ComfyUI APIs
