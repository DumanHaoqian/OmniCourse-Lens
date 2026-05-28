from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.services.deepseek_ocr_service import DeepSeekOCRService  # noqa: E402
from app.services.math_ocr_service import MathOCRService  # noqa: E402
from app.storage import read_json, write_json  # noqa: E402


CONCEPTS = [
    "gradient descent",
    "learning rate",
    "normal equation",
    "linear regression",
    "mean squared error",
    "loss function",
    "chain rule",
    "backpropagation",
    "neural network",
    "activation function",
    "optimization",
    "risk minimization",
    "local minimum",
    "empirical risk",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh real course frame OCR with DeepSeek-OCR.")
    parser.add_argument("--course-id", default="real_i2ml")
    parser.add_argument("--lecture-id", default=None)
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of unique frames to OCR.")
    parser.add_argument("--force", action="store_true", help="Ignore cached OCR JSON files.")
    parser.add_argument("--rebuild-index", action="store_true")
    args = parser.parse_args()

    course_path = settings.courses_dir / f"{args.course_id}.json"
    course = read_json(course_path)
    if not course:
        raise SystemExit(f"Course not found: {course_path}")

    deepseek = DeepSeekOCRService()
    math_ocr = MathOCRService()
    status = deepseek.describe_provider()
    print(json.dumps({"deepseek_ocr": status}, indent=2))
    if not status.get("available"):
        raise SystemExit("DeepSeek-OCR is not available; cannot refresh real OCR.")

    cache_dir = settings.generated_dir / "ocr" / "deepseek"
    cache_dir.mkdir(parents=True, exist_ok=True)

    frame_cache: dict[str, dict[str, Any]] = {}
    processed = 0
    updated_moments = 0
    started = time.time()

    for lecture in course.get("lectures", []):
        if args.lecture_id and lecture.get("lecture_id") != args.lecture_id:
            continue
        for moment in lecture.get("moments", []):
            deepseek_blocks: list[dict[str, Any]] = []
            deepseek_formulas: list[dict[str, Any]] = []
            for frame in moment.get("keyframes", []) or []:
                frame_path = Path(frame)
                if not frame_path.exists():
                    continue
                cache_key = _cache_key(frame_path)
                if cache_key not in frame_cache:
                    if args.limit and processed >= args.limit:
                        continue
                    cache_path = cache_dir / f"{cache_key}.json"
                    if cache_path.exists() and not args.force:
                        result = read_json(cache_path, {})
                    else:
                        print(f"[deepseek-ocr] {processed + 1}: {frame_path}")
                        result = deepseek.ocr_image(str(frame_path))
                        write_json(cache_path, result)
                    frame_cache[cache_key] = result
                    processed += 1
                result = frame_cache[cache_key]
                text = (result.get("text") or "").strip()
                if not text:
                    continue
                timestamp = _frame_timestamp(frame_path, moment)
                deepseek_blocks.append(
                    {
                        "text": text,
                        "bbox": None,
                        "confidence": None,
                        "provider": "deepseek_ocr",
                        "frame_path": str(frame_path),
                        "timestamp": timestamp,
                    }
                )
                for formula in math_ocr.extract_formula_blocks(text, frame_path=str(frame_path), timestamp=timestamp):
                    formula["provider"] = "deepseek_ocr_formula_heuristic"
                    deepseek_formulas.append(formula)

            if not deepseek_blocks and not deepseek_formulas:
                continue
            existing_ocr = [block for block in moment.get("ocr_blocks", []) if block.get("provider") != "deepseek_ocr"]
            existing_formula = [
                block
                for block in moment.get("formula_blocks", [])
                if block.get("provider") != "deepseek_ocr_formula_heuristic"
            ]
            moment["ocr_blocks"] = existing_ocr + deepseek_blocks
            moment["formula_blocks"] = _dedupe_formula_blocks(existing_formula + deepseek_formulas)
            moment["ocr_text"] = _dedupe_join([*(block.get("text", "") for block in moment["ocr_blocks"])])
            moment["formula_latex"] = _dedupe_join([*(block.get("latex", "") for block in moment["formula_blocks"])], sep="; ")
            moment["concept_tags"] = _merge_concepts(moment.get("concept_tags", []), moment)
            moment.setdefault("metadata", {})["deepseek_ocr_refreshed_at"] = int(started)
            updated_moments += 1

    write_json(course_path, course)
    summary = {
        "course_id": args.course_id,
        "lecture_id": args.lecture_id,
        "provider": status,
        "unique_frames_processed_or_loaded": processed,
        "updated_moments": updated_moments,
        "elapsed_seconds": round(time.time() - started, 2),
    }
    log_path = settings.generated_dir / "evals" / f"ocr_refresh_{args.course_id}_{int(started)}.json"
    write_json(log_path, summary)
    print(json.dumps(summary, indent=2))

    if args.rebuild_index:
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "rebuild_index.py")], check=True)


def _cache_key(frame_path: Path) -> str:
    stat = frame_path.stat()
    raw = f"{frame_path.resolve()}:{stat.st_mtime_ns}:{stat.st_size}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _frame_timestamp(frame_path: Path, moment: dict[str, Any]) -> float:
    match = re.search(r"frame_(\d+(?:\.\d+)?)", frame_path.stem)
    if match:
        return float(match.group(1))
    start = float(moment.get("start_time") or 0.0)
    end = float(moment.get("end_time") or start)
    return round((start + end) / 2.0, 2)


def _dedupe_join(values: list[str], sep: str = "\n") -> str:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return sep.join(out)


def _dedupe_formula_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for block in blocks:
        latex = re.sub(r"\s+", " ", str(block.get("latex") or "")).strip()
        if not latex:
            continue
        key = latex.lower()
        if key in seen:
            continue
        seen.add(key)
        block["latex"] = latex
        deduped.append(block)
    return deduped[:12]


def _merge_concepts(existing: list[str], moment: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            moment.get("transcript", ""),
            moment.get("ocr_text", ""),
            moment.get("formula_latex", ""),
            moment.get("visual_caption", ""),
        ]
    ).lower()
    merged = []
    for concept in [*existing, *CONCEPTS]:
        normalized = str(concept).strip().lower()
        if not normalized:
            continue
        if normalized in text or normalized in {str(item).lower() for item in existing}:
            if normalized not in merged:
                merged.append(normalized)
    return merged[:10]


if __name__ == "__main__":
    main()
