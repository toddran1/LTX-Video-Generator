#!/usr/bin/env python3
import argparse
import json
import os
import shutil
from pathlib import Path


DEFAULT_MANIFEST = Path(__file__).with_name("model_manifest.json")


def size_gb(path):
    total = 0
    if not os.path.exists(path):
        return 0.0
    if os.path.isfile(path):
        return os.path.getsize(path) / (1024**3)
    for root, _, files in os.walk(path):
        for filename in files:
            full_path = os.path.join(root, filename)
            if not os.path.islink(full_path):
                total += os.path.getsize(full_path)
    return total / (1024**3)


def path_status(path):
    if os.path.exists(path):
        return "present"
    if os.path.exists(f"{path}.aria2"):
        return "partial"
    return "missing"


def main():
    parser = argparse.ArgumentParser(description="Report Runpod model storage requirements.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--model-root", default=os.environ.get("MODEL_ROOT", "/workspace/ComfyUI/models"))
    parser.add_argument("--workspace", default=os.environ.get("WORKSPACE", "/workspace"))
    args = parser.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    required_gb = sum(item.get("estimated_gb", 0) for item in manifest.get("model_sets", []) if item.get("required"))
    optional_gb = sum(item.get("estimated_gb", 0) for item in manifest.get("model_sets", []) if not item.get("required"))
    workspace_usage = shutil.disk_usage(args.workspace)

    print("Storage estimate")
    print(f"  Required model sets: {required_gb:.1f} GB")
    print(f"  Optional/future model sets: {optional_gb:.1f} GB")
    print(f"  Model root: {args.model_root}")
    print(f"  Model root current size: {size_gb(args.model_root):.1f} GB")
    print(f"  Workspace free: {workspace_usage.free / (1024**3):.1f} GB")
    print()

    for model_set in manifest.get("model_sets", []):
        print(f"{model_set['id']} ({model_set.get('estimated_gb', 0)} GB estimate)")
        for model_path in model_set.get("paths", []):
            print(f"  {path_status(model_path):8} {model_path}")
        if not model_set.get("paths"):
            print("  no concrete model paths registered yet")


if __name__ == "__main__":
    main()

