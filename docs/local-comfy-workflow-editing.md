# Local ComfyUI Workflow Editing

Use this when you want to inspect or edit workflow graphs on your Mac without running model inference.

## Local ComfyUI Path

The expected local ComfyUI checkout is:

```bash
/Users/reginaldrandolph/Documents/coding projects/python/comfyUI/ComfyUI-local
```

ComfyUI should be reachable at:

```text
http://127.0.0.1:8188
```

## Setup Or Refresh Custom Nodes

From this repo:

```bash
bash scripts/setup_local_comfy_workflow_editor.sh
```

This installs or refreshes the custom nodes needed to open the current LTX workflows. It does not download model weights.

## Source And API Workflow Files

Editable ComfyUI source workflows go here:

```text
runpod/workflows/source/
```

ComfyUI API exports go here:

```text
runpod/workflows/api/
```

The current v2v backend is configured to prefer:

```text
runpod/workflows/api/ltx23_v2v_retake_api.json
```

If that file is not present, the app falls back to:

```text
/workspace/workflows/ltx23_v2v_retake_api.json
```

## Edit And Export Loop

1. Open ComfyUI locally.
2. Load the editable source workflow from `runpod/workflows/source/`.
3. Inspect and tune the graph.
4. Export the graph as API JSON.
5. Save the API JSON to `runpod/workflows/api/ltx23_v2v_retake_api.json`.
6. Commit both source and API JSON changes when the graph is ready.
7. On Runpod, pull the repo and run the app. The app will use the repo-tracked API JSON automatically.

## Current V2V Controls To Inspect

The current backend is based on the RuneXX LTX 2.3 ReTake workflow. The first output looked too similar to the input video, so inspect these controls first:

- `RETAKE START` and `RETAKE END`: the app now patches these to the full uploaded video by default.
- `BasicScheduler` denoise: exposed in the app as `Transform Strength`.
- `LTXVImgToVideoInplace` strength: also patched by `Transform Strength`.
- `CFGGuider` cfg values: exposed as `Prompt CFG`.
- `LTX2_NAG` `nag_scale`: exposed as `NAG Prompt Influence`.
- Reference image nodes: the current backend has no reference-image patch mapping yet.
- Whole-video behavior: confirm the graph is not still designed around a narrow retake window.

Inspection notes from the current source workflow:

- The editable source has `RETAKE START (seconds)` at node `661`, default `3.3`.
- The editable source has `RETAKE END (seconds)` at node `662`, default `7.9`.
- The app now patches those to `0.0` and the uploaded video duration when `Transform Full Video` is enabled.
- The source workflow's GGUF text encoder node is saved as `sdxl`; the app patches the exported API node to `ltxv` at runtime.
- The preview override node is removed at runtime because it can crash in headless/API ComfyUI sessions.
- The workflow's `ref_image` channel is normally set from the first frame of the source video. The app now overrides that channel with the first uploaded reference image when a reference image is provided.

## Reference Images

The current LTX ReTake workflow has one practical reference-image slot:

```text
Editor workflow:
  294: Set_ref_image
  439: Get_ref_image
  438: LTXVImgToVideoInplace

API workflow:
  438: LTXVImgToVideoInplace image input
```

Without an uploaded reference image, this slot keeps the workflow's original behavior and uses the input video's first frame. With an uploaded reference image, the app inserts a `LoadImage` node into the API workflow at runtime and feeds that image into `438.image`.

For prompts like `Change the person in the video to the character in this image`, upload one clear character image. The current backend uses the first uploaded image only. Later backends can support multiple reference images with a different workflow.

## Important

Opening and editing workflows locally does not require the models. Queueing a generation does require the models and should be done on the A100 pod.
