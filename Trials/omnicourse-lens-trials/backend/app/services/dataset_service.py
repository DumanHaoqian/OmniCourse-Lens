from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from ..config import ensure_directories, settings
from ..storage import course_path, load_course, read_json, static_url, write_json
from .video_ingest import VideoIngestService


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
REAL_COURSE_ID = "real_i2ml"
JOBS: dict[str, dict[str, Any]] = {}


class DatasetService:
    def __init__(self) -> None:
        ensure_directories()
        self.dataset_root = settings.dataset_dir.resolve()
        self.status_path = settings.indexes_dir / "dataset_status.json"

    def list_videos(self) -> list[dict[str, Any]]:
        status = read_json(self.status_path, {})
        videos = []
        for path in sorted(self.dataset_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            rel = path.resolve().relative_to(self.dataset_root).as_posix()
            video_id = self.video_id_for_path(path)
            item_status = status.get(video_id, {})
            thumbnail = self._thumbnail_for(video_id)
            videos.append(
                {
                    "video_id": video_id,
                    "filename": path.name,
                    "absolute_path": str(path),
                    "relative_path": rel,
                    "size": path.stat().st_size,
                    "duration": item_status.get("duration") or self._probe_duration(path),
                    "ingestion_status": item_status.get("ingestion_status", "not_ingested"),
                    "indexed_status": item_status.get("indexed_status", "unknown"),
                    "thumbnail": thumbnail,
                    "title": self.title_for_path(path),
                    "course_id": item_status.get("course_id", REAL_COURSE_ID),
                    "lecture_id": item_status.get("lecture_id", self.lecture_id_for_path(path)),
                    "slides_path": str(self.find_slides(path)) if self.find_slides(path) else None,
                }
            )
        return videos

    def ingest_video(
        self,
        video_id: str | None = None,
        video_path: str | None = None,
        course_id: str | None = None,
        lecture_id: str | None = None,
        title: str | None = None,
        force_reingest: bool = False,
        frame_interval: float = 120.0,
        window_sec: float = 120.0,
    ) -> dict[str, Any]:
        path = self.resolve_video(video_id=video_id, video_path=video_path)
        resolved_id = self.video_id_for_path(path)
        course_id = course_id or REAL_COURSE_ID
        lecture_id = lecture_id or self.lecture_id_for_path(path)
        title = title or self.title_for_path(path)
        status = read_json(self.status_path, {})
        if not force_reingest and status.get(resolved_id, {}).get("ingestion_status") == "ingested":
            return {"video_id": resolved_id, "status": "already_ingested", **status[resolved_id]}
        slides = self.find_slides(path)
        slide_text = self.extract_pdf_text(slides) if slides else ""
        course = VideoIngestService().ingest_video(
            video_path=str(path),
            course_id=course_id,
            lecture_id=lecture_id,
            title=title,
            transcript_file=None,
            frame_interval=frame_interval,
            window_sec=window_sec,
            supplemental_text=slide_text,
            video_id=resolved_id,
            source_metadata={
                "dataset_root": str(self.dataset_root),
                "dataset_relative_path": path.relative_to(self.dataset_root).as_posix(),
                "slides_path": str(slides) if slides else None,
                "source": "real_dataset",
            },
        )
        lecture = next(lecture for lecture in course.lectures if lecture.lecture_id == lecture_id)
        status[resolved_id] = {
            "video_id": resolved_id,
            "video_path": str(path),
            "course_id": course_id,
            "lecture_id": lecture_id,
            "title": title,
            "duration": lecture.duration,
            "ingestion_status": "ingested",
            "indexed_status": "stale",
            "moment_count": len(lecture.moments),
            "thumbnail": lecture.moments[0].thumbnail_url if lecture.moments else None,
            "slides_path": str(slides) if slides else None,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        write_json(self.status_path, status)
        return {"video_id": resolved_id, "status": "ingested", **status[resolved_id]}

    def ingest_all(self, limit: int | None = None, force_reingest: bool = False) -> dict[str, Any]:
        videos = self.list_videos()[:limit] if limit else self.list_videos()
        results = []
        for video in videos:
            results.append(
                self.ingest_video(
                    video_id=video["video_id"],
                    force_reingest=force_reingest,
                    frame_interval=120.0,
                    window_sec=120.0,
                )
            )
        self.rebuild_index()
        return {"count": len(results), "results": results}

    def start_ingest_all_job(self, force_reingest: bool = False, limit: int | None = None) -> dict[str, Any]:
        job_id = f"ingest_{int(time.time())}_{hashlib.sha1(str(time.time()).encode()).hexdigest()[:8]}"
        JOBS[job_id] = {"job_id": job_id, "status": "queued", "progress": 0, "message": "Queued", "results": []}

        def worker() -> None:
            try:
                videos = self.list_videos()[:limit] if limit else self.list_videos()
                JOBS[job_id].update({"status": "running", "total": len(videos), "message": "Ingesting dataset videos"})
                for idx, video in enumerate(videos, start=1):
                    result = self.ingest_video(video_id=video["video_id"], force_reingest=force_reingest)
                    JOBS[job_id]["results"].append(result)
                    JOBS[job_id]["progress"] = idx / max(len(videos), 1)
                    JOBS[job_id]["message"] = f"Ingested {idx}/{len(videos)}"
                self.rebuild_index()
                JOBS[job_id].update({"status": "completed", "progress": 1.0, "message": "Completed"})
            except Exception as exc:
                JOBS[job_id].update({"status": "failed", "message": str(exc)[:500]})

        threading.Thread(target=worker, daemon=True).start()
        return JOBS[job_id]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return JOBS.get(job_id)

    def mark_indexed(self) -> None:
        status = read_json(self.status_path, {})
        for item in status.values():
            if item.get("ingestion_status") == "ingested":
                item["indexed_status"] = "indexed"
        write_json(self.status_path, status)

    def rebuild_index(self) -> dict[str, Any]:
        script = settings.project_root / "scripts" / "rebuild_index.py"
        result = subprocess.run([sys.executable, str(script)], cwd=settings.project_root, capture_output=True, text=True)
        if result.returncode == 0:
            self.mark_indexed()
        return {"returncode": result.returncode, "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]}

    def resolve_video(self, video_id: str | None = None, video_path: str | None = None) -> Path:
        if video_path:
            path = Path(video_path).expanduser().resolve()
            self._assert_inside_dataset(path)
            return path
        if not video_id:
            raise FileNotFoundError("video_id or video_path is required")
        for video in self.list_videos():
            if video["video_id"] == video_id:
                return Path(video["absolute_path"]).resolve()
        raise FileNotFoundError(f"Dataset video not found: {video_id}")

    def video_id_for_path(self, path: Path) -> str:
        rel = path.resolve().relative_to(self.dataset_root).as_posix()
        prefix = re.sub(r"[^a-zA-Z0-9]+", "_", path.parent.name.lower()).strip("_")
        digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:10]
        return f"{prefix}_{digest}"

    def lecture_id_for_path(self, path: Path) -> str:
        stem = path.parent.name or path.stem
        return re.sub(r"[^a-zA-Z0-9]+", "_", stem.lower()).strip("_")[:80]

    def title_for_path(self, path: Path) -> str:
        title = path.parent.name
        title = re.sub(r"^\d+_", "", title)
        return title.replace("_", " ").title()

    def find_slides(self, video_path: Path) -> Path | None:
        candidates = sorted(video_path.parent.glob("*.pdf"))
        return candidates[0] if candidates else None

    def extract_pdf_text(self, pdf_path: Path | None) -> str:
        if not pdf_path or not pdf_path.exists():
            return ""
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(pdf_path))
            chunks = []
            for idx, page in enumerate(reader.pages[:80]):
                text = page.extract_text() or ""
                if text.strip():
                    chunks.append(f"Slide {idx + 1}: {text.strip()}")
            return "\n\n".join(chunks)
        except Exception:
            return ""

    def _probe_duration(self, path: Path) -> float | None:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            return round(float(result.stdout.strip()), 3)
        except Exception:
            return None

    def _thumbnail_for(self, video_id: str) -> str | None:
        if course_path(REAL_COURSE_ID).exists():
            try:
                course = load_course(REAL_COURSE_ID)
                for lecture in course.lectures:
                    if lecture.metadata.get("video_id") == video_id and lecture.moments:
                        return lecture.moments[0].thumbnail_url
            except Exception:
                return None
        return None

    def _assert_inside_dataset(self, path: Path) -> None:
        path.resolve().relative_to(self.dataset_root)
