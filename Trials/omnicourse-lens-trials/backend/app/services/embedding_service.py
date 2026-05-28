from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..config import settings


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
    def __init__(self) -> None:
        self.text_model = os.getenv("OMNICOURSE_TEXT_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.embed_python = os.getenv("OMNICOURSE_EMBED_PYTHON", "/home/haoqian/miniconda3/envs/omniC/bin/python")
        self.cache_dir = Path(os.getenv("OMNICOURSE_EMBED_MODEL_DIR", str(settings.repo_root / "Trials" / "checkpoints" / "embeddings"))).expanduser()
        self.runner = settings.project_root / "scripts" / "embed_text.py"
        self.image_model = os.getenv("OMNICOURSE_IMAGE_EMBED_MODEL", "ViT-B-32")
        self.image_pretrained = os.getenv("OMNICOURSE_IMAGE_EMBED_PRETRAINED", "laion2b_s34b_b79k")
        self.image_runner = settings.project_root / "scripts" / "embed_image.py"

    def describe_provider(self) -> dict[str, Any]:
        return {
            "text_embedding": "sentence_transformers" if self._runner_ready() else "unavailable",
            "text_model": self.text_model,
            "runner": str(self.runner) if self.runner.exists() else None,
            "runner_python": self.embed_python if Path(self.embed_python).exists() else None,
            "model_cache": str(self.cache_dir),
            "online_query_dense_enabled": os.getenv("OMNICOURSE_ENABLE_QUERY_DENSE", "false").lower() in {"1", "true", "yes"},
            "image_embedding": "open_clip" if self._image_runner_ready() else "unavailable",
            "image_model": self.image_model,
            "image_pretrained": self.image_pretrained,
            "image_runner": str(self.image_runner) if self.image_runner.exists() else None,
            "interactive_image_timeout_sec": int(os.getenv("OMNICOURSE_IMAGE_EMBED_TIMEOUT", "12")),
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
        open_clip_embedding = self.image_embedding(path)
        if open_clip_embedding:
            return open_clip_embedding
        return self.image_color_descriptor(path)

    def image_color_descriptor(self, path: str | Path) -> list[float]:
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

    def dense_text_embedding(self, text: str) -> list[float]:
        if not self._runner_ready():
            return []
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        command = [
            self.embed_python if Path(self.embed_python).exists() else sys.executable,
            str(self.runner),
            "--text",
            text,
            "--model",
            self.text_model,
            "--cache-dir",
            str(self.cache_dir),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=int(os.getenv("OMNICOURSE_EMBED_TIMEOUT", "180")))
            payload = json.loads((result.stdout or "").strip().splitlines()[-1])
            embeddings = payload.get("embeddings") or []
            return embeddings[0] if embeddings else []
        except Exception:
            return []

    def dense_similarity(self, left: list[float], right: list[float]) -> float:
        return self.vector_similarity(left, right)

    def image_embedding(self, path: str | Path) -> list[float]:
        if not self._image_runner_ready():
            return []
        command = [
            self.embed_python if Path(self.embed_python).exists() else sys.executable,
            str(self.image_runner),
            "--image-path",
            str(path),
            "--model",
            self.image_model,
            "--pretrained",
            self.image_pretrained,
            "--device",
            os.getenv("OMNICOURSE_IMAGE_EMBED_DEVICE", "auto"),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=int(os.getenv("OMNICOURSE_IMAGE_EMBED_TIMEOUT", "12")))
            if result.returncode != 0:
                return []
            payload = json.loads((result.stdout or "").strip().splitlines()[-1])
            embeddings = payload.get("embeddings") or {}
            return embeddings.get(str(path), [])
        except Exception:
            return []

    def _runner_ready(self) -> bool:
        return self.runner.exists() and (Path(self.embed_python).exists() or sys.executable)

    def _image_runner_ready(self) -> bool:
        return self.image_runner.exists() and (Path(self.embed_python).exists() or sys.executable)

    def load_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
