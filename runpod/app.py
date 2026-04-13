import os

import gradio as gr

from ltx_video.comfy import ComfyClient
from ltx_video.manifest import enabled_v2v_backends, load_manifest
from ltx_video.providers import ComfyVideoToVideoProvider, LtxTextImageProvider


COMFY_PATH = os.environ.get("COMFY_PATH", "/workspace/ComfyUI")
OUTPUT_PATH = os.path.join(COMFY_PATH, "output")
COMFY_PORT = int(os.environ.get("COMFY_PORT", "8188"))
GRADIO_PORT = int(os.environ.get("GRADIO_PORT", "7860"))
WORKFLOW_URL = os.environ.get(
    "WORKFLOW_URL",
    "https://raw.githubusercontent.com/AICHUCKY/Comfyui-Workflows/AICHUCKY-patch-1/Ltx2.3%20.json",
)


manifest = load_manifest()
comfy = ComfyClient(COMFY_PATH, COMFY_PORT)
ltx_provider = LtxTextImageProvider(comfy, WORKFLOW_URL)
v2v_backends = enabled_v2v_backends(manifest)
v2v_provider_by_label = {
    backend.get("label", backend["id"]): ComfyVideoToVideoProvider(comfy, backend)
    for backend in v2v_backends
}


def generate_ltx_video(
    mode,
    image_filepath,
    prompt,
    width,
    height,
    duration,
    seed,
    progress=gr.Progress(),
):
    return ltx_provider.generate(
        mode=mode,
        image_filepath=image_filepath,
        prompt=prompt,
        width=width,
        height=height,
        duration=duration,
        seed=seed,
        progress=progress,
    )


def generate_v2v_video(
    backend_label,
    input_video,
    prompt,
    reference_files,
    target_width,
    target_height,
    seed,
    preserve_audio,
    progress=gr.Progress(),
):
    if backend_label not in v2v_provider_by_label:
        raise gr.Error("No enabled video-to-video backend is configured.")

    return v2v_provider_by_label[backend_label].generate(
        input_video=input_video,
        prompt=prompt,
        reference_files=reference_files,
        target_width=target_width,
        target_height=target_height,
        seed=seed,
        preserve_audio=preserve_audio,
        progress=progress,
    )


with gr.Blocks(theme=gr.themes.Monochrome()) as demo:
    gr.Markdown("# LTX 2.3 Video Generator")
    gr.Markdown("Generate and transform videos on a Runpod GPU.")

    with gr.Tab("LTX Text / Image"):
        with gr.Row():
            with gr.Column(scale=1):
                mode_selector = gr.Radio(
                    ["Text-to-Video", "Image-to-Video"],
                    value="Text-to-Video",
                    label="Generation Mode",
                )
                image_input = gr.Image(type="filepath", label="Starting Image", visible=False)
                prompt_input = gr.Textbox(label="Prompt", placeholder="A cinematic shot...", lines=3)
                with gr.Row():
                    width_slider = gr.Slider(minimum=256, maximum=1920, step=32, value=832, label="Width")
                    height_slider = gr.Slider(minimum=256, maximum=1080, step=32, value=480, label="Height")
                with gr.Row():
                    duration_slider = gr.Slider(minimum=1, maximum=10, step=1, value=3, label="Duration")
                    seed_input = gr.Number(value=43, label="Seed", precision=0)
                generate_btn = gr.Button("Generate Video", variant="primary")
            with gr.Column(scale=1):
                video_output = gr.Video(label="Generated Output")

    with gr.Tab("Video-to-Video"):
        gr.Markdown(
            "Transform an input video with a prompt and optional reference images. "
            "Inputs are validated before they are queued in ComfyUI."
        )
        with gr.Row():
            with gr.Column(scale=1):
                backend_choices = list(v2v_provider_by_label.keys())
                backend_selector = gr.Dropdown(
                    choices=backend_choices,
                    value=backend_choices[0] if backend_choices else None,
                    label="Video-to-Video Backend",
                )
                v2v_video_input = gr.Video(label="Input Video", sources=["upload"])
                v2v_prompt_input = gr.Textbox(
                    label="Prompt",
                    placeholder="Describe the transformation...",
                    lines=4,
                )
                v2v_reference_input = gr.File(
                    file_count="multiple",
                    file_types=["image"],
                    label="Reference Images",
                )
                with gr.Row():
                    v2v_width_slider = gr.Slider(minimum=256, maximum=1280, step=32, value=1280, label="Target Width")
                    v2v_height_slider = gr.Slider(minimum=256, maximum=720, step=32, value=720, label="Target Height")
                with gr.Row():
                    v2v_seed_input = gr.Number(value=43, label="Seed", precision=0)
                    preserve_audio_input = gr.Checkbox(value=True, label="Preserve Original Audio")
                v2v_generate_btn = gr.Button("Transform Video", variant="primary")
            with gr.Column(scale=1):
                v2v_output = gr.Video(label="Transformed Output")

    def update_visibility(mode):
        return gr.update(visible=(mode == "Image-to-Video"))

    mode_selector.change(fn=update_visibility, inputs=mode_selector, outputs=image_input)
    generate_btn.click(
        fn=generate_ltx_video,
        inputs=[
            mode_selector,
            image_input,
            prompt_input,
            width_slider,
            height_slider,
            duration_slider,
            seed_input,
        ],
        outputs=video_output,
    )
    v2v_generate_btn.click(
        fn=generate_v2v_video,
        inputs=[
            backend_selector,
            v2v_video_input,
            v2v_prompt_input,
            v2v_reference_input,
            v2v_width_slider,
            v2v_height_slider,
            v2v_seed_input,
            preserve_audio_input,
        ],
        outputs=v2v_output,
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=GRADIO_PORT,
        share=False,
        allowed_paths=[OUTPUT_PATH],
    )
