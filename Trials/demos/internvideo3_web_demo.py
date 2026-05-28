from __future__ import annotations

import argparse
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path

import gradio as gr
import torch
from PIL import Image
from qwen_vl_utils import process_vision_info
from transformers import AutoModelForCausalLM, AutoProcessor


DEFAULT_MODEL_PATH = Path("Trials/checkpoints/InternVideo3-8B-Instruct")
BASE_PIXELS = 128 * 32 * 32
GENERATION_LOCK = threading.Lock()


def available_dataset_videos() -> list[tuple[str, str]]:
    videos = []
    for path in sorted(Path("Dataset").glob("*/*__video.mp4")):
        videos.append((path.parent.name.replace("_", " "), str(path)))
    return videos


@lru_cache(maxsize=1)
def load_model(model_path: str):
    processor = AutoProcessor.from_pretrained(
        model_path,
        trust_remote_code=True,
        local_files_only=True,
        fix_mistral_regex=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        device_map="auto",
        trust_remote_code=True,
        local_files_only=True,
    )
    model.eval()
    return model, processor


def active_device(model) -> torch.device:
    return getattr(model, "device", next(model.parameters()).device)


def decode_new_tokens(processor, inputs, output) -> str:
    generated_ids = [o[len(i) :] for i, o in zip(inputs.input_ids, output)]
    return processor.batch_decode(
        generated_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0].strip()


def generate_text(prompt: str, max_new_tokens: int, enable_thinking: bool, model_path: str) -> str:
    if not prompt.strip():
        return "Please enter a prompt."
    model, processor = load_model(model_path)
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt.strip()}]}]
    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=enable_thinking,
    )
    inputs = processor(text=text, images=None, videos=None, do_resize=False, return_tensors="pt")
    inputs = inputs.to(active_device(model))
    started = time.time()
    with GENERATION_LOCK, torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=int(max_new_tokens), use_cache=True)
    return f"{decode_new_tokens(processor, inputs, output)}\n\n---\nElapsed: {time.time() - started:.2f}s"


def image_to_path(image) -> str | None:
    if image is None:
        return None
    if isinstance(image, str):
        return image
    if isinstance(image, dict):
        return image.get("path") or image.get("name")
    if isinstance(image, Image.Image):
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        image.save(tmp.name)
        return tmp.name
    return None


def generate_image(prompt: str, image, max_new_tokens: int, enable_thinking: bool, model_path: str) -> str:
    image_path = image_to_path(image)
    if not image_path:
        return "Please upload an image."
    if not prompt.strip():
        prompt = "Please describe this image in detail."
    model, processor = load_model(model_path)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image_path},
                {"type": "text", "text": prompt.strip()},
            ],
        }
    ]
    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=enable_thinking,
    )
    images, _, _ = process_vision_info(
        messages,
        image_patch_size=16,
        return_video_kwargs=True,
        return_video_metadata=True,
    )
    inputs = processor(text=text, images=images, videos=None, do_resize=False, return_tensors="pt")
    inputs = inputs.to(active_device(model))
    started = time.time()
    with GENERATION_LOCK, torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=int(max_new_tokens), use_cache=True)
    return f"{decode_new_tokens(processor, inputs, output)}\n\n---\nElapsed: {time.time() - started:.2f}s"


def resolve_video_path(uploaded_video: str | None, dataset_video: str | None) -> str | None:
    if uploaded_video:
        if isinstance(uploaded_video, dict):
            return uploaded_video.get("path") or uploaded_video.get("video") or uploaded_video.get("name")
        if isinstance(uploaded_video, (list, tuple)) and uploaded_video:
            return str(uploaded_video[0])
        return uploaded_video
    if dataset_video:
        return dataset_video
    return None


def generate_video(
    prompt: str,
    uploaded_video: str | None,
    dataset_video: str | None,
    fps: float,
    min_frames: int,
    max_frames: int,
    max_new_tokens: int,
    model_path: str,
) -> str:
    video_path = resolve_video_path(uploaded_video, dataset_video)
    if not video_path:
        return "Please upload a video or select one from the dataset."
    if not prompt.strip():
        prompt = "Please describe this video in detail."
    model, processor = load_model(model_path)
    processor.video_processor.size = {
        "longest_edge": int(BASE_PIXELS * max(1, int(max_frames))),
        "shortest_edge": int(BASE_PIXELS * max(1, int(min_frames))),
    }
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "video", "video": video_path, "fps": float(fps)},
                {"type": "text", "text": prompt.strip()},
            ],
        }
    ]
    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        fps=float(fps),
        return_tensors="pt",
    )
    inputs = inputs.to(active_device(model))
    started = time.time()
    with GENERATION_LOCK, torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=int(max_new_tokens), use_cache=True)
    return f"{decode_new_tokens(processor, inputs, output)}\n\n---\nElapsed: {time.time() - started:.2f}s"


def build_demo(model_path: str, eager_load: bool = False) -> gr.Blocks:
    dataset_videos = available_dataset_videos()
    if eager_load:
        load_model(model_path)

    with gr.Blocks(title="InternVideo3 OmniCourse Demo") as demo:
        gr.Markdown(
            "# InternVideo3 OmniCourse Demo\n"
            f"Local checkpoint: `{model_path}`\n\n"
            "Use the tabs below for text-only, image, and video understanding."
        )
        model_path_box = gr.Textbox(value=model_path, label="Model path", interactive=False)

        with gr.Tab("Text"):
            text_prompt = gr.Textbox(
                label="Prompt",
                value="Please introduce yourself in one sentence.",
                lines=4,
            )
            text_tokens = gr.Slider(16, 1024, value=128, step=16, label="Max new tokens")
            text_thinking = gr.Checkbox(value=True, label="Enable thinking")
            text_button = gr.Button("Generate")
            text_output = gr.Textbox(label="Response", lines=12)
            text_button.click(
                generate_text,
                inputs=[text_prompt, text_tokens, text_thinking, model_path_box],
                outputs=text_output,
            )

        with gr.Tab("Image"):
            image_input = gr.Image(label="Image", type="pil")
            image_prompt = gr.Textbox(
                label="Prompt",
                value="Please describe this image in detail.",
                lines=3,
            )
            image_tokens = gr.Slider(16, 1024, value=256, step=16, label="Max new tokens")
            image_thinking = gr.Checkbox(value=True, label="Enable thinking")
            image_button = gr.Button("Analyze image")
            image_output = gr.Textbox(label="Response", lines=14)
            image_button.click(
                generate_image,
                inputs=[image_prompt, image_input, image_tokens, image_thinking, model_path_box],
                outputs=image_output,
            )

        with gr.Tab("Video"):
            dataset_dropdown = gr.Dropdown(
                choices=dataset_videos,
                value=dataset_videos[0][1] if dataset_videos else None,
                label="Dataset video",
            )
            video_input = gr.Video(label="Optional uploaded video")
            video_prompt = gr.Textbox(
                label="Prompt",
                value="Please describe this lecture video segment in detail.",
                lines=3,
            )
            with gr.Row():
                fps = gr.Slider(0.1, 4.0, value=0.5, step=0.1, label="Sampling FPS")
                min_frames = gr.Slider(1, 64, value=4, step=1, label="Min frames")
                max_frames = gr.Slider(8, 512, value=64, step=8, label="Max frames")
            video_tokens = gr.Slider(16, 1024, value=256, step=16, label="Max new tokens")
            video_button = gr.Button("Analyze video")
            video_output = gr.Textbox(label="Response", lines=14)
            video_button.click(
                generate_video,
                inputs=[
                    video_prompt,
                    video_input,
                    dataset_dropdown,
                    fps,
                    min_frames,
                    max_frames,
                    video_tokens,
                    model_path_box,
                ],
                outputs=video_output,
            )

    return demo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--server-name", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    parser.add_argument("--eager-load", action="store_true")
    args = parser.parse_args()

    demo = build_demo(args.model_path, eager_load=args.eager_load)
    demo.queue(max_size=8, default_concurrency_limit=1)
    demo.launch(
        server_name=args.server_name,
        server_port=args.server_port,
        share=args.share,
        show_error=True,
    )


if __name__ == "__main__":
    main()
