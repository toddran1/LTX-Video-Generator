import json
import os


DEFAULT_MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "model_manifest.json",
)


def load_manifest(path=None):
    manifest_path = path or os.environ.get("MODEL_MANIFEST", DEFAULT_MANIFEST_PATH)
    with open(manifest_path, "r", encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


def get_backend(manifest, backend_id):
    for backend in manifest.get("backends", []):
        if backend.get("id") == backend_id:
            return backend
    raise KeyError(f"Backend '{backend_id}' is not defined in the model manifest.")


def enabled_v2v_backends(manifest):
    return [
        backend
        for backend in manifest.get("backends", [])
        if backend.get("type") == "video_to_video" and backend.get("enabled", False)
    ]

