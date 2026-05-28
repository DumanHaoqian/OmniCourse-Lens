from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

import requests

from ..config import settings


class InternVideo3Service:
    """Lazy adapter for optional InternVideo3 retrieval signals.

    The local checkpoint exists in the parent Trials workspace, but loading it
    at API startup would make the MVP painful to run. This adapter therefore
    uses HTTP or CLI modes when configured and only reports the local checkpoint
    as discoverable by default.
    """

    def __init__(self) -> None:
        self.endpoint = os.getenv("INTERNVIDEO3_ENDPOINT", "").strip()
        self.cli = os.getenv("INTERNVIDEO3_CLI", "").strip()
        configured_model_path = os.getenv("INTERNVIDEO3_MODEL_PATH", "").strip()
        self.model_path = Path(configured_model_path).expanduser() if configured_model_path else settings.legacy_internvideo3_path
        if not self.model_path.is_absolute():
            self.model_path = (settings.project_root / self.model_path).resolve()
        self.local_enabled = os.getenv("INTERNVIDEO3_ENABLE_LOCAL", "0").lower() in {"1", "true", "yes"}

    def is_available(self) -> bool:
        return bool(self.endpoint or self.cli or (self.local_enabled and self.model_path.exists()))

    def describe_provider(self) -> dict[str, Any]:
        if self.endpoint:
            mode = "http"
            reason = None
        elif self.cli:
            mode = "cli"
            reason = None
        elif self.local_enabled and self.model_path.exists():
            mode = "local_import"
            reason = None
        else:
            mode = "disabled"
            reason = "No INTERNVIDEO3_ENDPOINT/CLI configured. Local checkpoint is detected but not loaded unless INTERNVIDEO3_ENABLE_LOCAL=1."
        return {
            "provider": "internvideo3",
            "available": self.is_available(),
            "mode": mode,
            "endpoint_configured": bool(self.endpoint),
            "cli_configured": bool(self.cli),
            "local_checkpoint_detected": self.model_path.exists(),
            "model_path": str(self.model_path) if self.model_path.exists() else None,
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
