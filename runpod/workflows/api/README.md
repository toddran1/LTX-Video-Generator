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
