import math

import comfy.utils
from typing_extensions import override

from comfy_api.latest import ComfyExtension, io


KREA_MULTI_REFERENCE_TEMPLATE = """<|im_start|>system
You are preparing conditioning for a Krea 2 image generation. Analyze each provided reference image for the visual information that matters to the user's request, including identity cues, facial structure, age, skin texture, hair, lighting, materials, styling, camera feel, composition, clothing, and environment when relevant. Combine useful traits from multiple references into one coherent new image. Do not produce a collage or literal copy of the references. Follow the user's text instruction as the final authority for what to synthesize.<|im_end|>
<|im_start|>user
{}<|im_end|>
<|im_start|>assistant
"""


class TextEncodeKreaMultiReference(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="TextEncodeKreaMultiReference",
            display_name="Text Encode Krea Multi-Reference",
            category="model/conditioning/krea",
            description=(
                "Encodes a prompt plus up to four ordered reference images for local Krea 2 generation. "
                "This is intended for experimental multi-reference synthesis on top of Krea 2's Qwen3-VL conditioning path."
            ),
            inputs=[
                io.Clip.Input("clip"),
                io.String.Input("prompt", multiline=True, dynamic_prompts=True),
                io.Image.Input("image1", optional=True),
                io.Image.Input("image2", optional=True),
                io.Image.Input("image3", optional=True),
                io.Image.Input("image4", optional=True),
            ],
            outputs=[
                io.Conditioning.Output(),
            ],
            is_experimental=True,
        )

    @classmethod
    def execute(cls, clip, prompt, image1=None, image2=None, image3=None, image4=None) -> io.NodeOutput:
        refs = [image1, image2, image3, image4]
        images_vl = []
        image_prompt_parts = []

        for index, image in enumerate(refs, start=1):
            if image is None:
                continue

            samples = image.movedim(-1, 1)
            target_pixels = int(384 * 384)
            scale_by = math.sqrt(target_pixels / (samples.shape[3] * samples.shape[2]))
            width = round(samples.shape[3] * scale_by)
            height = round(samples.shape[2] * scale_by)
            resized = comfy.utils.common_upscale(samples, width, height, "area", "disabled")
            images_vl.append(resized.movedim(1, -1)[:, :, :, :3])
            image_prompt_parts.append(f"Reference {index}: <|vision_start|><|image_pad|><|vision_end|>")

        multimodal_prefix = "\n".join(image_prompt_parts)
        full_prompt = prompt if not multimodal_prefix else f"{multimodal_prefix}\n{prompt}"
        tokens = clip.tokenize(
            full_prompt,
            images=images_vl,
            llama_template=KREA_MULTI_REFERENCE_TEMPLATE,
        )
        conditioning = clip.encode_from_tokens_scheduled(tokens)
        return io.NodeOutput(conditioning)


class LTXImageNodesExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [TextEncodeKreaMultiReference]


async def comfy_entrypoint() -> LTXImageNodesExtension:
    return LTXImageNodesExtension()
