from __future__ import annotations

import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("INTERNVIDEO3_LOCAL_RERANK_TOP_N", "0")
os.environ.setdefault("OMNICOURSE_IMAGE_EMBED_TIMEOUT", "8")
os.environ.setdefault("OMNICOURSE_IMAGE_QUERY_ALLOW_HEAVY_OCR", "false")


def test_health_and_search() -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    videos = client.get("/api/dataset/videos").json()
    assert len(videos) >= 9
    optimization = next(video for video in videos if "optimization" in video["relative_path"])
    response = client.post(
        "/api/search/text",
        json={"course_id": "real_i2ml", "query": "gradient descent", "video_ids": [optimization["video_id"]], "top_k": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["results"]
    assert data["results"][0]["video_id"] == optimization["video_id"]
    assert data["results"][0]["score_breakdown"]
    subtitles = client.get(f"/api/dataset/videos/{optimization['video_id']}/subtitles")
    assert subtitles.status_code == 200
    subtitle_json = subtitles.json()
    assert subtitle_json["audio_cue_count"] > 0
    assert subtitle_json["ocr_cue_count"] > 0
    vtt = client.get(f"/api/dataset/videos/{optimization['video_id']}/subtitles.vtt")
    assert vtt.status_code == 200
    assert vtt.text.startswith("WEBVTT")
    non_optimization = next(video for video in videos if video["video_id"] != optimization["video_id"])
    fallback = client.post(
        "/api/search/text",
        json={"course_id": "real_i2ml", "query": "gradient descent update rule learning rate", "video_ids": [non_optimization["video_id"]], "top_k": 2},
    )
    assert fallback.status_code == 200
    fallback_json = fallback.json()
    assert fallback_json["scope_notice"]
    assert fallback_json["results"][0]["video_id"] == optimization["video_id"]
