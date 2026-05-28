from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from ..config import ensure_directories, settings
from ..schemas import ASRSegment, Course, FormulaBlock, Lecture, Moment, OCRBlock
from ..storage import course_path, load_course, save_course, static_url
from .audio_asr_service import AudioASRService
from .math_ocr_service import MathOCRService
from .ocr_service import OCRService


class VideoIngestService:
    def __init__(self) -> None:
        self.asr = AudioASRService()
        self.ocr = OCRService()
        self.math_ocr = MathOCRService()

    def describe_provider(self) -> dict[str, Any]:
        return {
            "asr": self.asr.describe_provider(),
            "ocr": self.ocr.describe_provider(),
            "math_ocr": self.math_ocr.describe_provider(),
        }

    def ingest_video(
        self,
        video_path: str,
        course_id: str,
        lecture_id: str,
        title: str,
        transcript_file: str | None = None,
        frame_interval: float = 10.0,
        window_sec: float = 20.0,
    ) -> Course:
        ensure_directories()
        metadata = self.probe_video(video_path)
        duration = float(metadata.get("duration") or 120.0)
        audio_path = self.asr.extract_audio(video_path, course_id, lecture_id)
        asr_segments = self.asr.transcribe(audio_path, duration=duration, title=title, transcript_file=transcript_file)
        frames = self.extract_keyframes(video_path, course_id, lecture_id, duration, frame_interval)
        ocr_by_frame = []
        formula_blocks = []
        for frame in frames:
            ocr_result = self.ocr.ocr_image(frame["path"], timestamp=frame["timestamp"])
            ocr_by_frame.append({"frame": frame, "ocr": ocr_result})
            formula_blocks.extend(
                self.math_ocr.extract_formula_blocks(
                    ocr_result.get("text", ""),
                    frame_path=frame["path"],
                    timestamp=frame["timestamp"],
                )
            )
        moments = self.construct_moments(
            course_id=course_id,
            lecture_id=lecture_id,
            duration=duration,
            asr_segments=asr_segments,
            ocr_by_frame=ocr_by_frame,
            formula_blocks=formula_blocks,
            window_sec=window_sec,
        )
        lecture = Lecture(
            lecture_id=lecture_id,
            course_id=course_id,
            title=title,
            video_path=str(video_path),
            duration=duration,
            moments=moments,
            metadata={"ingested": True, "probe": metadata, "audio_path": audio_path},
        )
        if course_path(course_id).exists():
            course = load_course(course_id)
            course.lectures = [lec for lec in course.lectures if lec.lecture_id != lecture_id]
            course.lectures.append(lecture)
        else:
            course = Course(course_id=course_id, title=course_id.replace("_", " ").title(), lectures=[lecture])
        save_course(course)
        return course

    def probe_video(self, video_path: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    video_path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            data = json.loads(result.stdout)
            video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
            return {
                "duration": float(data.get("format", {}).get("duration") or 0),
                "fps": video_stream.get("r_frame_rate"),
                "width": video_stream.get("width"),
                "height": video_stream.get("height"),
            }
        except Exception:
            return {"duration": 120.0, "fps": None, "width": None, "height": None, "probe_error": True}

    def extract_keyframes(self, video_path: str, course_id: str, lecture_id: str, duration: float, interval: float) -> list[dict[str, Any]]:
        frame_dir = settings.frames_dir / course_id / lecture_id
        frame_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        t = 0.0
        while t < max(duration, interval):
            output = frame_dir / f"frame_{int(t):05d}.png"
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-ss",
                        str(t),
                        "-i",
                        video_path,
                        "-frames:v",
                        "1",
                        str(output),
                    ],
                    check=True,
                )
            except Exception:
                self._fallback_frame(output, lecture_id, t)
            if output.exists():
                frames.append({"path": str(output), "timestamp": t, "url": static_url(output)})
            t += interval
        return frames

    def _fallback_frame(self, output: Path, lecture_id: str, timestamp: float) -> None:
        img = Image.new("RGB", (960, 540), "#f8fafc")
        draw = ImageDraw.Draw(img)
        draw.text((48, 48), f"{lecture_id} @ {timestamp:.1f}s", fill="#0f172a")
        draw.text((48, 100), "Fallback frame generated because video decoding failed.", fill="#475569")
        output.parent.mkdir(parents=True, exist_ok=True)
        img.save(output)

    def construct_moments(
        self,
        course_id: str,
        lecture_id: str,
        duration: float,
        asr_segments: list[dict[str, Any]],
        ocr_by_frame: list[dict[str, Any]],
        formula_blocks: list[dict[str, Any]],
        window_sec: float,
    ) -> list[Moment]:
        moments: list[Moment] = []
        start = 0.0
        while start < duration:
            end = min(duration, start + window_sec)
            overlapping_asr = [s for s in asr_segments if s["end_time"] >= start and s["start_time"] <= end]
            overlapping_ocr = [x for x in ocr_by_frame if start <= x["frame"]["timestamp"] <= end]
            overlapping_formula = [f for f in formula_blocks if f.get("timestamp") is None or start <= f.get("timestamp", 0) <= end]
            keyframes = [x["frame"]["path"] for x in overlapping_ocr]
            ocr_blocks = []
            for item in overlapping_ocr:
                for block in item["ocr"].get("blocks", []):
                    block = {**block, "provider": block.get("provider") or item["ocr"].get("provider"), "frame_path": item["frame"]["path"], "timestamp": item["frame"]["timestamp"]}
                    ocr_blocks.append(OCRBlock.model_validate(block))
            concepts = self._concept_tags(overlapping_asr, overlapping_ocr, overlapping_formula)
            moment_id = f"{course_id}_{lecture_id}_{int(start):05d}_{int(end):05d}"
            moments.append(
                Moment(
                    moment_id=moment_id,
                    course_id=course_id,
                    lecture_id=lecture_id,
                    start_time=start,
                    end_time=end,
                    transcript=" ".join(s["text"] for s in overlapping_asr),
                    asr_segments=[ASRSegment.model_validate(s) for s in overlapping_asr],
                    ocr_text=" ".join(x["ocr"].get("text", "") for x in overlapping_ocr),
                    ocr_blocks=ocr_blocks,
                    formula_latex="; ".join(f["latex"] for f in overlapping_formula),
                    formula_blocks=[FormulaBlock.model_validate(f) for f in overlapping_formula],
                    visual_caption=f"Frames from {lecture_id} around {start:.0f}-{end:.0f}s.",
                    concept_tags=concepts,
                    keyframes=keyframes,
                    thumbnail_url=static_url(keyframes[0]) if keyframes else None,
                    metadata={"ingested_window": True},
                )
            )
            start += window_sec
        return moments

    def _concept_tags(self, asr_segments: list[dict[str, Any]], ocr_by_frame: list[dict[str, Any]], formulas: list[dict[str, Any]]) -> list[str]:
        text = " ".join([*(s["text"] for s in asr_segments), *(x["ocr"].get("text", "") for x in ocr_by_frame), *(f["latex"] for f in formulas)]).lower()
        tags = []
        for concept in [
            "gradient descent",
            "learning rate",
            "normal equation",
            "linear regression",
            "mean squared error",
            "loss function",
            "chain rule",
            "backpropagation",
            "neural network",
            "activation function",
        ]:
            if concept in text:
                tags.append(concept)
        return tags[:8]
