from __future__ import annotations

import importlib.util
import re
from typing import Any


FORMULA_HINTS = [
    r"theta",
    r"alpha",
    r"\\",
    r"=",
    r"gradient",
    r"loss",
    r"frac",
    r"sum",
    r"ReLU",
    r"max",
]


class MathOCRService:
    def describe_provider(self) -> dict[str, Any]:
        return {
            "pix2text_available": importlib.util.find_spec("pix2text") is not None,
            "mathpix_configured": False,
            "fallback": "formula_text_heuristic",
        }

    def extract_formula_blocks(self, ocr_text: str, frame_path: str | None = None, timestamp: float | None = None) -> list[dict[str, Any]]:
        formulas: list[str] = []
        for line in re.split(r"[\n.;]", ocr_text):
            stripped = line.strip()
            if not stripped:
                continue
            if any(hint.lower() in stripped.lower() for hint in FORMULA_HINTS):
                formulas.append(stripped)
        return [
            {
                "latex": formula,
                "source_frame": frame_path,
                "confidence": 0.45,
                "timestamp": timestamp,
                "provider": "heuristic_math_ocr",
            }
            for formula in formulas[:5]
        ]
