# Workflow Files

Put small text-only ComfyUI workflow JSON files here.

Do not commit model weights, generated videos, input media, or large binary artifacts.

Use these subfolders:

```text
source/
api/
```

`source/` stores editable ComfyUI editor workflows. `api/` stores ComfyUI API exports that the app can queue.

For one-off production Runpod usage, you can also store workflow JSON on persistent storage, for example:

```text
/workspace/workflows/my-v2v-api.json
```

Then point `runpod/model_manifest.json` at that path.
