from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def measure(name: str, fn: Callable[[], Any], runs: int = 6) -> dict[str, Any]:
    timings = []
    last: Any = None
    for _ in range(runs):
        started = perf_counter()
        last = fn()
        timings.append((perf_counter() - started) * 1000)
    return {
        "name": name,
        "runs": runs,
        "mean_ms": round(statistics.mean(timings), 2),
        "median_ms": round(statistics.median(timings), 2),
        "max_ms": round(max(timings), 2),
        "last_status": getattr(last, "status_code", None),
    }


def main() -> int:
    os.environ.setdefault("INTERNVIDEO3_LOCAL_RERANK_TOP_N", "0")
    os.environ.setdefault("OMNICOURSE_ENABLE_QUERY_DENSE", "false")
    os.environ.setdefault("OMNICOURSE_IMAGE_QUERY_ALLOW_HEAVY_OCR", "false")

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    videos = client.get("/api/dataset/videos").json()
    if not videos:
        raise SystemExit("No Dataset videos discovered.")
    video = next((item for item in videos if "optimization" in item["relative_path"]), videos[0])
    video_id = video["video_id"]

    report = {
        "video_count": len(videos),
        "tested_video_id": video_id,
        "checks": [
            measure("health_cached", lambda: client.get("/api/health")),
            measure("dataset_videos_cached", lambda: client.get("/api/dataset/videos")),
            measure("subtitles_cached", lambda: client.get(f"/api/dataset/videos/{video_id}/subtitles")),
            measure(
                "text_search_current_video",
                lambda: client.post(
                    "/api/search/text",
                    json={
                        "course_id": "real_i2ml",
                        "query": "gradient descent update rule learning rate",
                        "video_ids": [video_id],
                        "top_k": 5,
                    },
                ),
                runs=4,
            ),
        ],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
