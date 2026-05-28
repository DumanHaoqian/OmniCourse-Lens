from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.schemas import ASRSegment  # noqa: E402
from app.services.audio_asr_service import AudioASRService  # noqa: E402
from app.storage import load_course, save_course  # noqa: E402


def overlap_segments(segments: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [
        segment
        for segment in segments
        if float(segment.get("end_time", 0.0)) >= start and float(segment.get("start_time", 0.0)) <= end
    ]


def refresh(course_id: str, lecture_id: str | None, rebuild_index: bool) -> dict[str, Any]:
    course = load_course(course_id)
    asr = AudioASRService()
    summary: dict[str, Any] = {
        "course_id": course_id,
        "provider": asr.describe_provider(),
        "lectures": [],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    for lecture in course.lectures:
        if lecture_id and lecture.lecture_id != lecture_id:
            continue
        audio_path = lecture.metadata.get("audio_path") or str(settings.audio_dir / f"{lecture.course_id}_{lecture.lecture_id}.wav")
        if not audio_path or not Path(audio_path).exists():
            summary["lectures"].append({"lecture_id": lecture.lecture_id, "status": "missing_audio", "audio_path": audio_path})
            continue
        segments = asr.transcribe(audio_path, duration=lecture.duration, title=lecture.title)
        if not segments or all(segment.get("provider") == "fallback_asr" for segment in segments):
            summary["lectures"].append({"lecture_id": lecture.lecture_id, "status": "asr_failed_or_fallback", "audio_path": audio_path})
            continue
        provider_counts = Counter(str(segment.get("provider")) for segment in segments)
        for moment in lecture.moments:
            overlapping = overlap_segments(segments, moment.start_time, moment.end_time)
            moment.asr_segments = [ASRSegment.model_validate(segment) for segment in overlapping]
            moment.transcript = " ".join(segment.get("text", "") for segment in overlapping).strip()
            moment.metadata["asr_refreshed"] = True
            moment.metadata["asr_provider_counts"] = dict(provider_counts)
        lecture.metadata["asr_refreshed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        lecture.metadata["asr_provider_counts"] = dict(provider_counts)
        summary["lectures"].append(
            {
                "lecture_id": lecture.lecture_id,
                "status": "refreshed",
                "segment_count": len(segments),
                "provider_counts": dict(provider_counts),
                "sample": segments[0]["text"][:180],
            }
        )
    save_course(course)
    summary["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if rebuild_index:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "rebuild_index.py")], cwd=ROOT, capture_output=True, text=True)
        summary["rebuild_index"] = {
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-2000:],
        }
    out_dir = settings.generated_dir / "evals"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"asr_refresh_{course_id}_{int(time.time())}.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["log_path"] = str(out_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-id", default="real_i2ml")
    parser.add_argument("--lecture-id")
    parser.add_argument("--rebuild-index", action="store_true")
    args = parser.parse_args()
    print(json.dumps(refresh(args.course_id, args.lecture_id, args.rebuild_index), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
