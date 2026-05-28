from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoProcessor


@dataclass(frozen=True)
class TemporalPrediction:
    start_sec: float | None
    end_sec: float | None
    raw_text: str


def parse_seconds(text: str) -> tuple[float | None, float | None]:
    numbers = [float(x) for x in re.findall(r"\b\d+(?:\.\d+)?\b", text)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return None, None


class InternVideo3TemporalGrounder:
    """Small adapter for evaluating InternVideo3-style temporal grounding.

    The public GitHub README currently points to an OpenGVLab model id that is
    not discoverable through the Hugging Face API. The reachable checkpoint used
    here is `yanziang/InternVideo3-8B-Instruct`, which is about 18.7 GB.
    """

    def __init__(self, model_id: str = "yanziang/InternVideo3-8B-Instruct") -> None:
        self.model_id = model_id
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            dtype=torch.bfloat16,
            attn_implementation="sdpa",
            device_map="auto",
            trust_remote_code=True,
        )
        self.processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

    def predict(self, video_path: Path, query: str, fps: float = 0.5, max_new_tokens: int = 128) -> TemporalPrediction:
        prompt = (
            "Find the moment in this lecture video that best answers the query. "
            "Return only JSON like {\"start_sec\": 12.0, \"end_sec\": 35.0}. "
            f"Query: {query}"
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "video", "video": str(video_path), "fps": fps},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            fps=fps,
            return_tensors="pt",
        )
        inputs = inputs.to(self.model.device)
        with torch.inference_mode():
            output = self.model.generate(**inputs, max_new_tokens=max_new_tokens, use_cache=True)
        generated = [o[len(i) :] for i, o in zip(inputs.input_ids, output)]
        text = self.processor.batch_decode(generated, skip_special_tokens=True)[0]
        try:
            data = json.loads(text)
            return TemporalPrediction(float(data.get("start_sec")), float(data.get("end_sec")), text)
        except Exception:
            start, end = parse_seconds(text)
            return TemporalPrediction(start, end, text)
