from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from ..schemas import EvidenceItem, EvidenceLedgerItem, SearchResult, SkillDefinition


@dataclass(frozen=True)
class RoutedSkill:
    name: str
    reason: str


class EvidenceLedgerBuilder:
    """Normalize retrieved course artifacts into traceable evidence records."""

    def from_search_results(self, results: list[SearchResult | EvidenceItem | dict[str, Any]], provider: str = "hybrid_search") -> list[EvidenceLedgerItem]:
        return [self.from_evidence_item(item, provider=provider, index=idx) for idx, item in enumerate(results)]

    def from_evidence_item(self, item: SearchResult | EvidenceItem | dict[str, Any], provider: str = "indexed_evidence", index: int = 0) -> EvidenceLedgerItem:
        data = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        modalities = data.get("matched_modalities") or data.get("modality") or []
        content_parts = [
            data.get("transcript_snippet") or data.get("transcript") or "",
            data.get("ocr_snippet") or data.get("ocr_text") or "",
            data.get("formula_latex") or "",
        ]
        content = "\n".join(part for part in content_parts if part).strip()
        moment_id = str(data.get("moment_id") or data.get("evidence_id") or f"evidence_{index}")
        return EvidenceLedgerItem(
            evidence_id=f"ev_{self._short_hash(moment_id + provider + str(index))}",
            source_type="video_moment",
            video_id=data.get("video_id"),
            lecture_id=data.get("lecture_id"),
            lecture_title=data.get("lecture_title"),
            start_time=self._float_or_none(data.get("start_time")),
            end_time=self._float_or_none(data.get("end_time")),
            modality=list(modalities),
            content=content[:1800],
            confidence=self._confidence(data),
            provider=provider,
            score=float(data.get("score") or 0.0),
            reason=str(data.get("matched_reason") or data.get("reason") or "Timestamped course evidence"),
            metadata={
                "moment_id": moment_id,
                "thumbnail_url": data.get("thumbnail_url"),
                "formula_latex": data.get("formula_latex"),
                "concept_tags": data.get("concept_tags") or [],
            },
        )

    def _confidence(self, data: dict[str, Any]) -> float:
        score = float(data.get("score") or 0.0)
        modalities = data.get("matched_modalities") or []
        modality_bonus = min(0.25, 0.05 * len(modalities))
        return round(max(0.05, min(1.0, score + modality_bonus)), 3)

    def _short_hash(self, text: str) -> str:
        return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]

    def _float_or_none(self, value: Any) -> float | None:
        try:
            return float(value)
        except Exception:
            return None


class SkillRouter:
    """Small explicit skill registry for the product-level agent."""

    def __init__(self) -> None:
        self.ledger = EvidenceLedgerBuilder()

    def list_skills(self) -> list[SkillDefinition]:
        return [
            self._skill(
                "Dataset Ingestion Skill",
                ["dataset scanner", "ffmpeg", "ASR", "OCR", "formula OCR", "index rebuild"],
                ["Discover fixed Dataset videos", "Extract multimodal evidence", "Write timestamped moments"],
            ),
            self._skill(
                "Video Moment Retrieval Skill",
                ["ASR retrieval", "OCR retrieval", "formula retrieval", "visual retrieval", "InternVideo3 rerank"],
                ["Build hybrid query", "Score every indexed moment", "Return timestamped evidence ledger"],
            ),
            self._skill(
                "Multimodal QA Skill",
                ["Video Moment Retrieval Skill", "GPT-4o", "Evidence Ledger", "Self-Validation"],
                ["Retrieve first", "Answer only from evidence", "Self-check grounding", "Repair weak answers"],
            ),
            self._skill(
                "Cheatsheet Generation Skill",
                ["ASR", "OCR", "formula OCR", "LaTeX compiler", "GPT-4o"],
                ["Select lecture evidence", "Write compact LaTeX", "Compile or return Overleaf workflow"],
            ),
            self._skill(
                "Knowledge Graph Skill",
                ["concept extraction", "formula linking", "Cytoscape graph", "GraphRAG-style lookup"],
                ["Extract concepts", "Prune noisy nodes", "Add prerequisite edges", "Expose graph evidence"],
            ),
            self._skill(
                "Prerequisite Rewind Skill",
                ["Knowledge Graph Skill", "Video Moment Retrieval Skill"],
                ["Detect target concept", "Find prerequisites", "Return review playlist"],
            ),
            self._skill(
                "Misconception Detection Skill",
                ["pattern library", "Video Moment Retrieval Skill", "GPT-4o judge"],
                ["Detect likely misconception", "Ground correction in clips", "Ask check question"],
            ),
            self._skill(
                "Socratic Drill Skill",
                ["Video Moment Retrieval Skill", "GPT-4o/fallback question writer"],
                ["Retrieve topic evidence", "Generate questions", "Attach hints and answer keys"],
            ),
            self._skill(
                "Formula Derivation Skill",
                ["formula parser", "Video Moment Retrieval Skill", "LaTeX renderer"],
                ["Parse symbols", "Explain derivation steps", "Cite related timestamps"],
            ),
            self._skill(
                "Region Visual Explain Skill",
                ["frame crop", "DeepSeek OCR", "formula OCR", "visual search"],
                ["Crop selected region", "OCR and parse formulas", "Retrieve related moments"],
            ),
            self._skill(
                "Mastery Planning Skill",
                ["local mastery profile", "concept graph", "study plan generator"],
                ["Update concept mastery", "Find weak concepts", "Recommend review clips"],
            ),
        ]

    def route_question(self, question: str) -> list[RoutedSkill]:
        text = question.lower()
        routes = [RoutedSkill("Video Moment Retrieval Skill", "Every tutor response starts with timestamped evidence retrieval.")]
        if re.search(r"\b(why|explain|how|formula|derive|theta|gradient|loss)\b", text):
            routes.append(RoutedSkill("Formula Derivation Skill", "The question asks for mechanism or formula-level explanation."))
        if re.search(r"\b(before|prerequisite|confused|don'?t understand|backpropagation)\b", text):
            routes.append(RoutedSkill("Prerequisite Rewind Skill", "The student may need earlier concepts before this moment."))
        if re.search(r"\b(wrong|misconception|follows the gradient|minimize|maximize)\b", text):
            routes.append(RoutedSkill("Misconception Detection Skill", "The wording may contain a known STEM misconception."))
        routes.append(RoutedSkill("Self-Validation Skill", "The final answer must be checked for grounding and timestamps."))
        return routes

    def _skill(self, name: str, tools: list[str], steps: list[str]) -> SkillDefinition:
        return SkillDefinition(
            name=name,
            input_schema={"type": "object", "course_id": "string", "optional_context": "video_id|moment_id|image|text"},
            tools_used=tools,
            execution_procedure=steps,
            evidence_output_schema={"evidence": "list[EvidenceLedgerItem]", "self_check": "dict"},
        )
