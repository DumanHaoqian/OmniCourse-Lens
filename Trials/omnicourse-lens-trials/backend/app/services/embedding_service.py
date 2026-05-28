from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def normalize_text(text: str) -> str:
    replacements = {
        "θ": " theta ",
        "α": " alpha learning rate ",
        "∇": " gradient ",
        "ᵀ": " transpose ",
        "λ": " lambda ",
        "σ": " sigmoid activation ",
        "ℓ": " loss ",
        "≤": " <= ",
        "≥": " >= ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.lower()


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(normalize_text(text)) if len(token) > 1]


class EmbeddingService:
    def describe_provider(self) -> dict[str, Any]:
        return {
            "text_embedding": "json_tfidf_or_token_overlap_fallback",
            "image_embedding": "pil_color_histogram_fallback",
            "heavy_models_loaded": False,
        }

    def text_sparse_vector(self, text: str, idf: dict[str, float] | None = None) -> dict[str, float]:
        counts = Counter(tokenize(text))
        if not counts:
            return {}
        vector = {}
        for term, count in counts.items():
            vector[term] = (1.0 + math.log(count)) * (idf or {}).get(term, 1.0)
        return vector

    def sparse_cosine(self, left: dict[str, float], right: dict[str, float]) -> float:
        if not left or not right:
            return 0.0
        dot = sum(value * right.get(term, 0.0) for term, value in left.items())
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if not left_norm or not right_norm:
            return 0.0
        return max(0.0, min(1.0, dot / (left_norm * right_norm)))

    def lexical_relevance(self, query: str, document: str) -> float:
        query_tokens = tokenize(query)
        doc_tokens = tokenize(document)
        if not query_tokens or not doc_tokens:
            return 0.0
        doc_counts = Counter(doc_tokens)
        overlap = sum(min(1, doc_counts.get(token, 0)) for token in set(query_tokens))
        score = overlap / max(len(set(query_tokens)), 1)
        phrase_bonus = 0.25 if normalize_text(query).strip() and normalize_text(query).strip() in normalize_text(document) else 0.0
        return max(0.0, min(1.0, score + phrase_bonus))

    def image_descriptor(self, path: str | Path) -> list[float]:
        try:
            img = Image.open(path).convert("RGB").resize((64, 64))
        except Exception:
            return [0.0] * 54
        arr = np.asarray(img, dtype=np.float32) / 255.0
        features: list[float] = []
        features.extend(arr.mean(axis=(0, 1)).tolist())
        features.extend(arr.std(axis=(0, 1)).tolist())
        for channel in range(3):
            hist, _ = np.histogram(arr[:, :, channel], bins=16, range=(0, 1), density=True)
            features.extend(hist.tolist())
        vec = np.asarray(features, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm:
            vec = vec / norm
        return vec.round(6).tolist()

    def vector_similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        a = np.asarray(left, dtype=np.float32)
        b = np.asarray(right, dtype=np.float32)
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if not denom:
            return 0.0
        return max(0.0, min(1.0, float(np.dot(a, b) / denom)))

    def load_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
