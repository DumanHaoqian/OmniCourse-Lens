from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from PIL import Image

from .deepseek_ocr_service import DeepSeekOCRService


class OCRService:
    def __init__(self) -> None:
        self.deepseek = DeepSeekOCRService()

    def describe_provider(self) -> dict[str, Any]:
        return {
            "deepseek": self.deepseek.describe_provider(),
            "pytesseract_available": importlib.util.find_spec("pytesseract") is not None,
            "paddleocr_available": importlib.util.find_spec("paddleocr") is not None,
            "easyocr_available": importlib.util.find_spec("easyocr") is not None,
            "fallback": "demo_filename_and_image_metadata",
        }

    def ocr_image(self, image_path: str, timestamp: float | None = None) -> dict[str, Any]:
        deepseek_result = self.deepseek.ocr_image(image_path)
        if deepseek_result.get("text"):
            return deepseek_result
        tesseract = self._try_tesseract(image_path)
        if tesseract.get("text"):
            return tesseract
        return self._demo_fallback(image_path, timestamp)

    def ocr_images(self, image_paths: list[str]) -> list[dict[str, Any]]:
        return [self.ocr_image(path) for path in image_paths]

    def _try_tesseract(self, image_path: str) -> dict[str, Any]:
        if importlib.util.find_spec("pytesseract") is None:
            return {"provider": "tesseract", "text": "", "blocks": [], "raw": {"available": False}}
        try:
            import pytesseract

            text = pytesseract.image_to_string(Image.open(image_path)).strip()
            return {
                "provider": "tesseract",
                "text": text,
                "blocks": [{"text": text, "confidence": None}] if text else [],
                "raw": {},
            }
        except Exception as exc:
            return {
                "provider": "tesseract",
                "text": "",
                "blocks": [],
                "raw": {"error": type(exc).__name__, "message": str(exc)[:300]},
            }

    def _demo_fallback(self, image_path: str, timestamp: float | None) -> dict[str, Any]:
        stem = Path(image_path).stem.replace("_", " ")
        text = f"Visual frame OCR fallback: {stem}"
        return {
            "provider": "demo_ocr",
            "text": text,
            "blocks": [
                {
                    "text": text,
                    "bbox": None,
                    "confidence": 0.35,
                    "frame_path": image_path,
                    "timestamp": timestamp,
                }
            ],
            "raw": {"fallback": True},
        }
