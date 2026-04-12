# Runpod LTX 2.3 Setup

This folder turns the original Modal notebook flow into scripts that run directly on a Runpod A100 pod.

## Recommended Runpod Configuration

Use an **NVIDIA A100 80 GB** pod for the best balance of VRAM headroom and cost. The current setup has been verified on:

```text
GPU: NVIDIA A100-SXM4-80GB
PyTorch: 2.5.1+cu121
ComfyUI: 0.18.1
Gradio: 6.12.0
```

Recommended pod settings:

```text
GPU: A100 80 GB
Container disk: 40 GB or more
Persistent volume: 80-100 GB or more
HTTP ports: 7860 for Gradio, 8888 optional for Jupyter
SSH: enable direct TCP SSH if you want local port forwarding
```

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

## SSH

Use the private key that matches the public key you added to Runpod. If you added the key created for this project, use:

```bash
ssh xh1vb7ucieubve-64412072@ssh.runpod.io -i ~/.ssh/runpod_ltx_video
```

The command Runpod showed uses `~/.ssh/id_ed25519`. That only works if the matching public key for `id_ed25519` was added to the pod.

## Upload This Project To The Pod

If your Runpod pod exposes a standard SSH service, upload from your Mac:

```bash
rsync -av --exclude .git -e "ssh -i ~/.ssh/runpod_ltx_video" \
  /Users/reginaldrandolph/Documents/LTX-Video-Generator/modal-notebook/ \
  xh1vb7ucieubve-64412072@ssh.runpod.io:/workspace/modal-notebook/
```

Some Runpod proxy SSH sessions are interactive-only and block `rsync`/`scp`. If that happens, push this repo to a GitHub fork or use Runpod's file upload/terminal workflow, then put the project at:

```text
/workspace/modal-notebook
```

Then SSH in:

```bash
ssh xh1vb7ucieubve-64412072@ssh.runpod.io -i ~/.ssh/runpod_ltx_video
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

If your pod template exposes HTTP port `7860`, open that endpoint in Runpod. Otherwise, create an SSH tunnel from your Mac:

```bash
ssh -L 7860:127.0.0.1:7860 xh1vb7ucieubve-64412072@ssh.runpod.io -i ~/.ssh/runpod_ltx_video
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

Watch the combined Gradio and ComfyUI logs:

```bash
cd /workspace/modal-notebook
tail -f runpod/ui.log
```

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

## Useful Environment Variables

```bash
COMFY_PATH=/workspace/ComfyUI
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
