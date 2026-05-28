from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.services.math_ocr_service import MathOCRService  # noqa: E402
from app.storage import read_json, write_json  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean noisy formula OCR blocks in a course JSON.")
    parser.add_argument("--course-id", default="real_i2ml")
    parser.add_argument("--rebuild-index", action="store_true")
    args = parser.parse_args()

    path = settings.courses_dir / f"{args.course_id}.json"
    course = read_json(path)
    if not course:
        raise SystemExit(f"Course not found: {path}")

    math_ocr = MathOCRService()
    before = 0
    after = 0
    changed = 0
    for lecture in course.get("lectures", []):
        for moment in lecture.get("moments", []):
            blocks = moment.get("formula_blocks", []) or []
            before += len(blocks)
            cleaned = math_ocr.clean_formula_blocks(blocks)
            if len(cleaned) != len(blocks) or [b.get("latex") for b in cleaned] != [b.get("latex") for b in blocks]:
                changed += 1
            moment["formula_blocks"] = cleaned
            moment["formula_latex"] = "; ".join(block.get("latex", "") for block in cleaned if block.get("latex"))
            after += len(cleaned)

    write_json(path, course)
    summary = {
        "course_id": args.course_id,
        "formula_blocks_before": before,
        "formula_blocks_after": after,
        "moments_changed": changed,
        "updated_at": int(time.time()),
    }
    log_path = settings.generated_dir / "evals" / f"formula_clean_{args.course_id}_{summary['updated_at']}.json"
    write_json(log_path, summary)
    print(json.dumps(summary, indent=2))

    if args.rebuild_index:
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "rebuild_index.py")], check=True)


if __name__ == "__main__":
    main()
