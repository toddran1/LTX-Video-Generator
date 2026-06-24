# Runpod LTX 2.3 Setup

This folder turns the original Modal notebook flow into scripts that run directly on a Runpod A100 pod. The current app keeps the working LTX text/image flow and adds a manifest-driven video-to-video backend layer.

## Recommended Runpod Configuration

Use an **NVIDIA A100 80 GB** pod for the best balance of VRAM headroom and cost. A smaller A100 can work for conservative settings, but the 80 GB card leaves enough room for the LTX 2.3 GGUF model, text encoder, VAE, LoRA, and video upscaling flow.

The current setup has been verified on:

```text
GPU: NVIDIA A100-SXM4-80GB
PyTorch: 2.5.1+cu121
ComfyUI: 0.18.1
Gradio: 6.12.0
```

Minimum pod settings:

```text
GPU: A100 40 GB
Container disk: 40 GB or more
Persistent volume: 60 GB or more
HTTP ports: 7860 for Gradio
SSH: enable direct TCP SSH if you want local port forwarding
```

Recommended pod settings:

```text
GPU: A100 80 GB
Container disk: 60-80 GB or more
Persistent volume: 100-150 GB or more
HTTP ports: 7860 for Gradio, 8888 optional for Jupyter
SSH: enable direct TCP SSH if you want local port forwarding
```

Practical notes:

- Use A100 80 GB for the default workflow and larger resolutions/durations.
- Use A100 40 GB only if you are willing to keep resolution, duration, and batch size conservative.
- Avoid 24 GB GPUs for this setup. The model stack is large enough that VRAM pressure and CPU offload will likely make it unstable or too slow.
- Use persistent storage for `/workspace/ComfyUI/models` if you do not want to re-download weights after every pod termination.

LTX 2.3 uses large model files. The core files currently take roughly:

```text
UNet GGUF: 14.3 GB
Gemma text encoder GGUF: 6.9 GB
Embeddings connector: 2.3 GB
Distilled LoRA: 7.6 GB
VAE/upscaler/audio models: about 3.3 GB
Total model storage: about 35 GB
```

Use persistent storage when possible. `/dev/shm` is a practical fallback on large-memory A100 pods, but it is erased when the pod stops.

Do not use a 10 GB network volume. The model set is too large. Use at least 100 GB for short testing and 150 GB or more for normal development with generated outputs. A 100 GB network volume can fit the current LTX stack plus the first v2v backends, but it leaves limited room for outputs and future model experiments.

## Network Storage Layout

On Runpod, network storage is mounted at `/workspace`. Use this explicit layout:

```text
/workspace/ComfyUI/models
/workspace/hf-cache
/workspace/ComfyUI
/workspace/outputs
/workspace/tmp
```

Prepare it with:

```bash
NETWORK_ROOT=/workspace bash runpod/bootstrap_storage.sh
```

Then run setup with persistent model storage:

```bash
export NETWORK_ROOT=/workspace
export MODEL_ROOT=/workspace/ComfyUI/models
export HF_HOME=/workspace/hf-cache
export HUGGINGFACE_HUB_CACHE=/workspace/hf-cache/hub
export TRANSFORMERS_CACHE=/workspace/hf-cache/transformers
export TMPDIR=/workspace/tmp
bash runpod/setup_ltx23.sh
```

For a new pod or migrated pod, use this order:

```bash
cd /workspace/modal-notebook
NETWORK_ROOT=/workspace bash runpod/bootstrap_storage.sh
export NETWORK_ROOT=/workspace
export MODEL_ROOT=/workspace/ComfyUI/models
export HF_HOME=/workspace/hf-cache
export HUGGINGFACE_HUB_CACHE=/workspace/hf-cache/hub
export TRANSFORMERS_CACHE=/workspace/hf-cache/transformers
export TMPDIR=/workspace/tmp
bash runpod/setup_ltx23.sh
bash runpod/setup_image_generation.sh
bash runpod/setup_wan21_fun_control_v2v.sh
bash runpod/setup_v2v_ltx23.sh
nohup bash runpod/run_ui.sh > runpod/ui.log 2>&1 &
echo $! > runpod/ui.pid
```

Install the initial LTX 2.3 video-to-video backend:

```bash
bash runpod/setup_v2v_ltx23.sh
```

Install the stronger Wan 2.1 Fun Control video-to-video backend:

```bash
bash runpod/setup_wan21_fun_control_v2v.sh
```

Install the experimental Wan 2.1 VACE video editing backend:

```bash
bash runpod/setup_wan21_vace_v2v.sh
```

Install the local image generation stack:

```bash
bash runpod/setup_image_generation.sh
```

That script:

- syncs the API workflow JSON files into `/workspace/workflows`
- installs the local InsightFace face-swap stack
- installs the local Qwen multi-reference face-blend stack
- installs the experimental local Krea 2 multi-reference stack
- optionally installs local FLUX.2 Klein when `INSTALL_FLUX2_KLEIN=1` and `HF_TOKEN` is set
- leaves the video-side compatibility packages in the image venv so the same pod can run the image and video routes without extra manual pip installs

Check storage estimates and missing files:

```bash
python runpod/storage_report.py --model-root "${MODEL_ROOT:-/workspace/ComfyUI/models}"
```

## SSH

Use the private key that matches the public key you added to Runpod. If you added the key created for this project, use:

```bash
ssh <pod-id>@ssh.runpod.io -i ~/.ssh/runpod_ltx_video
```

The command Runpod showed uses `~/.ssh/id_ed25519`. That only works if the matching public key for `id_ed25519` was added to the pod.

## Upload This Project To The Pod

If your Runpod pod exposes a standard SSH service, upload from your Mac:

```bash
rsync -av --exclude .git -e "ssh -i ~/.ssh/runpod_ltx_video" \
  /Users/reginaldrandolph/Documents/LTX-Video-Generator/modal-notebook/ \
  <pod-id>@ssh.runpod.io:/workspace/modal-notebook/
```

Some Runpod proxy SSH sessions are interactive-only and block `rsync`/`scp`. If that happens, push this repo to a GitHub fork or use Runpod's file upload/terminal workflow, then put the project at:

```text
/workspace/modal-notebook
```

Then SSH in:

```bash
ssh <pod-id>@ssh.runpod.io -i ~/.ssh/runpod_ltx_video
cd /workspace/modal-notebook
```

## Install ComfyUI, Nodes, And LTX 2.3 Weights

Run this once on the pod:

```bash
bash runpod/setup_ltx23.sh
```

By default this installs into:

```text
/workspace/ComfyUI
/opt/venvs/ltx23
```

ComfyUI and model weights stay under `/workspace` because that is the preferred Runpod path for persistent storage. The Python virtualenv uses `/opt/venvs/ltx23` by default because installing thousands of package files into the network-mounted `/workspace` volume can be very slow.

LTX 2.3 needs more than 20 GB for model weights. If your pod was created with a small `/workspace` quota, either resize/attach a larger persistent volume or use memory-backed storage for the current pod session:

```bash
MODEL_ROOT=/dev/shm/ltx23-models bash runpod/setup_ltx23.sh
```

`/dev/shm` is fast and large on A100 pods, but it is volatile. If the pod stops, run the setup again to re-download the weights.

## Video-To-Video Backends

The app currently exposes four video-to-video backends:

```text
Wan 2.1 VACE Depth Restyle
Wan 2.1 VACE Pose V2V
Wan 2.1 Fun Control V2V
LTX 2.3 V2V ReTake
```

Use **Wan 2.1 VACE Depth Restyle** first for full-style transformation tests such as anime-to-realism or stronger scene restyling. It extracts Depth Anything V2 structure from the source video so the generated clip can preserve scene geometry, camera structure, and subject placement while repainting the visual style.

Use **Wan 2.1 VACE Pose V2V** for motion or character experiments where human/body motion matters more than preserving the exact source scene. It extracts OpenPose motion from the source video, so it gives the model more freedom to invent a new environment.

Both VACE workflows use the 14B VACE model with a Q4 GGUF quantization so it can fit alongside the existing test models.

Use **Wan 2.1 Fun Control V2V** for controlled motion experiments where preserving the original pose/structure is more important than aggressive style replacement. In testing, this backend can over-preserve the source appearance, so it is not the best first choice for anime-to-realism or full-scene restyling.

Use **LTX 2.3 V2V ReTake** for lighter retake/editing tests where preserving the original structure is more important than replacing the visual style. That backend is useful, but it is not the best fit for converting an entire anime clip into realistic footage.

The initial Wan workflow caps each generation to 161 loaded frames to keep testing practical on one A100. Longer 60 second inputs need chunking and stitching before they are practical at 720p. The provider structure is set up so that chunking, upscaling, interpolation, identity-preservation passes, and alternate backends can be added without changing the original LTX text/image flow.

## Launch The Gradio UI

Foreground launch on the pod:

```bash
cd /workspace/modal-notebook
bash runpod/run_ui.sh
```

Background launch on the pod:

```bash
cd /workspace/modal-notebook
nohup bash runpod/run_ui.sh > runpod/ui.log 2>&1 &
echo $! > runpod/ui.pid
```

The app listens on port `7860`. ComfyUI listens on `127.0.0.1:8188` and is started automatically on the first generation.

The dedicated image workspace is mounted at:

```text
http://127.0.0.1:7860/image-generation
```

It uses image-generation backends from `runpod/model_manifest.json`. The local FLUX.2 Klein backend uses `runpod/workflows/api/flux2_klein_image_api.json`, `ComfyUI-GGUF`, the ponpoke GGUF text encoder, and the Comfy FLUX.2 VAE. It is a text-to-image graph. True separate multi-reference input requires a workflow with image-conditioning slots; the included BFL API backend exposes up to 8 reference-image slots.

The image workspace also includes:

- `SDXL Turbo Image Test`: local smoke-test workflow for verifying ComfyUI queueing and image output.
- `FLUX.2 BFL API Multi-Reference`: ComfyUI `Flux2ImageNode` workflow with up to 8 reference-image slots. This requires Comfy Org/BFL API credentials in ComfyUI.
- `FLUX.2 Klein Image Generation`: local text-to-image workflow using `flux-2-klein-9b.safetensors`, `flux2-klein-9b-uncensored-q4_k_m.gguf`, and `flux2-vae.safetensors`.
- `Krea 2 Local Multi-Reference`: experimental local Krea 2 workflow using ordered multimodal reference images through a custom ComfyUI node.
- `Qwen Image Edit Multi-Reference`: local image-edit workflow using up to 3 separate references to synthesize one integrated result.
- `InsightFace Face Swap`: local source-face to target-body/composition swap backend that uses two reference images and writes a downloadable PNG result.

The image UI now returns a real downloadable file alongside the preview, so after each generation you can save the result directly from the `Download Image` control.

`bash runpod/setup_image_generation.sh` installs `InsightFace Face Swap` by default. If you want to skip it on a lighter pod setup, run `INSTALL_INSIGHTFACE_SWAP=0 bash runpod/setup_image_generation.sh`.

For the local Krea 2 multi-reference path, run:

```bash
bash runpod/setup_krea2_image.sh
```

This script downloads:

- `krea2_turbo_fp8_scaled.safetensors`
- `qwen3vl_4b_fp8_scaled.safetensors`
- `qwen_image_vae.safetensors`

It also installs the repo's `ComfyUI-LTXImageNodes` custom node into `ComfyUI/custom_nodes` so the local Krea workflow can accept multiple ordered reference images.

For the local Qwen face-blend path, run:

```bash
bash runpod/setup_qwen_face_blend_image.sh
```

This script downloads:

- `qwen_image_edit_2511_bf16.safetensors`
- `qwen_2.5_vl_7b_fp8_scaled.safetensors`
- `qwen_image_vae.safetensors`

By default it stores the large source files under `/root/comfy-models` and symlinks them into `/workspace/ComfyUI/models`. That avoids common `/workspace` quota issues on Runpod while keeping ComfyUI's model discovery path unchanged.

For the local FLUX.2 Klein + ponpoke text encoder path, accept the gated Hugging Face terms in your browser first, then run:

```bash
HF_TOKEN=hf_xxx bash runpod/setup_flux2_klein_image.sh
```

Required gated pages:

```text
https://huggingface.co/black-forest-labs/FLUX.2-klein-9B
https://huggingface.co/ponpoke/flux2-klein-9b-uncensored-text-encoder
```

If your pod template exposes HTTP port `7860`, open that endpoint in Runpod. Otherwise, create an SSH tunnel from your Mac:

```bash
ssh -L 7860:127.0.0.1:7860 <pod-id>@ssh.runpod.io -i ~/.ssh/runpod_ltx_video
```

Runpod's proxied `ssh.runpod.io` connection may reject port forwarding with `unsupported channel type`. If that happens, use the **SSH over exposed TCP** host and port from the Runpod Connect panel:

```bash
ssh -N -L 7861:127.0.0.1:7860 root@<direct-tcp-host> -p <direct-tcp-port> -i ~/.ssh/runpod_ltx_video
```

Then open:

```text
http://127.0.0.1:7861
```

The first number is your Mac's local port. The second number is the pod's Gradio port. If local port `7860` is already in use, use `7861` or another free local port.

## Operations Commands

Watch the Gradio app logs:

```bash
cd /workspace/modal-notebook
tail -f runpod/ui.log
```

Watch the ComfyUI render logs:

```bash
tail -f /workspace/ComfyUI/comfyui.log
```

The app also reads the ComfyUI log while a job is running and shows elapsed time,
prompt id, percent, step count, and per-step timing in the Gradio progress text.

Check whether the UI and ComfyUI backend are running:

```bash
ps -ef | grep -E 'runpod/app.py|ComfyUI/main.py' | grep -v grep
ss -ltnp | grep -E ':7860|:8188'
```

Restart the Gradio UI:

```bash
cd /workspace/modal-notebook
kill $(cat runpod/ui.pid) 2>/dev/null || true
pkill -f '/workspace/modal-notebook/runpod/app.py' 2>/dev/null || true
nohup bash runpod/run_ui.sh > runpod/ui.log 2>&1 &
echo $! > runpod/ui.pid
```

Stop ComfyUI if it needs a clean reload:

```bash
pkill -f '/workspace/ComfyUI/main.py' 2>/dev/null || true
```

List generated videos:

```bash
ls -lh /workspace/ComfyUI/output/video
```

Check GPU usage while a render is running:

```bash
nvidia-smi
watch -n 2 nvidia-smi
```

Check model storage and quota:

```bash
df -h /workspace /dev/shm /
du -sh /workspace/ComfyUI /dev/shm/ltx23-models 2>/dev/null
find -L /workspace/ComfyUI/models -maxdepth 2 -type f \( -name '*.gguf' -o -name '*.safetensors' \) -printf '%p %s bytes\n' | sort
```

Verify CUDA from the project environment:

```bash
source /opt/venvs/ltx23/bin/activate
python - <<'PY'
import torch
print("torch", torch.__version__)
print("cuda_available", torch.cuda.is_available())
print("gpu", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none")
PY
```

## Common Issues

### Gradio Shows An Error After The Render Finishes

Check the log:

```bash
tail -n 240 /workspace/modal-notebook/runpod/ui.log
```

If the log says `Prompt executed` and then raises `gradio.exceptions.InvalidPathError`, make sure the pod has the latest code. The Gradio app must launch with `/workspace/ComfyUI/output` in `allowed_paths`.

```bash
cd /workspace/modal-notebook
git pull
kill $(cat runpod/ui.pid) 2>/dev/null || true
nohup bash runpod/run_ui.sh > runpod/ui.log 2>&1 &
echo $! > runpod/ui.pid
```

### LTX Image-To-Video Fails With `GGUF magic invalid`

One of the GGUF model files on disk is corrupt, usually from an interrupted download or a quota issue. The current `runpod/setup_ltx23.sh` and `runpod/setup_v2v_ltx23.sh` scripts now detect invalid GGUF headers and quarantine those files before re-downloading them. Re-run the relevant setup script:

```bash
bash runpod/setup_ltx23.sh
```

If you are also using the LTX ReTake video-to-video backend, then run:

```bash
bash runpod/setup_v2v_ltx23.sh
```

Then restart the UI:

```bash
kill $(cat runpod/ui.pid) 2>/dev/null || true
pkill -f '/workspace/modal-notebook/runpod/app.py' 2>/dev/null || true
nohup bash runpod/run_ui.sh > runpod/ui.log 2>&1 &
echo $! > runpod/ui.pid
```

### Local Tunnel Says Address Already In Use

Use a different local port:

```bash
ssh -N -L 7861:127.0.0.1:7860 root@<direct-tcp-host> -p <direct-tcp-port> -i ~/.ssh/runpod_ltx_video
```

Then open `http://127.0.0.1:7861`.

### Setup Fails With Disk Quota Exceeded

Your `/workspace` quota is too small for the model set. Prefer resizing or attaching persistent storage. For a temporary active-session workaround:

```bash
MODEL_ROOT=/dev/shm/ltx23-models bash runpod/setup_ltx23.sh
```

## Video-To-Video Backends

The app has a video-to-video tab and a backend abstraction. The initial backend is `ltx23_v2v_retake`, defined in `runpod/model_manifest.json`.

It supports:

- input videos up to 60 seconds
- required prompt
- optional reference images
- target 720p settings
- optional original audio passthrough/remux
- ComfyUI API workflow JSON patching

The initial backend uses the community LTX 2.3 ReTake source workflow from:

```text
https://huggingface.co/RuneXX/LTX-2.3-Workflows
```

`setup_v2v_ltx23.sh` downloads that source workflow and the extra model files. The downloaded source workflow is a ComfyUI editor workflow, so it must be exported once as API JSON before the Gradio app can queue it programmatically.

For local graph editing without using the pod GPU, see:

```text
docs/local-comfy-workflow-editing.md
```

Repo-tracked workflow locations:

```text
runpod/workflows/source/
runpod/workflows/api/
```

The app now prefers the repo-tracked API workflow when it exists:

```text
runpod/workflows/api/ltx23_v2v_retake_api.json
```

If that file is missing, it falls back to the older pod storage path:

```text
/workspace/workflows/ltx23_v2v_retake_api.json
```

To activate it on a pod:

1. Run `bash runpod/setup_v2v_ltx23.sh`.
2. Open ComfyUI at port `8188` through a tunnel or Runpod HTTP service.
3. Load `/workspace/workflows/source/LTX-2.3_-_V2V_ReTake_recreate_any_section_of_any_video.json`, or load the repo-tracked source workflow.
4. Export the workflow as API JSON.
5. Save it to `runpod/workflows/api/ltx23_v2v_retake_api.json` when you want the graph tracked in Git. For one-off pod tests, save it to `/workspace/workflows/ltx23_v2v_retake_api.json`.
6. Inspect the API workflow nodes:

   ```bash
   python runpod/inspect_workflow.py /workspace/workflows/ltx23_v2v_retake_api.json
   ```

7. Fill in or confirm the node patch mappings in `runpod/model_manifest.json`.
8. Restart the Gradio UI.

The current ReTake backend exposes app controls for full-video retake, retake start/end seconds, transform strength, prompt CFG, and NAG prompt influence. These patch the ComfyUI nodes that most directly affect whether the output meaningfully changes or simply preserves the input.

For this initial LTX ReTake backend, the first uploaded reference image overrides the workflow's `ref_image` channel. Use it for prompts such as `Change the person in the video to the character in this image`. If no reference image is uploaded, the workflow keeps its original first-frame reference behavior.

Future backends can use the same manifest shape with different workflow JSON and patch mappings.

The detailed design is in `runpod/ARCHITECTURE.md`.

## Useful Environment Variables

```bash
COMFY_PATH=/workspace/ComfyUI
COMFY_LOG_PATH=/workspace/ComfyUI/comfyui.log
VENV_PATH=/opt/venvs/ltx23
MODEL_ROOT=/workspace/ComfyUI/models
PIP_CACHE_DIR=/tmp/pip-cache-ltx23
GRADIO_PORT=7860
COMFY_PORT=8188
```

Example:

```bash
GRADIO_PORT=3000 bash runpod/run_ui.sh
```
