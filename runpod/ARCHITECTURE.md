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
/network/models
/network/hf-cache
/network/ComfyUI
/network/outputs
/network/tmp
```

Current compatibility layout:

```text
/workspace/modal-notebook
/workspace/ComfyUI
/workspace/ComfyUI/models -> /network/models when MODEL_ROOT=/network/models
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

The initial video-to-video backend is intentionally workflow-configurable:

```json
{
  "id": "comfy_v2v_template",
  "type": "video_to_video",
  "workflow": {
    "path": "",
    "url": ""
  },
  "patches": {
    "prompt": [],
    "video": [],
    "reference_images": [],
    "width": [],
    "height": [],
    "fps": [],
    "seed": []
  }
}
```

To activate a concrete ComfyUI v2v workflow, export the workflow as API JSON, place it under persistent storage or this repo, then add the node patch mappings. Example shape:

```json
"workflow": {
  "path": "/network/workflows/my-v2v-api.json"
},
"patches": {
  "prompt": [{"node": "12", "input": "text"}],
  "video": [{"node": "34", "input": "video"}],
  "reference_images": [{"node": "56", "input": "images"}],
  "width": [{"node": "78", "input": "width"}],
  "height": [{"node": "78", "input": "height"}],
  "fps": [{"node": "90", "input": "fps"}],
  "seed": [{"node": "91", "input": "seed"}]
}
```

This keeps the app independent of one node graph and lets multiple v2v backends coexist.

## Initial Video-To-Video Integration Strategy

Use a ComfyUI workflow that supports video loading, prompt conditioning, optional reference image conditioning, and video saving. The preferred first class of workflows should preserve motion structure and allow 720p output. Good candidates are workflows based on open ComfyUI nodes for video loading/saving, image/video conditioning, and diffusion video editing.

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

