from __future__ import annotations

import json
import time
from typing import Any

from ..config import settings
from ..schemas import EvidenceItem, QARequest, QAResponse, SearchRequest, SearchResult
from ..storage import load_course
from .llm_service import LLMService
from .search_service import SearchService
from .self_improvement_service import SelfImprovementService


class QAAgent:
    def __init__(self) -> None:
        self.search = SearchService()
        self.llm = LLMService()
        self.improver = SelfImprovementService()

    def answer(self, request: QARequest, image_path: str | None = None) -> QAResponse:
        evidence = self._retrieve(request, image_path)
        if self.llm.is_available():
            answer = self._answer_with_llm(request, evidence)
            mode = "gpt-4o"
            if not answer:
                answer = self._answer_fallback(request, evidence)
                mode = "fallback"
        else:
            answer = self._answer_fallback(request, evidence)
            mode = "fallback"
        improved = self.improver.improve_qa(request, answer, evidence)
        answer = improved["answer"]
        confidence = self._confidence(evidence, improved["self_check"])
        suggested_review = evidence[:3]
        followups = self._followups(request.question, evidence)
        response = QAResponse(
            answer=answer,
            evidence=evidence,
            suggested_review=suggested_review,
            follow_up_questions=followups,
            confidence=confidence,
            self_check=improved["self_check"],
            generation_mode=mode,
        )
        self._save_response(request, response, improved["actions_taken"])
        return response

    def _retrieve(self, request: QARequest, image_path: str | None) -> list[EvidenceItem]:
        lecture_ids = [request.lecture_id] if request.lecture_id else None
        top_k = request.top_k or 5
        if image_path:
            search_payload = self.search.image_search(
                request.course_id,
                image_path=image_path,
                text_query=request.question,
                lecture_ids=lecture_ids,
                top_k=top_k,
            )
        else:
            search_payload = self.search.text_search(
                SearchRequest(course_id=request.course_id, query=request.question, lecture_ids=lecture_ids, top_k=top_k)
            )
        results = search_payload.get("results", [])
        evidence = [self._from_search_result(result) for result in results]
        evidence.extend(self._nearby_timestamp_evidence(request, existing={item.moment_id for item in evidence}))
        evidence.sort(key=lambda item: item.score, reverse=True)
        return evidence[: max(1, top_k + 2)]

    def _answer_with_llm(self, request: QARequest, evidence: list[EvidenceItem]) -> str:
        evidence_text = "\n\n".join(self._evidence_text(item) for item in evidence)
        prompt = (
            f"Question: {request.question}\n\nCourse evidence:\n{evidence_text}\n\n"
            "Answer with timestamp citations. If evidence is weak, say so and recommend closest clips."
        )
        answer = self.llm.chat(
            "You are OmniCourse Lens, an evidence-grounded AI tutor for STEM lecture videos. "
            "You must answer only using the provided course evidence. Every important claim should be connected to a lecture moment or timestamp. "
            "If the evidence is insufficient, say so clearly and recommend the closest relevant clips. Do not invent lecture content. "
            "Prefer multimodal evidence: ASR transcript, frame OCR, formulas, keyframes, and video relevance signals.",
            prompt,
            temperature=0.2,
            max_tokens=1400,
        )
        return answer

    def _answer_fallback(self, request: QARequest, evidence: list[EvidenceItem]) -> str:
        if not evidence:
            return "I could not find enough course evidence to answer that. Try a more specific lecture concept or upload a slide/keyframe image."
        best = evidence[0]
        formula = f" The relevant formula evidence is `{best.formula_latex}`." if best.formula_latex else ""
        snippets = " ".join(part for part in [best.transcript_snippet, best.ocr_snippet] if part)
        return (
            f"Based on {best.lecture_title} at {best.start_time:.0f}-{best.end_time:.0f}s, the closest evidence says: "
            f"{snippets}{formula}\n\n"
            f"For the question \"{request.question}\", review this moment first, then compare it with the next suggested clips below."
        )

    def _nearby_timestamp_evidence(self, request: QARequest, existing: set[str]) -> list[EvidenceItem]:
        if request.current_timestamp is None or not request.lecture_id:
            return []
        try:
            course = load_course(request.course_id)
        except Exception:
            return []
        extras = []
        for lecture in course.lectures:
            if lecture.lecture_id != request.lecture_id:
                continue
            for moment in lecture.moments:
                if moment.moment_id in existing:
                    continue
                distance = min(abs(moment.start_time - request.current_timestamp), abs(moment.end_time - request.current_timestamp))
                if distance <= 45:
                    extras.append(
                        EvidenceItem(
                            moment_id=moment.moment_id,
                            lecture_id=lecture.lecture_id,
                            lecture_title=lecture.title,
                            start_time=moment.start_time,
                            end_time=moment.end_time,
                            thumbnail_url=moment.thumbnail_url,
                            matched_reason="Nearby current playback timestamp.",
                            matched_modalities=["Timestamp context", "ASR transcript", "OCR"],
                            transcript_snippet=self._short(moment.transcript),
                            ocr_snippet=self._short(moment.ocr_text),
                            formula_latex=moment.formula_latex,
                            score=max(0.1, 1.0 - distance / 45.0),
                        )
                    )
        return extras

    def _from_search_result(self, result: SearchResult | dict[str, Any]) -> EvidenceItem:
        data = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        return EvidenceItem(
            moment_id=data["moment_id"],
            lecture_id=data["lecture_id"],
            lecture_title=data["lecture_title"],
            start_time=float(data["start_time"]),
            end_time=float(data["end_time"]),
            thumbnail_url=data.get("thumbnail_url"),
            matched_reason=data.get("matched_reason", ""),
            matched_modalities=data.get("matched_modalities", []),
            transcript_snippet=data.get("transcript_snippet", ""),
            ocr_snippet=data.get("ocr_snippet", ""),
            formula_latex=data.get("formula_latex", ""),
            score=float(data.get("score", 0.0)),
        )

    def _evidence_text(self, item: EvidenceItem) -> str:
        return (
            f"- {item.lecture_title} ({item.lecture_id}) {item.start_time:.0f}-{item.end_time:.0f}s, score={item.score:.2f}\n"
            f"  Reason: {item.matched_reason}\n  Transcript: {item.transcript_snippet}\n"
            f"  OCR: {item.ocr_snippet}\n  Formula: {item.formula_latex}\n  Modalities: {', '.join(item.matched_modalities)}"
        )

    def _followups(self, question: str, evidence: list[EvidenceItem]) -> list[str]:
        concepts = []
        for item in evidence:
            text = f"{item.transcript_snippet} {item.ocr_snippet}".lower()
            for concept in ["learning rate", "loss function", "normal equation", "chain rule", "activation function", "backpropagation"]:
                if concept in text and concept not in concepts:
                    concepts.append(concept)
        if not concepts:
            concepts = ["the closest timestamped lecture evidence", "the formula shown in the slide"]
        return [f"How does {concept} connect to this question?" for concept in concepts[:3]]

    def _confidence(self, evidence: list[EvidenceItem], self_check: dict[str, Any]) -> float:
        if not evidence:
            return 0.0
        top = max(item.score for item in evidence)
        judge = float(self_check.get("score", 0.0)) / 10.0
        return round(max(0.0, min(1.0, 0.65 * top + 0.35 * judge)), 3)

    def _save_response(self, request: QARequest, response: QAResponse, actions_taken: list[str]) -> None:
        out_dir = settings.generated_dir / "qa"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        payload = {
            "request": request.model_dump(mode="json"),
            "response": response.model_dump(mode="json"),
            "actions_taken": actions_taken,
        }
        (out_dir / f"{request.course_id}_{stamp}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.improver.evaluator.save_log(
            "qa",
            request,
            {"answer_chars": len(response.answer), "evidence_count": len(response.evidence)},
            response.self_check,
            actions_taken,
        )

    def _short(self, text: str, max_chars: int = 220) -> str:
        text = " ".join((text or "").split())
        return text[: max_chars - 3] + "..." if len(text) > max_chars else text
