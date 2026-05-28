from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import requests

from ..config import settings


class InternVideo3Service:
    """Lazy adapter for optional InternVideo3 retrieval signals.

    The local checkpoint exists in the parent Trials workspace, but the backend
    pins Transformers for DeepSeek-OCR compatibility. To avoid dependency
    conflicts and startup GPU allocation, local InternVideo3 scoring runs through
    a small subprocess in the `omniC` environment only when reranking is needed.
    """

    def __init__(self) -> None:
        self.endpoint = os.getenv("INTERNVIDEO3_ENDPOINT", "").strip()
        self.cli = os.getenv("INTERNVIDEO3_CLI", "").strip()
        configured_model_path = os.getenv("INTERNVIDEO3_MODEL_PATH", "").strip()
        self.model_path = Path(configured_model_path).expanduser() if configured_model_path else settings.legacy_internvideo3_path
        if not self.model_path.is_absolute():
            self.model_path = (settings.project_root / self.model_path).resolve()
        self.local_enabled = os.getenv("INTERNVIDEO3_ENABLE_LOCAL", "1").lower() in {"1", "true", "yes"}
        self.local_search_rerank = os.getenv("INTERNVIDEO3_LOCAL_RERANK", "1").lower() in {"1", "true", "yes"}
        self.local_fps = float(os.getenv("INTERNVIDEO3_LOCAL_FPS", "0.25"))
        self.local_max_frames = int(os.getenv("INTERNVIDEO3_LOCAL_MAX_FRAMES", "8"))
        self.local_max_new_tokens = int(os.getenv("INTERNVIDEO3_LOCAL_MAX_NEW_TOKENS", "96"))
        self.local_python = os.getenv("INTERNVIDEO3_PYTHON", "/home/haoqian/miniconda3/envs/omniC/bin/python")
        self.local_runner = settings.project_root / "scripts" / "internvideo3_score.py"

    def is_available(self) -> bool:
        return bool(self.endpoint or self.cli or (self.local_enabled and self._local_checkpoint_ready()))

    def describe_provider(self) -> dict[str, Any]:
        if self.endpoint:
            mode = "http"
            reason = None
        elif self.cli:
            mode = "cli"
            reason = None
        elif self.local_enabled and self._local_checkpoint_ready():
            mode = "local_hf_lazy"
            reason = None
        else:
            mode = "disabled"
            reason = "No INTERNVIDEO3 endpoint/CLI and no ready local checkpoint, or local mode disabled."
        return {
            "provider": "internvideo3",
            "available": self.is_available(),
            "mode": mode,
            "endpoint_configured": bool(self.endpoint),
            "cli_configured": bool(self.cli),
            "local_checkpoint_detected": self.model_path.exists(),
            "local_checkpoint_ready": self._local_checkpoint_ready(),
            "local_enabled": self.local_enabled,
            "local_search_rerank": self.local_search_rerank,
            "local_python": self.local_python if Path(self.local_python).exists() else None,
            "local_runner": str(self.local_runner) if self.local_runner.exists() else None,
            "model_path": str(self.model_path) if self.model_path.exists() else None,
            "dependencies": self._dependency_status(),
            "reason": reason,
        }

    def encode_video_clip(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        keyframe_paths: list[str],
    ) -> Optional[list[float]]:
        if self.endpoint:
            payload = {
                "task": "encode_video_clip",
                "video_path": video_path,
                "start_time": start_time,
                "end_time": end_time,
                "keyframe_paths": keyframe_paths,
            }
            data = self._post(payload)
            return data.get("embedding") if isinstance(data.get("embedding"), list) else None
        if self.cli:
            data = self._run_cli("encode_video_clip", video_path, start_time, end_time, keyframe_paths)
            return data.get("embedding") if isinstance(data.get("embedding"), list) else None
        return None

    def encode_text(self, text: str) -> Optional[list[float]]:
        if self.endpoint:
            data = self._post({"task": "encode_text", "text": text})
            return data.get("embedding") if isinstance(data.get("embedding"), list) else None
        if self.cli:
            data = self._run_cli("encode_text", text)
            return data.get("embedding") if isinstance(data.get("embedding"), list) else None
        return None

    def score_text_video(
        self,
        query: str,
        video_path: str,
        start_time: float,
        end_time: float,
        keyframe_paths: list[str],
    ) -> Optional[float]:
        if self.endpoint:
            data = self._post(
                {
                    "task": "score_text_video",
                    "query": query,
                    "video_path": video_path,
                    "start_time": start_time,
                    "end_time": end_time,
                    "keyframe_paths": keyframe_paths,
                }
            )
            return self._coerce_score(data)
        if self.cli:
            data = self._run_cli("score_text_video", query, video_path, start_time, end_time, keyframe_paths)
            return self._coerce_score(data)
        if self.local_enabled and self.local_search_rerank and self._local_checkpoint_ready():
            data = self._score_local(query, video_path, start_time, end_time)
            return self._coerce_score(data)
        return None

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(self.endpoint, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            return {"error": type(exc).__name__, "message": str(exc)[:500]}

    def _run_cli(self, task: str, *args: Any) -> dict[str, Any]:
        command = [self.cli, "--task", task, "--json-args", json.dumps(args)]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
            return json.loads(result.stdout)
        except Exception as exc:
            return {"error": type(exc).__name__, "message": str(exc)[:500]}

    def _coerce_score(self, data: dict[str, Any]) -> Optional[float]:
        value = data.get("score") or data.get("relevance")
        if value is None:
            return None
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return None

    def _score_local(self, query: str, video_path: str, start_time: float, end_time: float) -> dict[str, Any]:
        if not video_path or not Path(video_path).exists():
            return {"score": None, "error": "video_path_missing"}
        started = time.time()
        try:
            data = self._score_local_subprocess(query, video_path, start_time, end_time)
            data["elapsed"] = round(time.time() - started, 2)
            data["mode"] = data.get("mode") or "local_subprocess"
            return data
        except Exception as exc:
            return {"score": None, "mode": "local_subprocess", "error": type(exc).__name__, "message": str(exc)[:700]}

    def _score_local_subprocess(self, query: str, video_path: str, start_time: float, end_time: float) -> dict[str, Any]:
        python = self.local_python if Path(self.local_python).exists() else sys.executable
        command = [
            python,
            str(self.local_runner),
            "--model-path",
            str(self.model_path),
            "--video-path",
            str(video_path),
            "--query",
            query,
            "--start-time",
            str(start_time),
            "--end-time",
            str(end_time),
            "--fps",
            str(self.local_fps),
            "--max-frames",
            str(self.local_max_frames),
            "--max-new-tokens",
            str(self.local_max_new_tokens),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=int(os.getenv("INTERNVIDEO3_LOCAL_TIMEOUT", "420")))
        text = (result.stdout or "").strip().splitlines()[-1] if result.stdout.strip() else "{}"
        try:
            data = json.loads(text)
        except Exception:
            data = {"score": None, "raw_stdout": result.stdout[-1000:]}
        if result.returncode != 0:
            data.setdefault("score", None)
            data["returncode"] = result.returncode
            data["stderr"] = result.stderr[-1000:]
        return data

    def _local_checkpoint_ready(self) -> bool:
        if not self.model_path.exists():
            return False
        return (self.model_path / "model.safetensors.index.json").exists() and any(self.model_path.glob("*.safetensors"))

    def _dependency_status(self) -> dict[str, bool]:
        import importlib.util

        return {
            "torch": importlib.util.find_spec("torch") is not None,
            "transformers": importlib.util.find_spec("transformers") is not None,
            "accelerate": importlib.util.find_spec("accelerate") is not None,
            "qwen_vl_utils": importlib.util.find_spec("qwen_vl_utils") is not None,
            "decord": importlib.util.find_spec("decord") is not None,
        }
