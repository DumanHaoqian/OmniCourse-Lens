from __future__ import annotations

import json
import math
import sys
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


def main() -> None:
    ensure_directories()
    courses = [course.model_dump(mode="json") for course in list_courses()]
    moments: list[dict[str, Any]] = []
    docs: list[list[str]] = []
    image_descriptors: dict[str, list[float]] = {}
    for course in courses:
        for lecture in course.get("lectures", []):
            for moment in lecture.get("moments", []):
                record = {
                    **moment,
                    "lecture_title": lecture.get("title", ""),
                    "video_path": lecture.get("video_path"),
                }
                moments.append(record)
                docs.append(tokenize(moment_document(moment, lecture)))
                for frame in moment.get("keyframes", []):
                    image_descriptors[frame] = image_descriptor(frame)

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

    metadata = {
        "courses": [course["course_id"] for course in courses],
        "moment_count": len(moments),
        "image_descriptor_count": len(image_descriptors),
        "providers": {
            "text_index": "json_tfidf",
            "image_descriptor": "pil_color_histogram",
            "video_embedding": "optional_internvideo3_or_disabled",
        },
    }
    write_json(settings.indexes_dir / "moments.json", moments)
    write_json(settings.indexes_dir / "lexical_index.json", {"idf": idf, "docs": sparse_docs, "inverted": inverted})
    write_json(settings.indexes_dir / "image_descriptors.json", image_descriptors)
    write_json(settings.indexes_dir / "metadata.json", metadata)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
