from __future__ import annotations

import importlib.util
import re
from typing import Any


DISPLAY_MATH_RE = re.compile(r"\\\[(.*?)\\\]|\\\((.*?)\\\)", re.DOTALL)
MATH_SIGNAL_RE = re.compile(
    r"(\\(?:theta|alpha|beta|lambda|nabla|frac|sum|arg|mathcal|text|hat|partial|leq|geq)|"
    r"[θΘαβλ∇∂≤≥]|"
    r"\barg\s*min\b|\barg\s*max\b|\bmin_\b|\bmax_\b|"
    r"\bR_?\{?\\?text\{?emp\}?|"
    r"[A-Za-z0-9_\]\)]\s*(?::=|=|≤|>=|<=|\\leq|\\geq)\s*[^=])",
    re.IGNORECASE,
)
NOISE_RE = re.compile(
    r"^(sub_title|text|image|table|learning goals|understand |know concept|for now you can|this concept can|"
    r"design choice|slide \d+|©|introduction to machine learning)\b",
    re.IGNORECASE,
)


class MathOCRService:
    def describe_provider(self) -> dict[str, Any]:
        return {
            "pix2text_available": importlib.util.find_spec("pix2text") is not None,
            "mathpix_configured": False,
            "fallback": "formula_text_heuristic",
        }

    def extract_formula_blocks(self, ocr_text: str, frame_path: str | None = None, timestamp: float | None = None) -> list[dict[str, Any]]:
        formulas = self.extract_formulas(ocr_text)
        return [
            {
                "latex": formula,
                "source_frame": frame_path,
                "confidence": 0.68 if formula.startswith("\\[") or formula.startswith("\\(") else 0.52,
                "timestamp": timestamp,
                "provider": "heuristic_math_ocr",
            }
            for formula in formulas[:8]
        ]

    def extract_formulas(self, text: str) -> list[str]:
        candidates: list[str] = []
        for match in DISPLAY_MATH_RE.finditer(text or ""):
            raw = match.group(0).strip()
            if raw:
                candidates.append(raw)
        for line in re.split(r"[\n;]", text or ""):
            stripped = self._clean_candidate(line)
            if not stripped:
                continue
            if self._looks_like_formula(stripped):
                candidates.append(stripped)
        return self._dedupe(candidates)

    def clean_formula_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cleaned: list[dict[str, Any]] = []
        for block in blocks:
            latex = self._clean_candidate(str(block.get("latex") or ""))
            if not latex or not self._looks_like_formula(latex):
                continue
            next_block = dict(block)
            next_block["latex"] = latex
            next_block["confidence"] = max(float(next_block.get("confidence") or 0.5), 0.55)
            cleaned.append(next_block)
        return self._dedupe_blocks(cleaned)

    def _looks_like_formula(self, text: str) -> bool:
        has_display_block = "\\[" in text and "\\]" in text
        if has_display_block and len(text) <= 420:
            return True
        lowered = text.lower()
        if any(noise in lowered for noise in ["slide ", "©", "introduction to machine learning", "learning goals", "understand "]):
            return False
        if re.match(r"^(for |does not |continuous params|definition of|neg\.? gradient|hessian|image|text)\b", text, flags=re.IGNORECASE):
            return False
        if len(text) > 260:
            return False
        if NOISE_RE.search(text):
            return False
        if "<table" in text.lower() or "</table>" in text.lower():
            return False
        has_relation = bool(re.search(r"(:=|=|≤|≥|<|>|\\leq|\\geq|\\approx|\\to|arg\s*min|arg\s*max|\\nabla|∇|∂)", text, re.IGNORECASE))
        has_math_symbol = bool(re.search(r"(\\[A-Za-z]+|[θΘαβλ∇∂]|R_\{?\\?text|Remp|J\()", text))
        return has_relation and has_math_symbol and bool(MATH_SIGNAL_RE.search(text))

    def _clean_candidate(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        text = re.sub(r"^(equation|formula)\s+", "", text, flags=re.IGNORECASE).strip()
        text = text.strip(" -•·")
        return text

    def _dedupe(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = re.sub(r"\s+", " ", item).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out[:12]

    def _dedupe_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for block in blocks:
            key = re.sub(r"\s+", " ", str(block.get("latex") or "")).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(block)
        return out[:12]
