# LTX 2.3 Video Generator

This fork packages the original Modal notebook workflow into a Runpod-ready LTX 2.3 video generator.

The current target runtime is a Runpod A100 pod running ComfyUI, the LTX 2.3 custom nodes, and a Gradio UI for text-to-video and image-to-video generation.

## Runpod Quick Start

The detailed setup and operations guide is in [`runpod/README.md`](runpod/README.md).

Minimum pod:

- GPU: NVIDIA A100 40 GB VRAM
- Container disk: 40 GB or more
- Persistent volume: 60 GB or more
- HTTP ports: expose `7860` for the Gradio UI
- SSH: enable direct TCP SSH if you want local port forwarding

Recommended pod:

- GPU: NVIDIA A100 80 GB VRAM
- Container disk: 60-80 GB or more
- Persistent volume: 100-150 GB or more if you want model files and outputs to survive pod restarts
- HTTP ports: expose `7860` for the Gradio UI, and optionally `8888` for Jupyter
- SSH: enable direct TCP SSH if you want local port forwarding

Setup on the pod:

```bash
cd /workspace/modal-notebook
MODEL_ROOT=/workspace/ComfyUI/models bash runpod/setup_ltx23.sh
nohup bash runpod/run_ui.sh > runpod/ui.log 2>&1 &
echo $! > runpod/ui.pid
```

If the pod has a small `/workspace` quota, use memory-backed model storage for the active session:

```bash
MODEL_ROOT=/dev/shm/ltx23-models bash runpod/setup_ltx23.sh
```

## Useful Commands

Watch logs:

```bash
cd /workspace/modal-notebook
tail -f runpod/ui.log
```

Check services:

```bash
ps -ef | grep -E 'runpod/app.py|ComfyUI/main.py' | grep -v grep
ss -ltnp | grep -E ':7860|:8188'
```

Restart the UI:

```bash
cd /workspace/modal-notebook
kill $(cat runpod/ui.pid) 2>/dev/null || true
nohup bash runpod/run_ui.sh > runpod/ui.log 2>&1 &
echo $! > runpod/ui.pid
```

## Original Notebooks

The upstream repository contains Modal notebooks under [`notebooks/`](notebooks/). This fork keeps them for reference, but the supported deployment path for this project is the Runpod setup in [`runpod/`](runpod/).

## 🤝 Contributing
Found a bug or have a suggestion for a new notebook? Feel free to open an issue or submit a pull request!
