# LTX 2.3 Video Generator

This fork packages the original Modal notebook workflow into a Runpod-ready image and video generation workspace.

The current target runtime is a Runpod A100 pod running ComfyUI, the LTX 2.3 and Wan custom nodes, and a Gradio UI for text-to-video, image-to-video, video-to-video, and `/image-generation` workflows.

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

Do not use a 10 GB network volume for this project. The current LTX model files alone are about 35 GB, the LTX ReTake v2v backend adds roughly 25 GB more, and the Wan Fun Control v2v backend adds roughly 16 GB more. Use at least 100 GB for short testing and 150 GB or more for normal development with generated outputs.

Setup on a new pod:

```bash
cd /workspace/modal-notebook
NETWORK_ROOT=/workspace bash runpod/bootstrap_storage.sh
export NETWORK_ROOT=/workspace
MODEL_ROOT=/workspace/ComfyUI/models bash runpod/setup_ltx23.sh
MODEL_ROOT=/workspace/ComfyUI/models bash runpod/setup_image_generation.sh
MODEL_ROOT=/workspace/ComfyUI/models bash runpod/setup_wan21_fun_control_v2v.sh
MODEL_ROOT=/workspace/ComfyUI/models bash runpod/setup_v2v_ltx23.sh
nohup bash runpod/run_ui.sh > runpod/ui.log 2>&1 &
echo $! > runpod/ui.pid
```

If the pod has a small `/workspace` quota, use memory-backed model storage for the active session:

```bash
MODEL_ROOT=/dev/shm/ltx23-models bash runpod/setup_ltx23.sh
```

The image flow now includes:

- `Krea 2 Local Multi-Reference`: experimental local multi-reference synthesis/editing
- `Qwen Image Edit Multi-Reference`: local multi-reference synthesis/editing
- `InsightFace Face Swap`: source-face to target-body/composition swap path
- `FLUX.2 Klein Image Generation`: optional local FLUX.2 text-to-image

The image page returns both an in-app preview and a downloadable file for saving the generated image locally.

The main video tab also includes a `Start/End Image-to-Video` mode. That mode expects a ComfyUI API workflow with first-frame and last-frame image inputs at `runpod/workflows/api/wan_first_last_frame_to_video_api.json` or `/workspace/workflows/wan_first_last_frame_to_video_api.json`.

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

If `7860` is not exposed as an HTTP service, tunnel it over direct TCP SSH:

```bash
ssh -N -L 7860:127.0.0.1:7860 root@<direct-tcp-host> -p <direct-tcp-port> -i ~/.ssh/runpod_ltx_video
```

Then open `http://127.0.0.1:7860`. The image workspace is at `http://127.0.0.1:7860/image-generation`.

## Original Notebooks

The upstream repository contains Modal notebooks under [`notebooks/`](notebooks/). This fork keeps them for reference, but the supported deployment path for this project is the Runpod setup in [`runpod/`](runpod/).

## Architecture

The app now uses a provider layer so the working LTX text/image flow can coexist with future video-to-video models. See [`runpod/ARCHITECTURE.md`](runpod/ARCHITECTURE.md) for the v2v backend structure, model manifest, storage layout, validation, and audio passthrough design.

## 🤝 Contributing
Found a bug or have a suggestion for a new notebook? Feel free to open an issue or submit a pull request!
