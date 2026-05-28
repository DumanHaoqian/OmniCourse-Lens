from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from functools import lru_cache
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoProcessor


BASE_PIXELS = 128 * 32 * 32


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
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        attn_implementation="sdpa",
        device_map="auto" if torch.cuda.is_available() else None,
        trust_remote_code=True,
        local_files_only=True,
    )
    model.eval()
    return model, processor


def active_device(model):
    return getattr(model, "device", next(model.parameters()).device)


def temporary_clip(video_path: str, start_time: float, end_time: float) -> Path:
    source = Path(video_path)
    if not source.exists():
        raise FileNotFoundError(video_path)
    duration = max(2.0, min(120.0, float(end_time) - float(start_time)))
    tmp = tempfile.NamedTemporaryFile(suffix=source.suffix or ".mp4", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    import subprocess

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(max(0.0, float(start_time))),
        "-t",
        str(duration),
        "-i",
        str(source),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "30",
        str(tmp_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if result.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        return source
    return tmp_path


def decode(processor, inputs, output) -> str:
    generated_ids = [out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, output)]
    return processor.batch_decode(generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0].strip()


def parse_score(text: str) -> dict:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if "score" in data:
                data["score"] = max(0.0, min(1.0, float(data["score"])))
                return data
        except Exception:
            pass
    numbers = [float(item) for item in re.findall(r"\b(?:0(?:\.\d+)?|1(?:\.0+)?)\b", text)]
    return {"score": numbers[0] if numbers else None, "reason": text[:220]}


def score(args: argparse.Namespace) -> dict:
    model, processor = load_model(args.model_path)
    clip = temporary_clip(args.video_path, args.start_time, args.end_time)
    try:
        if hasattr(processor, "video_processor"):
            processor.video_processor.size = {
                "longest_edge": int(BASE_PIXELS * max(1, args.max_frames)),
                "shortest_edge": int(BASE_PIXELS * 4),
            }
        prompt = (
            "You are reranking lecture video moments for a multimodal video search engine. "
            "Watch the provided sampled clip and decide how relevant it is to the query. "
            "Return strict JSON only: {\"score\": 0.0 to 1.0, \"reason\": \"short phrase\"}. "
            f"Query: {args.query}\nCandidate time window: {args.start_time:.1f}s to {args.end_time:.1f}s."
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "video", "video": str(clip), "fps": args.fps},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        inputs = processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            fps=args.fps,
            return_tensors="pt",
        )
        inputs = inputs.to(active_device(model))
        started = time.time()
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=args.max_new_tokens, use_cache=True)
        text = decode(processor, inputs, output)
        data = parse_score(text)
        data.update({"raw_text": text, "elapsed": round(time.time() - started, 2), "mode": "local_subprocess"})
        return data
    finally:
        if clip != Path(args.video_path):
            clip.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--video-path", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--start-time", type=float, required=True)
    parser.add_argument("--end-time", type=float, required=True)
    parser.add_argument("--fps", type=float, default=0.25)
    parser.add_argument("--max-frames", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    args = parser.parse_args()
    try:
        print(json.dumps(score(args), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"score": None, "error": type(exc).__name__, "message": str(exc)[:1000]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
