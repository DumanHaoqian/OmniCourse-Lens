from __future__ import annotations

from collections import Counter
from typing import Any

from ..storage import list_courses


class EvidenceService:
    def video_moments(self, video_id: str) -> list[dict[str, Any]]:
        moments: list[dict[str, Any]] = []
        for course in list_courses():
            for lecture in course.lectures:
                for moment in lecture.moments:
                    if moment.video_id == video_id or moment.metadata.get("video_id") == video_id:
                        data = moment.model_dump(mode="json")
                        data["lecture_title"] = lecture.title
                        data["video_path"] = lecture.video_path
                        moments.append(data)
        return sorted(moments, key=lambda item: (item.get("start_time", 0), item.get("end_time", 0)))

    def subtitles(self, video_id: str) -> dict[str, Any]:
        moments = self.video_moments(video_id)
        cues: list[dict[str, Any]] = []
        for moment in moments:
            for segment in moment.get("asr_segments", []) or []:
                text = " ".join(str(segment.get("text") or "").split())
                if not text:
                    continue
                provider = str(segment.get("provider") or "indexed")
                cues.append(
                    {
                        "start_time": float(segment.get("start_time") or moment.get("start_time") or 0.0),
                        "end_time": float(segment.get("end_time") or moment.get("end_time") or 0.0),
                        "text": text,
                        "provider": provider,
                        "source": self._subtitle_source(provider),
                        "moment_id": moment.get("moment_id"),
                        "kind": "audio" if "whisper" in provider or provider == "transcript_file" else "supplemental",
                    }
                )
            ocr_text = " ".join(str(moment.get("ocr_text") or "").split())
            if ocr_text:
                cues.append(
                    {
                        "start_time": float(moment.get("start_time") or 0.0),
                        "end_time": float(moment.get("end_time") or 0.0),
                        "text": ocr_text[:700],
                        "provider": self._best_ocr_provider(moment),
                        "source": self._subtitle_source(self._best_ocr_provider(moment)),
                        "moment_id": moment.get("moment_id"),
                        "kind": "ocr",
                    }
                )
        cues.sort(key=lambda item: (item["start_time"], self._cue_priority(item)))
        return {
            "video_id": video_id,
            "cue_count": len(cues),
            "audio_cue_count": sum(1 for cue in cues if cue["kind"] == "audio"),
            "ocr_cue_count": sum(1 for cue in cues if cue["kind"] == "ocr"),
            "cues": cues,
            "summary": self.video_summary(video_id),
        }

    def subtitles_vtt(self, video_id: str) -> str:
        payload = self.subtitles(video_id)
        audio_cues = [cue for cue in payload["cues"] if cue.get("kind") == "audio"]
        cues = audio_cues or payload["cues"]
        lines = ["WEBVTT", ""]
        for idx, cue in enumerate(cues, start=1):
            text = " ".join(str(cue.get("text") or "").split())
            if not text:
                continue
            lines.append(str(idx))
            lines.append(f"{self._vtt_time(float(cue['start_time']))} --> {self._vtt_time(float(cue['end_time']))}")
            lines.append(text.replace("-->", "->"))
            lines.append("")
        return "\n".join(lines)

    def video_summary(self, video_id: str) -> dict[str, Any]:
        moments = self.video_moments(video_id)
        providers = Counter()
        formula_count = 0
        concept_count = Counter()
        for moment in moments:
            providers.update(segment.get("provider", "unknown") for segment in moment.get("asr_segments", []) or [])
            providers.update(block.get("provider", "unknown") for block in moment.get("ocr_blocks", []) or [])
            providers.update(block.get("provider", "unknown") for block in moment.get("formula_blocks", []) or [])
            formula_count += len(moment.get("formula_blocks", []) or [])
            concept_count.update(moment.get("concept_tags", []) or [])
        return {
            "video_id": video_id,
            "moment_count": len(moments),
            "asr_segment_count": sum(len(moment.get("asr_segments", []) or []) for moment in moments),
            "ocr_block_count": sum(len(moment.get("ocr_blocks", []) or []) for moment in moments),
            "formula_block_count": formula_count,
            "provider_counts": dict(providers),
            "top_concepts": concept_count.most_common(12),
        }

    def moment(self, moment_id: str) -> dict[str, Any] | None:
        for course in list_courses():
            for lecture in course.lectures:
                for moment in lecture.moments:
                    if moment.moment_id == moment_id:
                        data = moment.model_dump(mode="json")
                        data["lecture_title"] = lecture.title
                        data["course_title"] = course.title
                        return data
        return None

    def _best_ocr_provider(self, moment: dict[str, Any]) -> str:
        providers = {str(block.get("provider") or "") for block in moment.get("ocr_blocks", []) or []}
        if "deepseek_ocr" in providers:
            return "deepseek_ocr"
        if providers:
            return sorted(providers)[0]
        return "ocr"

    def _subtitle_source(self, provider: str) -> str:
        value = provider.lower()
        if "whisper" in value or value == "transcript_file":
            return "Audio transcript"
        if value == "deepseek_ocr":
            return "DeepSeek frame OCR"
        if value == "slide_pdf_text":
            return "Slide/PDF text"
        if value == "fallback_asr":
            return "Fallback transcript"
        return "Indexed evidence"

    def _cue_priority(self, cue: dict[str, Any]) -> int:
        provider = str(cue.get("provider") or "").lower()
        if "whisper" in provider or provider == "transcript_file":
            return 0
        if provider == "deepseek_ocr":
            return 1
        if provider == "slide_pdf_text":
            return 2
        return 3

    def _vtt_time(self, seconds: float) -> str:
        seconds = max(0.0, seconds)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
