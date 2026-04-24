import os
from datetime import datetime

import gradio as gr

from ltx_video.comfy import ComfyClient
from ltx_video.manifest import enabled_v2v_backends, load_manifest
from ltx_video.providers import ComfyVideoToVideoProvider, LtxTextImageProvider, uploaded_path
from ltx_video.runtime_state import (
    create_job,
    get_job,
    latest_active_job,
    list_jobs,
    persist_request_files,
    update_job,
)


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


def _format_timestamp(timestamp):
    if not timestamp:
        return "unknown"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _job_label(job):
    output_name = os.path.basename(job.get("output_path") or "") or "pending"
    created = _format_timestamp(job.get("created_at"))
    backend = job.get("backend_label", "unknown backend")
    status = job.get("status", "unknown")
    return f"{created} | {status} | {backend} | {output_name}"


def _job_choices():
    jobs = sorted(list_jobs(), key=lambda job: job.get("created_at", 0), reverse=True)
    return [(_job_label(job), job["id"]) for job in jobs]


def _job_details(job):
    if not job:
        return "No saved job selected."

    lines = [
        f"Job ID: `{job.get('id')}`",
        f"Status: `{job.get('status', 'unknown')}`",
        f"Backend: `{job.get('backend_label', 'unknown')}`",
        f"Created: `{_format_timestamp(job.get('created_at'))}`",
        f"Updated: `{_format_timestamp(job.get('updated_at'))}`",
    ]
    if job.get("prompt_id"):
        lines.append(f"Prompt ID: `{job['prompt_id']}`")
    if job.get("output_path"):
        lines.append(f"Output: `{job['output_path']}`")
    if job.get("error"):
        lines.append(f"Error: `{job['error']}`")
    request = job.get("request", {})
    if request.get("reference_mode"):
        lines.append(f"Reference Mode: `{request['reference_mode']}`")
    if request.get("reference_index"):
        lines.append(f"Reference Index: `{request['reference_index']}`")
    if request.get("prompt"):
        lines.append("")
        lines.append("Prompt:")
        lines.append(request["prompt"])
    return "\n".join(lines)


def _active_job_markdown():
    job = latest_active_job()
    if not job:
        return "No active video-to-video job."

    status = job.get("status", "unknown")
    prompt_id = job.get("prompt_id")
    started_at = job.get("started_at") or job.get("created_at")
    if prompt_id and status in {"running", "starting", "cancelling"} and comfy.is_running():
        try:
            _, render_status = comfy.render_status(prompt_id, started_at or job.get("updated_at", 0))
            return (
                f"Active Job: `{job['id']}`\n\n"
                f"Backend: `{job.get('backend_label', 'unknown')}`\n\n"
                f"Status: `{status}`\n\n"
                f"{render_status}"
            )
        except Exception:
            pass

    fallback = [
        f"Active Job: `{job['id']}`",
        f"Backend: `{job.get('backend_label', 'unknown')}`",
        f"Status: `{status}`",
    ]
    if prompt_id:
        fallback.append(f"Prompt ID: `{prompt_id}`")
    if job.get("error"):
        fallback.append(f"Error: `{job['error']}`")
    return "\n\n".join(fallback)


def refresh_v2v_dashboard(selected_job_id=None):
    selected_job = get_job(selected_job_id) if selected_job_id else None
    choices = _job_choices()
    if not selected_job and choices:
        selected_job_id = choices[0][1]
        selected_job = get_job(selected_job_id)
    elif selected_job_id and not selected_job and choices:
        selected_job_id = choices[0][1]
        selected_job = get_job(selected_job_id)

    preview_path = selected_job.get("output_path") if selected_job and selected_job.get("output_path") else None
    download_path = preview_path
    return (
        _active_job_markdown(),
        gr.update(choices=choices, value=selected_job_id),
        _job_details(selected_job),
        preview_path,
        download_path,
    )


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


def _run_v2v_job(job_record, progress):
    backend_label = job_record["backend_label"]
    request = job_record["request"]
    provider = v2v_provider_by_label[backend_label]

    def on_queued(prompt_id, started_at, source_video, reference_files):
        update_job(
            job_record["id"],
            status="running",
            prompt_id=prompt_id,
            started_at=started_at,
            source_video=source_video,
            reference_files=reference_files,
        )

    def on_completed(output_path, completed_at, prompt_id):
        update_job(
            job_record["id"],
            status="completed",
            output_path=output_path,
            completed_at=completed_at,
            prompt_id=prompt_id,
            error=None,
        )

    def on_failed(message):
        update_job(job_record["id"], status="failed", error=message)

    try:
        return provider.generate(
            input_video=request["input_video"],
            prompt=request["prompt"],
            reference_files=request["reference_files"],
            reference_mode=request.get("reference_mode", "first"),
            reference_index=request.get("reference_index", 1),
            target_width=request["target_width"],
            target_height=request["target_height"],
            output_resolution=request["output_resolution"],
            seed=request["seed"],
            preserve_audio=request["preserve_audio"],
            retake_full_video=request["retake_full_video"],
            retake_start=request["retake_start"],
            retake_end=request["retake_end"],
            transform_strength=request["transform_strength"],
            prompt_cfg=request["prompt_cfg"],
            nag_scale=request["nag_scale"],
            progress=progress,
            job_id=job_record["id"],
            on_queued=on_queued,
            on_completed=on_completed,
            on_failed=on_failed,
        )
    except Exception as error:
        update_job(job_record["id"], status="failed", error=str(error))
        raise


def generate_v2v_video(
    backend_label,
    input_video,
    prompt,
    reference_files,
    reference_mode,
    reference_index,
    target_width,
    target_height,
    output_resolution,
    seed,
    preserve_audio,
    retake_full_video,
    retake_start,
    retake_end,
    transform_strength,
    prompt_cfg,
    nag_scale,
    progress=gr.Progress(),
):
    if backend_label not in v2v_provider_by_label:
        raise gr.Error("No enabled video-to-video backend is configured.")

    input_video = uploaded_path(input_video)
    reference_files = [uploaded_path(path) for path in (reference_files or [])]
    reference_files = [path for path in reference_files if path]
    if not input_video:
        raise gr.Error("Upload an input video.")

    request_dir, persisted_video, persisted_references = persist_request_files(input_video, reference_files)
    job_record = create_job(
        {
            "type": "video_to_video",
            "backend_label": backend_label,
            "status": "starting",
            "request_dir": request_dir,
            "request": {
                "input_video": persisted_video,
                "reference_files": persisted_references,
                "reference_mode": reference_mode,
                "reference_index": int(reference_index),
                "prompt": prompt,
                "target_width": int(target_width),
                "target_height": int(target_height),
                "output_resolution": output_resolution,
                "seed": int(seed),
                "preserve_audio": bool(preserve_audio),
                "retake_full_video": bool(retake_full_video),
                "retake_start": float(retake_start),
                "retake_end": float(retake_end),
                "transform_strength": float(transform_strength),
                "prompt_cfg": float(prompt_cfg),
                "nag_scale": float(nag_scale),
            },
        }
    )
    return _run_v2v_job(job_record, progress)


def retry_v2v_job(selected_job_id, progress=gr.Progress()):
    job = get_job(selected_job_id)
    if not job:
        raise gr.Error("Select a saved job to retry.")
    if not job.get("request"):
        raise gr.Error("This saved output does not have retry metadata.")

    retry_job = create_job(
        {
            "type": "video_to_video",
            "backend_label": job["backend_label"],
            "status": "starting",
            "retry_of": job["id"],
            "request_dir": job.get("request_dir"),
            "request": job["request"],
        }
    )
    return _run_v2v_job(retry_job, progress)


def cancel_active_v2v_job(selected_job_id):
    job = get_job(selected_job_id) if selected_job_id else latest_active_job()
    if not job:
        return refresh_v2v_dashboard(selected_job_id)

    if job.get("status") not in {"starting", "running", "cancelling"}:
        return refresh_v2v_dashboard(job["id"])

    if comfy.is_running():
        try:
            comfy.interrupt()
        except Exception as error:
            update_job(job["id"], status="failed", error=f"Interrupt failed: {error}")
            return refresh_v2v_dashboard(job["id"])

    update_job(job["id"], status="cancelled", error="Cancelled by user.")
    return refresh_v2v_dashboard(job["id"])


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
                    reference_mode_input = gr.Dropdown(
                        choices=[
                            ("Use First Uploaded Reference", "first"),
                            ("Use Specific Uploaded Reference", "specific"),
                            ("Create Montage From All References", "montage"),
                        ],
                        value="first",
                        label="Reference Handling",
                    )
                    reference_index_input = gr.Number(
                        value=1,
                        label="Reference Index (1-based)",
                        precision=0,
                        visible=False,
                    )
                gr.Markdown(
                    "These workflows accept one actual reference image at inference time. "
                    "Use Reference Handling to choose the first uploaded image, select a specific uploaded image, "
                    "or combine multiple uploads into a single montage guide image."
                )
                with gr.Row():
                    v2v_width_slider = gr.Slider(minimum=256, maximum=1280, step=16, value=848, label="Base Generation Width")
                    v2v_height_slider = gr.Slider(minimum=256, maximum=720, step=16, value=480, label="Base Generation Height")
                output_resolution_input = gr.Dropdown(
                    choices=["720p", "1080p"],
                    value="720p",
                    label="Upscaled Output Resolution",
                )
                with gr.Row():
                    v2v_seed_input = gr.Number(value=43, label="Seed", precision=0)
                    preserve_audio_input = gr.Checkbox(value=True, label="Preserve Original Audio")
                with gr.Accordion("Advanced V2V Controls", open=False):
                    retake_full_video_input = gr.Checkbox(
                        value=True,
                        label="Transform Full Video",
                    )
                    with gr.Row():
                        retake_start_input = gr.Number(value=0.0, label="Retake Start Seconds")
                        retake_end_input = gr.Number(value=60.0, label="Retake End Seconds")
                    with gr.Row():
                        transform_strength_input = gr.Slider(
                            minimum=0.1,
                            maximum=1.0,
                            step=0.05,
                            value=1.0,
                            label="Transform Strength",
                        )
                        prompt_cfg_input = gr.Slider(
                            minimum=0.5,
                            maximum=5.0,
                            step=0.1,
                            value=1.4,
                            label="Prompt CFG",
                        )
                    nag_scale_input = gr.Slider(
                        minimum=0.0,
                        maximum=20.0,
                        step=0.5,
                        value=11.0,
                        label="NAG Prompt Influence",
                    )
                v2v_generate_btn = gr.Button("Transform Video", variant="primary")
            with gr.Column(scale=1):
                v2v_output = gr.Video(label="Transformed Output")
                active_job_status = gr.Markdown("No active video-to-video job.")
                gr.Markdown("## Saved Outputs")
                saved_jobs = gr.Radio(
                    choices=[],
                    label="Completed / saved jobs",
                    value=None,
                )
                with gr.Row():
                    refresh_jobs_btn = gr.Button("Refresh")
                    cancel_job_btn = gr.Button("Cancel Active Job")
                    retry_job_btn = gr.Button("Retry Selected")
                saved_job_video = gr.Video(label="Saved Output Preview")
                saved_job_download = gr.File(label="Download Selected Output")
                saved_job_details = gr.Markdown("No saved job selected.")

    poll_timer = gr.Timer(5)

    def update_visibility(mode):
        return gr.update(visible=(mode == "Image-to-Video"))

    def update_reference_index_visibility(reference_mode):
        return gr.update(visible=(reference_mode == "specific"))

    mode_selector.change(fn=update_visibility, inputs=mode_selector, outputs=image_input)
    reference_mode_input.change(
        fn=update_reference_index_visibility,
        inputs=reference_mode_input,
        outputs=reference_index_input,
    )
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
    v2v_generate = v2v_generate_btn.click(
        fn=generate_v2v_video,
        inputs=[
            backend_selector,
            v2v_video_input,
            v2v_prompt_input,
            v2v_reference_input,
            reference_mode_input,
            reference_index_input,
            v2v_width_slider,
            v2v_height_slider,
            output_resolution_input,
            v2v_seed_input,
            preserve_audio_input,
            retake_full_video_input,
            retake_start_input,
            retake_end_input,
            transform_strength_input,
            prompt_cfg_input,
            nag_scale_input,
        ],
        outputs=v2v_output,
    )
    v2v_generate.then(
        fn=refresh_v2v_dashboard,
        inputs=saved_jobs,
        outputs=[
            active_job_status,
            saved_jobs,
            saved_job_details,
            saved_job_video,
            saved_job_download,
        ],
    )
    retry_click = retry_job_btn.click(
        fn=retry_v2v_job,
        inputs=saved_jobs,
        outputs=v2v_output,
    )
    retry_click.then(
        fn=refresh_v2v_dashboard,
        inputs=saved_jobs,
        outputs=[
            active_job_status,
            saved_jobs,
            saved_job_details,
            saved_job_video,
            saved_job_download,
        ],
    )
    cancel_job_btn.click(
        fn=cancel_active_v2v_job,
        inputs=saved_jobs,
        outputs=[
            active_job_status,
            saved_jobs,
            saved_job_details,
            saved_job_video,
            saved_job_download,
        ],
    )
    refresh_jobs_btn.click(
        fn=refresh_v2v_dashboard,
        inputs=saved_jobs,
        outputs=[
            active_job_status,
            saved_jobs,
            saved_job_details,
            saved_job_video,
            saved_job_download,
        ],
    )
    saved_jobs.change(
        fn=refresh_v2v_dashboard,
        inputs=saved_jobs,
        outputs=[
            active_job_status,
            saved_jobs,
            saved_job_details,
            saved_job_video,
            saved_job_download,
        ],
    )
    demo.load(
        fn=refresh_v2v_dashboard,
        inputs=saved_jobs,
        outputs=[
            active_job_status,
            saved_jobs,
            saved_job_details,
            saved_job_video,
            saved_job_download,
        ],
    )
    poll_timer.tick(
        fn=refresh_v2v_dashboard,
        inputs=saved_jobs,
        outputs=[
            active_job_status,
            saved_jobs,
            saved_job_details,
            saved_job_video,
            saved_job_download,
        ],
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=GRADIO_PORT,
        share=False,
        allowed_paths=[OUTPUT_PATH],
    )
