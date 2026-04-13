# Workflow JSON Files

Put ComfyUI API workflow JSON files here only if they are small text files.

Do not commit model weights, generated videos, input media, or large binary artifacts.

For production Runpod usage, prefer storing workflow JSON on persistent storage, for example:

```text
/network/workflows/my-v2v-api.json
```

Then point `runpod/model_manifest.json` at that path.

