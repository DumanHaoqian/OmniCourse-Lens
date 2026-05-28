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

    try:
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.audio_asr_service import AudioASRService
        from app.services.dataset_service import DatasetService
        from app.services.deepseek_ocr_service import DeepSeekOCRService
        from app.services.internvideo3_service import InternVideo3Service
        from app.services.llm_service import LLMService
        from app.services.ocr_service import OCRService
    except ModuleNotFoundError as exc:
        raise SystemExit(f"Missing backend dependency: {exc}. Run: python -m pip install -r backend/requirements.txt") from exc

    client = TestClient(app)
    health = client.get("/api/health")
    assert_true(health.status_code == 200, "/api/health failed")
    health_json = health.json()

    dataset = client.get("/api/dataset/videos")
    assert_true(dataset.status_code == 200, "/api/dataset/videos failed")
    videos = dataset.json()
    assert_true(len(videos) >= 9, f"Expected real Dataset videos, got {len(videos)}")
    optimization = next((video for video in videos if "optimization" in video["relative_path"]), videos[0])

    ingest = client.post("/api/dataset/ingest", json={"video_id": optimization["video_id"], "frame_interval": 180, "window_sec": 180})
    assert_true(ingest.status_code == 200, f"real dataset ingest failed: {ingest.text[:300]}")
    ingest_json = ingest.json()
    assert_true(ingest_json["result"]["status"] in {"ingested", "already_ingested"}, "real video was not ingested")

    rebuild = client.post("/api/index/rebuild")
    assert_true(rebuild.status_code == 200, "/api/index/rebuild failed")

    courses = client.get("/api/courses")
    assert_true(courses.status_code == 200 and courses.json(), "/api/courses returned empty")

    real_search = client.post(
        "/api/search/text",
        json={"course_id": "real_i2ml", "query": "gradient descent optimization", "video_ids": [optimization["video_id"]], "top_k": 3},
    )
    assert_true(real_search.status_code == 200, "real gradient descent search failed")
    real_search_json = real_search.json()
    assert_true(real_search_json["results"], "real search returned no results")
    assert_true(real_search_json["results"][0]["video_id"] == optimization["video_id"], "real search did not return selected Dataset video")
    assert_true(real_search_json["results"][0]["score_breakdown"], "real search lacks score breakdown")

    lecture_term = client.post(
        "/api/search/text",
        json={"course_id": "real_i2ml", "query": "risk function optimized learn optimal parameters", "video_ids": [optimization["video_id"]], "top_k": 3},
    )
    assert_true(lecture_term.status_code == 200 and lecture_term.json()["results"], "real lecture term search failed")

    frame_path = ROOT / "backend/app/static/frames/real_i2ml/08_i2ml_01_ml_basics_07_optimization/frame_00000.png"
    assert_true(frame_path.exists(), "real extracted keyframe missing")
    with frame_path.open("rb") as handle:
        image = client.post(
            "/api/search/image",
            data={"course_id": "real_i2ml", "query": "gradient descent optimization", "video_ids": optimization["video_id"], "top_k": "3"},
            files={"image": ("real_keyframe.png", handle, "image/png")},
        )
    assert_true(image.status_code == 200 and image.json()["results"], "real image search failed")

    qa = client.post(
        "/api/qa",
        json={
            "course_id": "real_i2ml",
            "question": "Why does gradient descent move opposite to the gradient?",
            "video_id": optimization["video_id"],
            "top_k": 3,
        },
    )
    assert_true(qa.status_code == 200, "real QA failed")
    qa_json = qa.json()
    assert_true(qa_json["answer"] and qa_json["evidence"], "real QA lacks answer/evidence")
    assert_true("\\[" in qa_json["answer"] or "\\(" in qa_json["answer"], "QA answer is not LaTeX-rendering friendly")

    cheatsheet = client.post(
        "/api/cheatsheet",
        json={
            "course_id": "real_i2ml",
            "lecture_ids": [optimization["lecture_id"]],
            "video_ids": [optimization["video_id"]],
            "focus_topics": "optimization gradient descent risk minimization",
            "max_pages": 2,
        },
    )
    assert_true(cheatsheet.status_code == 200, "real cheatsheet generation failed")
    cheatsheet_json = cheatsheet.json()
    assert_true(cheatsheet_json["tex_content"] and cheatsheet_json["tex_file_url"].endswith(".tex"), "cheatsheet lacks tex output")
    compile_result = client.post("/api/cheatsheet/compile", json={"tex_content": cheatsheet_json["tex_content"]})
    assert_true(compile_result.status_code == 200, "cheatsheet compile endpoint failed")
    assert_true("compile_error" in compile_result.json(), "compile endpoint did not report status")

    graph = client.post(
        "/api/knowledge-graph",
        json={
            "course_id": "real_i2ml",
            "lecture_ids": [optimization["lecture_id"]],
            "video_ids": [optimization["video_id"]],
            "focus_topic": "optimization",
            "max_concepts": 24,
            "include_moments": True,
        },
    )
    assert_true(graph.status_code == 200, "real knowledge graph failed")
    graph_json = graph.json()
    assert_true(graph_json["nodes"] and graph_json["edges"], "knowledge graph returned empty graph")
    assert_true(len(graph_json["nodes"]) <= 90 and len(graph_json["edges"]) <= 220, "graph is too dense for readable default UI")

    provider_status = client.get("/api/provider-status")
    assert_true(provider_status.status_code == 200, "provider status failed")

    llm = LLMService()
    llm_judge: dict[str, Any] | None = None
    if llm.is_available():
        llm_judge = llm.chat_json(
            "You are a strict evaluator for an evidence-grounded multimodal lecture demo. Return JSON only.",
            json.dumps(
                {
                    "real_dataset_videos": len(videos),
                    "real_search_top": real_search_json["results"][0],
                    "qa_answer": qa_json["answer"][:1500],
                    "graph_counts": {"nodes": len(graph_json["nodes"]), "edges": len(graph_json["edges"])},
                }
            ),
            max_tokens=600,
        )

    summary = {
        "passed": True,
        "checks": [
            "health",
            "dataset_videos",
            "real_video_ingest",
            "rebuild_index",
            "real_text_search_gradient_descent",
            "real_text_search_lecture_term",
            "real_image_search_keyframe",
            "qa_latex_answer",
            "cheatsheet_generation_and_compile_endpoint",
            "knowledge_graph_pruned",
            "provider_status",
        ],
        "real_dataset": {
            "video_count": len(videos),
            "tested_video": optimization,
            "ingest_result": ingest_json["result"],
        },
        "provider_status": {
            "gpt4o": llm.describe_provider(),
            "internvideo3": InternVideo3Service().describe_provider(),
            "deepseek_ocr": DeepSeekOCRService().describe_provider(),
            "asr": AudioASRService().describe_provider(),
            "ocr": OCRService().describe_provider(),
            "latex": health_json.get("providers", {}).get("latex"),
        },
        "llm_product_judge": llm_judge,
    }
    out_dir = ROOT / "backend/app/data/generated/evals"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "overnight_smoke_test_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
