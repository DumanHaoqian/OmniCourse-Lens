from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    run([sys.executable, "scripts/create_demo_data.py"])
    run([sys.executable, "scripts/rebuild_index.py"])

    try:
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.llm_service import LLMService
        from app.services.deepseek_ocr_service import DeepSeekOCRService
        from app.services.internvideo3_service import InternVideo3Service
        from app.services.ocr_service import OCRService
        from app.services.audio_asr_service import AudioASRService
    except ModuleNotFoundError as exc:
        raise SystemExit(f"Missing backend dependency: {exc}. Run: python -m pip install -r backend/requirements.txt") from exc

    client = TestClient(app)
    health = client.get("/api/health")
    assert_true(health.status_code == 200, "/api/health failed")
    health_json = health.json()

    courses = client.get("/api/courses")
    assert_true(courses.status_code == 200 and courses.json(), "/api/courses returned empty")

    gradient = client.post("/api/search/text", json={"course_id": "ml_foundations", "query": "gradient descent", "top_k": 3})
    assert_true(gradient.status_code == 200, "gradient descent search failed")
    gradient_json = gradient.json()
    assert_true(gradient_json["results"], "gradient descent search returned no results")
    assert_true("lec_02" == gradient_json["results"][0]["lecture_id"], "gradient descent top result should be lec_02")
    assert_true(gradient_json["results"][0]["score_breakdown"], "search result lacks score breakdown")
    assert_true(gradient_json.get("self_check"), "search result lacks self_check")

    normal = client.post("/api/search/text", json={"course_id": "ml_foundations", "query": "normal equation", "top_k": 3})
    assert_true(normal.status_code == 200, "normal equation search failed")
    assert_true(normal.json()["results"][0]["lecture_id"] == "lec_01", "normal equation top result should be lec_01")

    frame_path = ROOT / "backend/app/static/frames/ml_foundations/lec_02/01_gradient_descent.png"
    with frame_path.open("rb") as handle:
        image = client.post(
            "/api/search/image",
            data={"course_id": "ml_foundations", "query": "gradient descent", "top_k": "3"},
            files={"image": ("gradient.png", handle, "image/png")},
        )
    assert_true(image.status_code == 200, "image search failed")
    assert_true(image.json()["results"], "image search returned no results")

    cheatsheet = client.post(
        "/api/cheatsheet",
        json={"course_id": "ml_foundations", "lecture_ids": ["lec_01", "lec_02"], "focus_topics": "gradient descent normal equation", "max_pages": 2},
    )
    assert_true(cheatsheet.status_code == 200, "cheatsheet generation failed")
    cheatsheet_json = cheatsheet.json()
    assert_true("\\section*{Core Concepts}" in cheatsheet_json["tex_content"], "cheatsheet missing core concepts section")
    assert_true(cheatsheet_json["tex_file_url"].endswith(".tex"), "cheatsheet did not return tex file")
    assert_true(cheatsheet_json.get("self_check"), "cheatsheet lacks self_check")

    graph = client.post(
        "/api/knowledge-graph",
        json={"course_id": "ml_foundations", "lecture_ids": ["lec_01", "lec_02", "lec_03"]},
    )
    assert_true(graph.status_code == 200, "knowledge graph failed")
    graph_json = graph.json()
    assert_true(graph_json["nodes"] and graph_json["edges"], "knowledge graph returned empty graph")
    assert_true(graph_json.get("self_check"), "knowledge graph lacks self_check")

    qa = client.post(
        "/api/qa",
        json={"course_id": "ml_foundations", "question": "Why does gradient descent move opposite to the gradient?", "top_k": 3},
    )
    assert_true(qa.status_code == 200, "QA failed")
    qa_json = qa.json()
    assert_true(qa_json["answer"] and qa_json["evidence"], "QA response lacks answer or evidence")
    assert_true(qa_json.get("self_check"), "QA lacks self_check")

    llm = LLMService()
    llm_judge: dict[str, Any] | None = None
    if llm.is_available():
        llm_judge = llm.chat_json(
            "You are a strict product smoke-test judge. Return JSON only.",
            "Judge whether this demo is coherent from these passed checks: search, image search, cheatsheet, graph, QA.",
            max_tokens=500,
        )

    summary = {
        "passed": True,
        "checks": [
            "health",
            "courses",
            "text_search_gradient_descent",
            "text_search_normal_equation",
            "image_search_keyframe",
            "cheatsheet_generation",
            "knowledge_graph_generation",
            "qa_grounded_answer",
        ],
        "provider_status": {
            "gpt4o": llm.describe_provider(),
            "internvideo3": InternVideo3Service().describe_provider(),
            "deepseek_ocr": DeepSeekOCRService().describe_provider(),
            "asr": AudioASRService().describe_provider(),
            "ocr": OCRService().describe_provider(),
        },
        "api_health": health_json,
        "llm_product_judge": llm_judge,
    }
    out_dir = ROOT / "backend/app/data/generated/evals"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "smoke_test_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
