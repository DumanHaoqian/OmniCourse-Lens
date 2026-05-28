from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


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
