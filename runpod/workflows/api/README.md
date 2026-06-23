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

## Image Generation Workflows

The `/image-generation` page reads image backends from `runpod/model_manifest.json`.

The repo includes two immediately useful image workflow targets:

```text
runpod/workflows/api/sdxl_turbo_image_api.json
runpod/workflows/api/flux2_bfl_api_image_api.json
```

`sdxl_turbo_image_api.json` is a local smoke-test workflow. `flux2_bfl_api_image_api.json` uses ComfyUI's built-in `Flux2ImageNode`, which supports up to 8 reference images through the BFL/Comfy API node and requires Comfy Org/BFL API credentials at runtime.

The default image backend entry expects a FLUX.2 Klein API workflow at:

```text
runpod/workflows/api/flux2_klein_image_api.json
```

or, on the pod:

```text
/workspace/workflows/flux2_klein_image_api.json
```

Export a FLUX.2 Klein image generation or image-editing workflow from ComfyUI as API JSON and save it there. Then update the backend's `patches` section in `runpod/model_manifest.json` with the workflow's actual node IDs for prompt, width, height, steps, CFG, denoise, and seed.

For the local Hugging Face FLUX.2 Klein path, run:

```bash
HF_TOKEN=hf_xxx bash runpod/setup_flux2_klein_image.sh
```

That token must belong to a Hugging Face account that has accepted access/terms for:

```text
https://huggingface.co/black-forest-labs/FLUX.2-klein-9B
https://huggingface.co/ponpoke/flux2-klein-9b-uncensored-text-encoder
```

For the `ponpoke/flux2-klein-9b-uncensored-text-encoder` text encoder, patch the relevant text encoder loader node in `static_patches` to the exact filename installed under ComfyUI's text encoder model directory. The setup script defaults to `flux2-klein-9b-uncensored-q4_k_m.gguf`.

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
