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
    response = client.post("/api/search/text", json={"course_id": "ml_foundations", "query": "gradient descent", "top_k": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["results"]
    assert data["results"][0]["lecture_id"] == "lec_02"
    assert data["results"][0]["score_breakdown"]
