# API Workflows

Put ComfyUI API workflow JSON files here.

These are the files the Runpod app can queue through the ComfyUI HTTP API. In ComfyUI, use the API workflow export option after editing the source graph.

Current backend target:

```text
runpod/workflows/api/ltx23_v2v_retake_api.json
```

The app prefers this repo-tracked path when it exists. If it is missing, it falls back to the older pod path:

```text
/workspace/workflows/ltx23_v2v_retake_api.json
```

## Start/End Image-To-Video Workflow

The `LTX Text / Image` tab includes a `Start/End Image-to-Video` mode. It expects a first-frame/last-frame ComfyUI API workflow at:

```text
runpod/workflows/api/wan_first_last_frame_to_video_api.json
```

or, on the pod:

```text
/workspace/workflows/wan_first_last_frame_to_video_api.json
```

Use a Wan first/last-frame graph with two `LoadImage` nodes. Name or title those nodes with `start`/`first` and `end`/`last`, or set the explicit `START_END_I2V_*_NODE` env vars described in `runpod/README.md`.

## Image Generation Workflows

The `/image-generation` page reads image backends from `runpod/model_manifest.json`.

The repo includes two immediately useful image workflow targets:

```text
runpod/workflows/api/sdxl_turbo_image_api.json
runpod/workflows/api/flux2_bfl_api_image_api.json
```

`sdxl_turbo_image_api.json` is a local smoke-test workflow. `flux2_bfl_api_image_api.json` uses ComfyUI's built-in `Flux2ImageNode`, which supports up to 8 reference images through the BFL/Comfy API node and requires Comfy Org/BFL API credentials at runtime. `flux2_klein_image_api.json` is the local FLUX.2 Klein text-to-image workflow tested against ComfyUI `0.26.0` with `ComfyUI-GGUF`.

The local FLUX.2 Klein backend expects the API workflow at:

```text
runpod/workflows/api/flux2_klein_image_api.json
```

or, on the pod:

```text
/workspace/workflows/flux2_klein_image_api.json
```

The checked-in workflow patches prompt, width, height, steps, FLUX guidance, and seed through `runpod/model_manifest.json`. It does not expose local reference-image conditioning; use the BFL API backend for true multi-reference image editing, or replace this workflow with a local image-editing graph and update `reference_images.slots`.

For the local Hugging Face FLUX.2 Klein path, run:

```bash
HF_TOKEN=hf_xxx bash runpod/setup_flux2_klein_image.sh
```

That token must belong to a Hugging Face account that has accepted access/terms for:

```text
https://huggingface.co/black-forest-labs/FLUX.2-klein-9B
https://huggingface.co/ponpoke/flux2-klein-9b-uncensored-text-encoder
```

The setup script defaults to:

```text
/workspace/ComfyUI/models/diffusion_models/flux-2-klein-9b.safetensors
/workspace/ComfyUI/models/clip/flux2-klein-9b-uncensored-q4_k_m.gguf
/workspace/ComfyUI/models/vae/flux2-vae.safetensors
/workspace/ComfyUI/custom_nodes/ComfyUI-GGUF
```

Reference image handling is controlled by the backend's `reference_images` entry. Use a single image input for normal image-to-image/editing workflows:

```json
{
  "mode": "single_load_image",
  "set_node": "12",
  "input": "image"
}
```

For true multi-reference workflows, configure one slot per image-conditioning input:

```json
{
  "mode": "load_image_nodes",
  "slots": [
    { "node": "21", "input": "image_1" },
    { "node": "22", "input": "image_2" },
    { "node": "23", "input": "image_3" }
  ]
}
```

`Use All References Separately` only works when those slots are configured. For single-reference workflows, use first, specific, or montage reference handling.
