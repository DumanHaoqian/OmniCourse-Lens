from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import importlib.util
import json
import os
import re
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

from ..config import settings


class DeepSeekOCRService:
    """DeepSeek-OCR provider with HTTP and lazy local HuggingFace modes.

    The official `deepseek-ai/DeepSeek-OCR` model is a Transformers custom-code
    model whose local API is `model.infer(tokenizer, image_file=...)`. Loading it
    at FastAPI startup would be slow and use GPU memory, so this service reports
    local availability from disk but loads the model only when OCR is requested.
    """

    def __init__(self) -> None:
        self.endpoint = os.getenv("DEEPSEEK_OCR_ENDPOINT", "").strip()
        self.api_key = os.getenv("DEEPSEEK_OCR_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        self.model = os.getenv("DEEPSEEK_OCR_MODEL", "deepseek-ai/DeepSeek-OCR")
        configured_model_path = os.getenv("DEEPSEEK_OCR_MODEL_PATH", "").strip()
        self.model_path = Path(configured_model_path).expanduser() if configured_model_path else settings.legacy_deepseek_ocr_path
        if not self.model_path.is_absolute():
            self.model_path = (settings.project_root / self.model_path).resolve()
        self.prompt = os.getenv("DEEPSEEK_OCR_PROMPT", "<image>\n<|grounding|>Convert the document to markdown. ")
        self.base_size = int(os.getenv("DEEPSEEK_OCR_BASE_SIZE", "1024"))
        self.image_size = int(os.getenv("DEEPSEEK_OCR_IMAGE_SIZE", "640"))
        self.crop_mode = os.getenv("DEEPSEEK_OCR_CROP_MODE", "true").lower() not in {"0", "false", "no"}
        self.attention = os.getenv("DEEPSEEK_OCR_ATTN", "eager")
        self.allow_cpu = os.getenv("DEEPSEEK_OCR_ALLOW_CPU", "false").lower() in {"1", "true", "yes"}
        self.cache_dir = settings.generated_dir / "ocr" / "deepseek_cache"
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return bool((self.endpoint and self.api_key) or self._local_checkpoint_ready())

    def describe_provider(self) -> dict[str, Any]:
        if self.endpoint and self.api_key:
            mode = "http"
            reason = None
        elif self._local_checkpoint_ready():
            mode = "local_hf_lazy"
            reason = None
        elif self.model_path.exists():
            mode = "local_incomplete"
            reason = "DeepSeek-OCR folder exists but model safetensors are still missing or incomplete."
        else:
            mode = "disabled"
            reason = "No DEEPSEEK_OCR_ENDPOINT and no local DeepSeek-OCR checkpoint found."
        return {
            "provider": "deepseek_ocr",
            "available": self.is_available(),
            "mode": mode,
            "endpoint_configured": bool(self.endpoint),
            "api_key_present": bool(self.api_key),
            "api_key_suffix": self.api_key[-4:] if self.api_key else None,
            "model": self.model,
            "model_path": str(self.model_path) if self.model_path.exists() else None,
            "model_path_present": self.model_path.exists(),
            "local_checkpoint_ready": self._local_checkpoint_ready(),
            "dependencies": self._dependency_status(),
            "cache_dir": str(self.cache_dir),
            "cpu_fallback_enabled": self.allow_cpu,
            "reason": reason,
        }

    def ocr_image(self, image_path: str, allow_heavy: bool = True) -> dict[str, Any]:
        if not self.is_available():
            return {"provider": "deepseek_ocr", "text": "", "blocks": [], "raw": {"disabled": True, "status": self.describe_provider()}}
        cached = self._read_cache(Path(image_path))
        if cached:
            cached.setdefault("raw", {})["cache_hit"] = True
            return cached
        if self.endpoint and self.api_key:
            result = self._ocr_http(Path(image_path))
        elif allow_heavy:
            result = self._ocr_local(Path(image_path))
        else:
            result = {
                "provider": "deepseek_ocr",
                "text": "",
                "blocks": [],
                "raw": {
                    "mode": "local_hf_lazy",
                    "skipped": True,
                    "reason": "Heavy local DeepSeek-OCR was skipped for an interactive request; ingest jobs can run it offline.",
                },
            }
        if result.get("text"):
            self._write_cache(Path(image_path), result)
        return result

    def ocr_images(self, image_paths: list[str], allow_heavy: bool = True) -> list[dict[str, Any]]:
        return [self.ocr_image(path, allow_heavy=allow_heavy) for path in image_paths]

    def _ocr_http(self, image_path: Path) -> dict[str, Any]:
        try:
            data = base64.b64encode(image_path.read_bytes()).decode("ascii")
            response = requests.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "image": data},
                timeout=90,
            )
            response.raise_for_status()
            raw = response.json()
            text = raw.get("text") or raw.get("content") or ""
            blocks = raw.get("blocks") or ([{"text": text, "confidence": raw.get("confidence")}] if text else [])
            return {"provider": "deepseek_ocr", "text": text, "blocks": blocks, "raw": raw}
        except Exception as exc:
            return self._error("http", exc)

    def _ocr_local(self, image_path: Path) -> dict[str, Any]:
        try:
            if not self._cuda_available() and not self.allow_cpu:
                return {
                    "provider": "deepseek_ocr",
                    "text": "",
                    "blocks": [],
                    "raw": {
                        "mode": "local_hf_lazy",
                        "skipped": True,
                        "reason": "CUDA is unavailable and DEEPSEEK_OCR_ALLOW_CPU is not enabled.",
                    },
                }
            started = time.time()
            model, tokenizer = self._load_local()
            with tempfile.TemporaryDirectory(prefix="deepseek_ocr_") as output_dir:
                with self._lock:
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        returned = model.infer(
                            tokenizer,
                            prompt=self.prompt,
                            image_file=str(image_path),
                            output_path=output_dir,
                            base_size=self.base_size,
                            image_size=self.image_size,
                            crop_mode=self.crop_mode,
                            save_results=False,
                            test_compress=True,
                        )
            text = self._clean_local_output(str(returned or stdout.getvalue() or "").strip())
            return {
                "provider": "deepseek_ocr",
                "text": text,
                "blocks": [{"text": text, "bbox": None, "confidence": None, "provider": "deepseek_ocr", "frame_path": str(image_path)}] if text else [],
                "raw": {"mode": "local_hf_lazy", "model_path": str(self.model_path), "elapsed_sec": round(time.time() - started, 3)},
            }
        except Exception as exc:
            return self._error("local_hf_lazy", exc)

    @lru_cache(maxsize=1)
    def _load_local(self):
        import torch
        from transformers import AutoModel, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(str(self.model_path), trust_remote_code=True, local_files_only=True)
        kwargs: dict[str, Any] = {
            "trust_remote_code": True,
            "use_safetensors": True,
            "local_files_only": True,
        }
        if self.attention == "flash_attention_2":
            kwargs["_attn_implementation"] = "flash_attention_2"
        elif self.attention in {"sdpa", "eager"}:
            kwargs["_attn_implementation"] = self.attention
        model = AutoModel.from_pretrained(str(self.model_path), **kwargs)
        model = model.eval()
        if torch.cuda.is_available():
            model = model.cuda().to(torch.bfloat16)
        return model, tokenizer

    def _cuda_available(self) -> bool:
        try:
            import torch

            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def _cache_key(self, image_path: Path) -> str | None:
        try:
            digest = hashlib.sha1()
            digest.update(image_path.read_bytes())
            digest.update(str(self.model_path).encode("utf-8", errors="ignore"))
            digest.update(self.prompt.encode("utf-8", errors="ignore"))
            return digest.hexdigest()
        except Exception:
            return None

    def _read_cache(self, image_path: Path) -> dict[str, Any] | None:
        key = self._cache_key(image_path)
        if not key:
            return None
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _write_cache(self, image_path: Path, result: dict[str, Any]) -> None:
        key = self._cache_key(image_path)
        if not key:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cacheable = json.loads(json.dumps(result, default=str))
            cacheable.setdefault("raw", {})["cache_hit"] = False
            (self.cache_dir / f"{key}.json").write_text(json.dumps(cacheable, indent=2), encoding="utf-8")
        except Exception:
            return

    def _local_checkpoint_ready(self) -> bool:
        if not self.model_path.exists():
            return False
        has_index = (self.model_path / "model.safetensors.index.json").exists() or (self.model_path / "model.safetensors").exists()
        has_weight = any(self.model_path.glob("*.safetensors"))
        has_incomplete = any((self.model_path / ".cache" / "huggingface" / "download").glob("*.incomplete")) if (self.model_path / ".cache").exists() else False
        return has_index and has_weight and not has_incomplete

    def _dependency_status(self) -> dict[str, bool]:
        return {
            "torch": importlib.util.find_spec("torch") is not None,
            "transformers": importlib.util.find_spec("transformers") is not None,
            "einops": importlib.util.find_spec("einops") is not None,
            "addict": importlib.util.find_spec("addict") is not None,
            "easydict": importlib.util.find_spec("easydict") is not None,
        }

    def _clean_local_output(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<\|det\|>.*?<\|/det\|>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<\|/?ref\|>", " ", text)
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                lines.append("")
                continue
            if stripped.startswith("=") or stripped.startswith("BASE:") or stripped.startswith("NO PATCHES"):
                continue
            if stripped.startswith("image size:") or stripped.startswith("valid image tokens:") or stripped.startswith("output texts tokens"):
                continue
            if stripped.startswith("compression ratio:"):
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def _error(self, mode: str, exc: Exception) -> dict[str, Any]:
        return {
            "provider": "deepseek_ocr",
            "text": "",
            "blocks": [],
            "raw": {"mode": mode, "error": type(exc).__name__, "message": str(exc)[:700]},
        }
