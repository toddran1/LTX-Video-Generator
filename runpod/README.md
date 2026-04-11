# Runpod LTX 2.3 Setup

This folder turns the original Modal notebook flow into scripts that run directly on a Runpod A100 pod.

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

## Launch The Gradio UI

On the pod:

```bash
cd /workspace/modal-notebook
bash runpod/run_ui.sh
```

The app listens on port `7860`.

If your pod template exposes HTTP port `7860`, open that endpoint in Runpod. Otherwise, create an SSH tunnel from your Mac:

```bash
ssh -L 7860:127.0.0.1:7860 xh1vb7ucieubve-64412072@ssh.runpod.io -i ~/.ssh/runpod_ltx_video
```

Then open:

```text
http://127.0.0.1:7860
```

## Useful Environment Variables

```bash
COMFY_PATH=/workspace/ComfyUI
VENV_PATH=/opt/venvs/ltx23
GRADIO_PORT=7860
COMFY_PORT=8188
```

Example:

```bash
GRADIO_PORT=3000 bash runpod/run_ui.sh
```
