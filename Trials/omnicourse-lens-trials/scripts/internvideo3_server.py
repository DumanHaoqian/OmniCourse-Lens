from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from internvideo3_score import score


class ScoreRequest(BaseModel):
    query: str
    video_path: str
    start_time: float
    end_time: float
    fps: float = 0.25
    max_frames: int = 8
    max_new_tokens: int = 96


def create_app(model_path: str) -> FastAPI:
    app = FastAPI(title="InternVideo3 Local Scoring Server")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "model_path": model_path, "model_exists": Path(model_path).exists()}

    @app.post("/score")
    def score_clip(request: ScoreRequest) -> dict[str, Any]:
        namespace = argparse.Namespace(
            model_path=model_path,
            video_path=request.video_path,
            query=request.query,
            start_time=request.start_time,
            end_time=request.end_time,
            fps=request.fps,
            max_frames=request.max_frames,
            max_new_tokens=request.max_new_tokens,
        )
        return score(namespace)

    return app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()
    uvicorn.run(create_app(args.model_path), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
