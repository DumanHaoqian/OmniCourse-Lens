from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..config import settings


class AudioASRService:
    def __init__(self) -> None:
        self.enabled = os.getenv("OMNICOURSE_ENABLE_ASR", "1").lower() in {"1", "true", "yes"}
        self.provider = os.getenv("OMNICOURSE_ASR_PROVIDER", "faster_whisper").strip() or "faster_whisper"
        self.model = os.getenv("OMNICOURSE_ASR_MODEL", "small.en").strip() or "small.en"
        self.device = os.getenv("OMNICOURSE_ASR_DEVICE", "auto").strip() or "auto"
        self.compute_type = os.getenv("OMNICOURSE_ASR_COMPUTE_TYPE", "float16").strip() or "float16"
        self.language = os.getenv("OMNICOURSE_ASR_LANGUAGE", "en").strip()
        self.beam_size = int(os.getenv("OMNICOURSE_ASR_BEAM_SIZE", "5"))
        self.word_timestamps = os.getenv("OMNICOURSE_ASR_WORD_TIMESTAMPS", "1").lower() in {"1", "true", "yes"}
        self.vad_filter = os.getenv("OMNICOURSE_ASR_VAD_FILTER", "1").lower() in {"1", "true", "yes"}
        self.python = os.getenv("OMNICOURSE_ASR_PYTHON", "/home/haoqian/miniconda3/envs/omniC/bin/python")
        self.runner = settings.project_root / "scripts" / "asr_transcribe.py"
        configured_download_root = os.getenv("OMNICOURSE_ASR_MODEL_DIR", "").strip()
        self.download_root = Path(configured_download_root).expanduser() if configured_download_root else settings.repo_root / "Trials" / "checkpoints" / "asr"

    def describe_provider(self) -> dict[str, Any]:
        runner_available = self.runner.exists()
        python_available = Path(self.python).exists()
        runner_deps = self._runner_dependency_status() if python_available and runner_available else {}
        return {
            "faster_whisper_available": importlib.util.find_spec("faster_whisper") is not None,
            "faster_whisper_runner_available": bool(runner_deps.get("faster_whisper")),
            "ctranslate2_runner_available": bool(runner_deps.get("ctranslate2")),
            "openai_whisper_available": importlib.util.find_spec("whisper") is not None,
            "openai_whisper_enabled": os.getenv("OMNICOURSE_ENABLE_WHISPER", "1").lower() in {"1", "true", "yes"},
            "enabled": self.enabled,
            "active_provider": self.provider,
            "model": self.model,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": self.language,
            "word_timestamps": self.word_timestamps,
            "vad_filter": self.vad_filter,
            "runner": str(self.runner) if runner_available else None,
            "runner_python": self.python if python_available else None,
            "model_cache": str(self.download_root),
            "cuda_library_paths": self._cuda_library_paths(),
            "runner_dependencies": runner_deps,
            "fallback": "transcript_file_or_deterministic_demo_segments",
        }

    def extract_audio(self, video_path: str, course_id: str, lecture_id: str) -> str | None:
        output = settings.audio_dir / f"{course_id}_{lecture_id}.wav"
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video_path,
            "-ac",
            "1",
            "-ar",
            "16000",
            str(output),
        ]
        try:
            subprocess.run(command, check=True)
            return str(output)
        except Exception:
            return None

    def transcribe(
        self,
        audio_path: str | None,
        duration: float,
        title: str,
        transcript_file: str | None = None,
    ) -> list[dict[str, Any]]:
        if transcript_file:
            parsed = self._parse_transcript_file(Path(transcript_file))
            if parsed:
                return parsed
        if audio_path and os.getenv("OMNICOURSE_ASR_REUSE_CACHE", "1").lower() in {"1", "true", "yes"}:
            cached = self._read_transcript_cache(audio_path)
            if cached:
                return cached
        if audio_path and self.enabled:
            result = self._try_runner(audio_path)
            if result:
                self._write_transcript_cache(audio_path, result)
                return result
        if audio_path and importlib.util.find_spec("faster_whisper") is not None:
            result = self._try_faster_whisper(audio_path)
            if result:
                self._write_transcript_cache(audio_path, result)
                return result
        if audio_path and importlib.util.find_spec("whisper") is not None:
            result = self._try_openai_whisper(audio_path)
            if result:
                self._write_transcript_cache(audio_path, result)
                return result
        return self._fallback_segments(duration, title)

    def _try_runner(self, audio_path: str) -> list[dict[str, Any]]:
        if not self.runner.exists():
            return []
        python = self.python if Path(self.python).exists() else sys.executable
        provider = self.provider
        model = self.model
        if provider == "openai_whisper" and os.getenv("OMNICOURSE_ENABLE_WHISPER", "1").lower() not in {"1", "true", "yes"}:
            return []
        self.download_root.mkdir(parents=True, exist_ok=True)
        command = [
            python,
            str(self.runner),
            "--audio-path",
            audio_path,
            "--provider",
            provider,
            "--model",
            model,
            "--device",
            self.device,
            "--compute-type",
            self.compute_type,
            "--language",
            self.language,
            "--beam-size",
            str(self.beam_size),
            "--download-root",
            str(self.download_root),
        ]
        if self.word_timestamps:
            command.append("--word-timestamps")
        if self.vad_filter:
            command.append("--vad-filter")
        timeout = int(os.getenv("OMNICOURSE_ASR_TIMEOUT", "1800"))
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=self._runner_env())
            text = (result.stdout or "").strip().splitlines()[-1] if result.stdout.strip() else "{}"
            payload = json.loads(text)
            if result.returncode != 0 or payload.get("error"):
                if provider != "openai_whisper" and os.getenv("OMNICOURSE_ASR_ALLOW_OPENAI_FALLBACK", "1").lower() in {"1", "true", "yes"}:
                    return self._try_runner_with_provider(audio_path, "openai_whisper", self._openai_model_name())
                return []
            return self._normalize_segments(payload.get("segments", []), fallback_provider=payload.get("provider", provider))
        except Exception:
            if provider != "openai_whisper" and os.getenv("OMNICOURSE_ASR_ALLOW_OPENAI_FALLBACK", "1").lower() in {"1", "true", "yes"}:
                return self._try_runner_with_provider(audio_path, "openai_whisper", self._openai_model_name())
            return []

    def _try_runner_with_provider(self, audio_path: str, provider: str, model: str) -> list[dict[str, Any]]:
        original_provider, original_model = self.provider, self.model
        self.provider, self.model = provider, model
        try:
            return self._try_runner(audio_path)
        finally:
            self.provider, self.model = original_provider, original_model

    def _try_faster_whisper(self, audio_path: str) -> list[dict[str, Any]]:
        try:
            from faster_whisper import WhisperModel

            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(audio_path)
            return [
                {
                    "start_time": float(seg.start),
                    "end_time": float(seg.end),
                    "text": seg.text.strip(),
                    "confidence": None,
                    "provider": "faster_whisper",
                }
                for seg in segments
            ]
        except Exception:
            return []

    def _try_openai_whisper(self, audio_path: str) -> list[dict[str, Any]]:
        if os.getenv("OMNICOURSE_ENABLE_WHISPER", "1").lower() not in {"1", "true", "yes"}:
            return []
        try:
            import whisper

            model_name = os.getenv("OMNICOURSE_WHISPER_MODEL", "base")
            model = whisper.load_model(model_name)
            result = model.transcribe(audio_path, fp16=False)
            return self._normalize_segments([
                {
                    "start_time": float(seg.get("start", 0.0)),
                    "end_time": float(seg.get("end", 0.0)),
                    "text": str(seg.get("text", "")).strip(),
                    "confidence": None,
                    "provider": f"openai_whisper_{model_name}",
                }
                for seg in result.get("segments", [])
                if str(seg.get("text", "")).strip()
            ])
        except Exception:
            return []

    def _normalize_segments(self, segments: list[dict[str, Any]], fallback_provider: str = "asr") -> list[dict[str, Any]]:
        normalized = []
        for seg in segments:
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            start = float(seg.get("start_time", seg.get("start", 0.0)) or 0.0)
            end = float(seg.get("end_time", seg.get("end", start + 1.0)) or start + 1.0)
            normalized.append(
                {
                    "start_time": round(max(0.0, start), 3),
                    "end_time": round(max(start + 0.05, end), 3),
                    "text": text,
                    "confidence": seg.get("confidence"),
                    "provider": seg.get("provider") or fallback_provider,
                    "words": seg.get("words", []),
                }
            )
        return normalized

    def _runner_dependency_status(self) -> dict[str, bool]:
        command = [
            self.python,
            "-c",
            "import importlib.util, json; print(json.dumps({m: importlib.util.find_spec(m) is not None for m in ['faster_whisper','ctranslate2','whisper','torch']}))",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=8, env=self._runner_env())
            return json.loads(result.stdout.strip() or "{}")
        except Exception:
            return {}

    def _runner_env(self) -> dict[str, str]:
        env = os.environ.copy()
        paths = self._cuda_library_paths()
        if paths:
            existing = env.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = ":".join([*paths, existing] if existing else paths)
        return env

    def _cuda_library_paths(self) -> list[str]:
        candidates = [
            "/home/haoqian/miniconda3/lib/python3.13/site-packages/nvidia/cublas/lib",
            "/home/haoqian/miniconda3/envs/omniC/lib/python3.11/site-packages/nvidia/cublas/lib",
            "/home/haoqian/miniconda3/envs/omniC/lib/python3.11/site-packages/nvidia/cudnn/lib",
            "/usr/local/cuda-13.0/targets/x86_64-linux/lib",
        ]
        return [path for path in candidates if Path(path).exists()]

    def _openai_model_name(self) -> str:
        return os.getenv("OMNICOURSE_OPENAI_WHISPER_MODEL", "base.en")

    def _write_transcript_cache(self, audio_path: str, segments: list[dict[str, Any]]) -> None:
        try:
            output = Path(audio_path).with_suffix(".asr.json")
            output.write_text(json.dumps({"segments": segments}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _read_transcript_cache(self, audio_path: str) -> list[dict[str, Any]]:
        try:
            path = Path(audio_path).with_suffix(".asr.json")
            if not path.exists():
                return []
            payload = json.loads(path.read_text(encoding="utf-8"))
            return self._normalize_segments(payload.get("segments", []), fallback_provider="cached_asr")
        except Exception:
            return []

    def _parse_transcript_file(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8", errors="ignore")
        segments = []
        for idx, line in enumerate(text.splitlines()):
            line = line.strip()
            if not line or re.match(r"^\d+$", line) or "-->" in line:
                continue
            start = float(idx * 10)
            segments.append(
                {
                    "start_time": start,
                    "end_time": start + 10,
                    "text": line,
                    "confidence": None,
                    "provider": "transcript_file",
                }
            )
        return segments

    def _fallback_segments(self, duration: float, title: str) -> list[dict[str, Any]]:
        duration = max(duration, 60.0)
        topics = [
            f"This lecture introduces {title}.",
            f"We connect the visual slide content to formulas and learning concepts.",
            f"The important ideas are searchable through transcript, OCR, formulas, and keyframes.",
        ]
        segment_len = duration / len(topics)
        return [
            {
                "start_time": round(i * segment_len, 2),
                "end_time": round((i + 1) * segment_len, 2),
                "text": text,
                "confidence": 0.25,
                "provider": "fallback_asr",
            }
            for i, text in enumerate(topics)
        ]
