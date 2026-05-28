from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.video_ingest import VideoIngestService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--course-id", required=True)
    parser.add_argument("--lecture-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--transcript-file")
    parser.add_argument("--frame-interval", type=float, default=10.0)
    parser.add_argument("--window-sec", type=float, default=20.0)
    args = parser.parse_args()

    service = VideoIngestService()
    course = service.ingest_video(
        video_path=args.video,
        course_id=args.course_id,
        lecture_id=args.lecture_id,
        title=args.title,
        transcript_file=args.transcript_file,
        frame_interval=args.frame_interval,
        window_sec=args.window_sec,
    )
    lecture = next(lec for lec in course.lectures if lec.lecture_id == args.lecture_id)
    print(f"Ingested {course.course_id}/{lecture.lecture_id}: {len(lecture.moments)} moments")
    print(service.describe_provider())


if __name__ == "__main__":
    main()
