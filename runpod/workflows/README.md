# Workflow Files

Put small text-only ComfyUI workflow JSON files here.

Do not commit model weights, generated videos, input media, or large binary artifacts.

Use these subfolders:

```text
source/
api/
```

`source/` stores editable ComfyUI editor workflows. `api/` stores ComfyUI API exports that the app can queue.

Current tracked workflows:

```text
source/LTX-2.3_-_V2V_ReTake_recreate_any_section_of_any_video.json
api/ltx23_v2v_retake_api.json

source/wan2_1_fun_control_v2v_custom_nodes.json
api/wan2_1_fun_control_v2v_api.json
```

Use the Wan workflow first for stronger prompt/reference style transformation tests. Use the LTX ReTake workflow for lighter edit/retake tests.

For one-off production Runpod usage, you can also store workflow JSON on persistent storage, for example:

```text
/workspace/workflows/my-v2v-api.json
```

Then point `runpod/model_manifest.json` at that path.
