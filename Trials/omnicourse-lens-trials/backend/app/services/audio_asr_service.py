from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from typing import Any

from ..config import settings


class AudioASRService:
    def describe_provider(self) -> dict[str, Any]:
        return {
            "faster_whisper_available": importlib.util.find_spec("faster_whisper") is not None,
            "openai_whisper_available": importlib.util.find_spec("whisper") is not None,
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
        if audio_path and importlib.util.find_spec("faster_whisper") is not None:
            result = self._try_faster_whisper(audio_path)
            if result:
                return result
        return self._fallback_segments(duration, title)

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
