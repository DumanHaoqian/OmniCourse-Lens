from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import ensure_directories, settings  # noqa: E402
from app.storage import list_courses, write_json  # noqa: E402


def tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in "".join(ch if ch.isalnum() else " " for ch in text).split()
        if len(token) > 2
    ]


def image_descriptor(path: str) -> list[float]:
    try:
        img = Image.open(path).convert("RGB").resize((64, 64))
    except Exception:
        return [0.0] * 64
    arr = np.asarray(img, dtype=np.float32) / 255.0
    channel_means = arr.mean(axis=(0, 1)).tolist()
    channel_stds = arr.std(axis=(0, 1)).tolist()
    hist = []
    for channel in range(3):
        values, _ = np.histogram(arr[:, :, channel], bins=16, range=(0, 1), density=True)
        hist.extend(values.tolist())
    vec = np.array([*channel_means, *channel_stds, *hist], dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm:
        vec = vec / norm
    return vec.round(6).tolist()


def moment_document(moment: dict[str, Any], lecture: dict[str, Any]) -> str:
    parts = [
        lecture.get("title", ""),
        moment.get("transcript", ""),
        moment.get("ocr_text", ""),
        moment.get("formula_latex", ""),
        moment.get("visual_caption", ""),
        " ".join(moment.get("concept_tags", [])),
    ]
    return "\n".join(parts)


def build_dense_embeddings(texts: list[str]) -> dict[str, Any]:
    runner = ROOT / "scripts" / "embed_text.py"
    python = os.getenv("OMNICOURSE_EMBED_PYTHON", "/home/haoqian/miniconda3/envs/omniC/bin/python")
    model = os.getenv("OMNICOURSE_TEXT_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    cache_dir = Path(os.getenv("OMNICOURSE_EMBED_MODEL_DIR", str(settings.repo_root / "Trials" / "checkpoints" / "embeddings"))).expanduser()
    if not runner.exists():
        return {"provider": "unavailable", "model": model, "embeddings": [], "error": "embed_text.py missing"}
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as src:
        json.dump(texts, src, ensure_ascii=False)
        input_path = Path(src.name)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as dst:
        output_path = Path(dst.name)
    try:
        command = [
            python if Path(python).exists() else sys.executable,
            str(runner),
            "--input-json",
            str(input_path),
            "--output-json",
            str(output_path),
            "--model",
            model,
            "--cache-dir",
            str(cache_dir),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=int(os.getenv("OMNICOURSE_EMBED_INDEX_TIMEOUT", "900")))
        if result.returncode != 0:
            return {
                "provider": "unavailable",
                "model": model,
                "embeddings": [],
                "error": result.stderr[-1000:] or result.stdout[-1000:],
            }
        return json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"provider": "unavailable", "model": model, "embeddings": [], "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    finally:
        input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


def build_image_embeddings(image_paths: list[str]) -> dict[str, Any]:
    runner = ROOT / "scripts" / "embed_image.py"
    python = os.getenv("OMNICOURSE_EMBED_PYTHON", "/home/haoqian/miniconda3/envs/omniC/bin/python")
    model = os.getenv("OMNICOURSE_IMAGE_EMBED_MODEL", "ViT-B-32")
    pretrained = os.getenv("OMNICOURSE_IMAGE_EMBED_PRETRAINED", "laion2b_s34b_b79k")
    device = os.getenv("OMNICOURSE_IMAGE_EMBED_DEVICE", "auto")
    if os.getenv("OMNICOURSE_ENABLE_OPEN_CLIP_INDEX", "false").lower() not in {"1", "true", "yes"}:
        return {
            "provider": "pil_color_histogram",
            "model": model,
            "pretrained": pretrained,
            "embeddings": {},
            "error": "OpenCLIP indexing skipped; set OMNICOURSE_ENABLE_OPEN_CLIP_INDEX=true for heavy offline image embeddings.",
        }
    if not runner.exists():
        return {"provider": "unavailable", "model": model, "embeddings": {}, "error": "embed_image.py missing"}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as src:
        json.dump(image_paths, src, ensure_ascii=False)
        input_path = Path(src.name)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as dst:
        output_path = Path(dst.name)
    try:
        command = [
            python if Path(python).exists() else sys.executable,
            str(runner),
            "--input-json",
            str(input_path),
            "--output-json",
            str(output_path),
            "--model",
            model,
            "--pretrained",
            pretrained,
            "--device",
            device,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=int(os.getenv("OMNICOURSE_IMAGE_EMBED_INDEX_TIMEOUT", "120")))
        if result.returncode != 0:
            return {
                "provider": "unavailable",
                "model": model,
                "pretrained": pretrained,
                "embeddings": {},
                "error": result.stderr[-1000:] or result.stdout[-1000:],
            }
        return json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"provider": "unavailable", "model": model, "pretrained": pretrained, "embeddings": {}, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    finally:
        input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


def main() -> None:
    ensure_directories()
    courses = [course.model_dump(mode="json") for course in list_courses()]
    moments: list[dict[str, Any]] = []
    docs: list[list[str]] = []
    dense_texts: list[str] = []
    image_descriptors: dict[str, list[float]] = {}
    all_frame_paths: list[str] = []
    for course in courses:
        for lecture in course.get("lectures", []):
            for moment in lecture.get("moments", []):
                record = {
                    **moment,
                    "lecture_title": lecture.get("title", ""),
                    "video_path": lecture.get("video_path"),
                    "video_id": moment.get("video_id") or moment.get("metadata", {}).get("video_id") or lecture.get("metadata", {}).get("video_id"),
                }
                moments.append(record)
                document = moment_document(moment, lecture)
                dense_texts.append(document)
                docs.append(tokenize(document))
                for frame in moment.get("keyframes", []):
                    if frame:
                        all_frame_paths.append(frame)

    document_frequency: Counter[str] = Counter()
    for tokens in docs:
        document_frequency.update(set(tokens))
    n_docs = max(len(docs), 1)
    vocabulary = sorted(document_frequency)
    idf = {
        term: math.log((1 + n_docs) / (1 + document_frequency[term])) + 1.0
        for term in vocabulary
    }
    sparse_docs = []
    inverted: dict[str, list[dict[str, float]]] = defaultdict(list)
    for idx, tokens in enumerate(docs):
        counts = Counter(tokens)
        weights = {}
        for term, count in counts.items():
            weight = (1 + math.log(count)) * idf.get(term, 1.0)
            weights[term] = round(weight, 6)
            inverted[term].append({"moment_index": idx, "weight": round(weight, 6)})
        sparse_docs.append(weights)

    dense_payload = build_dense_embeddings(dense_texts)
    dense_embeddings = dense_payload.get("embeddings", []) if dense_payload.get("provider") == "sentence_transformers" else []
    unique_frames = sorted(set(all_frame_paths))
    image_payload = build_image_embeddings(unique_frames)
    if image_payload.get("provider") == "open_clip":
        image_descriptors = image_payload.get("embeddings", {})
    else:
        image_descriptors = {frame: image_descriptor(frame) for frame in unique_frames}
    metadata = {
        "courses": [course["course_id"] for course in courses],
        "moment_count": len(moments),
        "image_descriptor_count": len(image_descriptors),
        "providers": {
            "text_index": "json_tfidf",
            "image_descriptor": {
                "provider": image_payload.get("provider") or "pil_color_histogram",
                "model": image_payload.get("model"),
                "pretrained": image_payload.get("pretrained"),
                "dimension": image_payload.get("dimension"),
                "count": image_payload.get("count") or len(image_descriptors),
                "error": image_payload.get("error"),
            },
            "dense_text_embedding": {
                "provider": dense_payload.get("provider"),
                "model": dense_payload.get("model"),
                "dimension": dense_payload.get("dimension"),
                "count": dense_payload.get("count"),
                "error": dense_payload.get("error"),
            },
            "video_embedding": "optional_internvideo3_or_disabled",
        },
    }
    write_json(settings.indexes_dir / "moments.json", moments)
    write_json(settings.indexes_dir / "lexical_index.json", {"idf": idf, "docs": sparse_docs, "inverted": inverted})
    write_json(settings.indexes_dir / "image_descriptors.json", image_descriptors)
    write_json(settings.indexes_dir / "dense_text_embeddings.json", dense_embeddings)
    write_json(settings.indexes_dir / "metadata.json", metadata)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
