from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import requests


class DeepSeekOCRService:
    def __init__(self) -> None:
        self.endpoint = os.getenv("DEEPSEEK_OCR_ENDPOINT")
        self.api_key = os.getenv("DEEPSEEK_OCR_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        self.model = os.getenv("DEEPSEEK_OCR_MODEL", "deepseek-ocr")
        self.model_path = os.getenv("DEEPSEEK_OCR_MODEL_PATH")
        self.reason = "No DEEPSEEK_OCR_ENDPOINT / model path configured."

    def is_available(self) -> bool:
        return bool((self.endpoint and self.api_key) or self.model_path)

    def describe_provider(self) -> dict[str, Any]:
        mode = "http" if self.endpoint and self.api_key else "local_path" if self.model_path else "disabled"
        return {
            "provider": "deepseek_ocr",
            "available": self.is_available(),
            "mode": mode,
            "endpoint_configured": bool(self.endpoint),
            "api_key_present": bool(self.api_key),
            "api_key_suffix": self.api_key[-4:] if self.api_key else None,
            "model": self.model,
            "model_path_present": bool(self.model_path),
            "reason": None if self.is_available() else self.reason,
        }

    def ocr_image(self, image_path: str) -> dict[str, Any]:
        if not self.is_available():
            return {"provider": "deepseek_ocr", "text": "", "blocks": [], "raw": {"disabled": True}}
        if self.endpoint and self.api_key:
            return self._ocr_http(Path(image_path))
        return {
            "provider": "deepseek_ocr",
            "text": "",
            "blocks": [],
            "raw": {"mode": "local_path_not_loaded", "model_path": self.model_path},
        }

    def ocr_images(self, image_paths: list[str]) -> list[dict[str, Any]]:
        return [self.ocr_image(path) for path in image_paths]

    def _ocr_http(self, image_path: Path) -> dict[str, Any]:
        try:
            data = base64.b64encode(image_path.read_bytes()).decode("ascii")
            response = requests.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "image": data},
                timeout=60,
            )
            response.raise_for_status()
            raw = response.json()
            text = raw.get("text") or raw.get("content") or ""
            blocks = raw.get("blocks") or ([{"text": text, "confidence": raw.get("confidence")}] if text else [])
            return {"provider": "deepseek_ocr", "text": text, "blocks": blocks, "raw": raw}
        except Exception as exc:
            return {
                "provider": "deepseek_ocr",
                "text": "",
                "blocks": [],
                "raw": {"error": type(exc).__name__, "message": str(exc)[:500]},
            }
