from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from PIL import Image


def encode_images(paths: list[str], model_name: str, pretrained: str, device: str, batch_size: int) -> dict[str, Any]:
    import torch
    import open_clip

    started = time.time()
    active_device = "cuda" if device in {"auto", "cuda"} and torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
    model = model.eval().to(active_device)
    embeddings: dict[str, list[float]] = {}
    valid_paths: list[str] = []
    tensors = []
    for path in paths:
        try:
            image = Image.open(path).convert("RGB")
            tensors.append(preprocess(image))
            valid_paths.append(path)
        except Exception:
            continue
        if len(tensors) >= batch_size:
            embeddings.update(_flush(model, tensors, valid_paths, active_device))
            tensors, valid_paths = [], []
    if tensors:
        embeddings.update(_flush(model, tensors, valid_paths, active_device))
    return {
        "provider": "open_clip",
        "model": model_name,
        "pretrained": pretrained,
        "device": active_device,
        "dimension": len(next(iter(embeddings.values()))) if embeddings else 0,
        "count": len(embeddings),
        "elapsed": round(time.time() - started, 2),
        "embeddings": embeddings,
    }


def _flush(model, tensors, paths, device: str) -> dict[str, list[float]]:
    import torch

    batch = torch.stack(tensors, dim=0).to(device)
    with torch.no_grad():
        vectors = model.encode_image(batch)
        vectors = vectors / vectors.norm(dim=-1, keepdim=True)
    return {path: vector.detach().cpu().numpy().round(6).tolist() for path, vector in zip(paths, vectors)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", help="JSON list of image paths.")
    parser.add_argument("--image-path", help="Single image path.")
    parser.add_argument("--output-json")
    parser.add_argument("--model", default="ViT-B-32")
    parser.add_argument("--pretrained", default="laion2b_s34b_b79k")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    if args.input_json:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        paths = payload if isinstance(payload, list) else payload.get("image_paths", [])
    elif args.image_path:
        paths = [args.image_path]
    else:
        raise SystemExit("--input-json or --image-path is required")
    result = encode_images([str(path) for path in paths], args.model, args.pretrained, args.device, args.batch_size)
    output = json.dumps(result, ensure_ascii=False)
    if args.output_json:
        Path(args.output_json).write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
