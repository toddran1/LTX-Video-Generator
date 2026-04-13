#!/usr/bin/env python3
import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="Inspect a ComfyUI workflow JSON for patchable node inputs.")
    parser.add_argument("workflow")
    args = parser.parse_args()

    with open(args.workflow, "r", encoding="utf-8") as workflow_file:
        workflow = json.load(workflow_file)

    if isinstance(workflow, dict) and "nodes" in workflow:
        print("Detected ComfyUI editor workflow JSON.")
        print("Export this workflow as API JSON before using it with runpod/app.py.")
        for node in workflow.get("nodes", []):
            node_id = node.get("id")
            node_type = node.get("type")
            title = node.get("title") or ""
            inputs = ", ".join(item.get("name", "") for item in node.get("inputs", []))
            widgets = node.get("widgets_values")
            if not isinstance(widgets, list):
                widgets = []
            widget_preview = " | ".join(str(value)[:80] for value in widgets[:4])
            print(f"{node_id}: {node_type} {title} inputs=[{inputs}] widgets=[{widget_preview}]")
        return

    print("Detected ComfyUI API workflow JSON.")
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "unknown")
        inputs = node.get("inputs", {})
        input_names = ", ".join(inputs.keys())
        print(f"{node_id}: {class_type} inputs=[{input_names}]")


if __name__ == "__main__":
    main()

