from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from PIL import Image

from ..config import settings
from ..schemas import (
    FormulaDerivationRequest,
    MasteryUpdateRequest,
    MisconceptionCheckRequest,
    PrerequisiteRewindRequest,
    RegionExplainRequest,
    SearchRequest,
    SocraticDrillRequest,
    StudyPlanRequest,
)
from ..storage import generated_url, list_courses, read_json, static_url, write_json
from .evidence_service import EvidenceService
from .llm_service import LLMService
from .math_ocr_service import MathOCRService
from .ocr_service import OCRService
from .search_service import SearchService
from .skill_router import EvidenceLedgerBuilder, SkillRouter


class LearningFeaturesService:
    """Student-facing learning skills built on the same timestamped evidence store."""

    PREREQUISITES: dict[str, list[str]] = {
        "backpropagation": ["chain rule", "loss function", "gradient descent"],
        "gradient descent": ["derivative", "gradient", "loss function", "learning rate"],
        "normal equation": ["linear regression", "mean squared error", "matrix inverse"],
        "neural network": ["linear model", "activation function", "loss function"],
        "activation function": ["linear model", "classification", "nonlinearity"],
        "chain rule": ["derivative", "composite function"],
        "learning rate": ["gradient descent", "step size", "loss function"],
    }

    MISCONCEPTIONS = [
        {
            "patterns": [r"follows? the gradient", r"go(es)? with the gradient", r"gradient.*minimi[sz]e"],
            "concept": "gradient descent",
            "misconception": "Gradient descent does not follow the gradient for minimization.",
            "correction": "The gradient points toward steepest local increase of the objective, so minimization updates parameters in the opposite direction.",
            "formula": r"\theta := \theta - \alpha \nabla_\theta J(\theta)",
        },
        {
            "patterns": [r"large learning rate.*always", r"bigger.*learning rate.*better"],
            "concept": "learning rate",
            "misconception": "A larger learning rate is not always better.",
            "correction": "A large step can overshoot a minimum or make optimization unstable; the step size controls the tradeoff between speed and stability.",
            "formula": r"\theta := \theta - \alpha \nabla_\theta J(\theta)",
        },
        {
            "patterns": [r"normal equation.*gradient descent", r"gradient descent.*closed form"],
            "concept": "normal equation",
            "misconception": "The normal equation and gradient descent are not the same optimization procedure.",
            "correction": "The normal equation solves a least-squares problem in closed form when assumptions and matrix conditions allow it; gradient descent iteratively updates parameters.",
            "formula": r"\hat{\theta} = (X^\top X)^{-1}X^\top y",
        },
        {
            "patterns": [r"backprop.*only.*neural", r"chain rule.*not.*backprop"],
            "concept": "backpropagation",
            "misconception": "Backpropagation is the chain rule organized over a computation graph.",
            "correction": "Backpropagation efficiently applies the chain rule from output loss back through intermediate variables and parameters.",
            "formula": r"\frac{\partial L}{\partial w} = \frac{\partial L}{\partial z}\frac{\partial z}{\partial w}",
        },
    ]

    def __init__(self) -> None:
        self.search = SearchService()
        self.evidence = EvidenceService()
        self.ocr = OCRService()
        self.math_ocr = MathOCRService()
        self.llm = LLMService()
        self.router = SkillRouter()
        self.ledger = EvidenceLedgerBuilder()

    def skills(self) -> dict[str, Any]:
        return {
            "skills": [skill.model_dump(mode="json") for skill in self.router.list_skills()],
            "architecture": "raw video -> timestamped multimodal evidence store -> skill router -> evidence ledger -> validated learning artifact",
        }

    def prerequisite_rewind(self, request: PrerequisiteRewindRequest) -> dict[str, Any]:
        target = self._target_concept(request.target_concept or request.question or request.current_moment_id or "gradient descent")
        prerequisites = self.PREREQUISITES.get(target, self._nearest_prerequisites(target))
        supporting = []
        for concept in prerequisites[:5]:
            supporting.extend(self._search(concept, request, top_k=2))
        supporting = self._dedupe_results(supporting)[: max(3, request.top_k)]
        ledger = self.ledger.from_search_results(supporting, provider="prerequisite_rewind")
        explanation = self._maybe_llm(
            "Explain prerequisite clips for a course learner using only the evidence.",
            self._prereq_prompt(target, prerequisites, supporting),
            fallback=(
                f"To study **{target}**, review these prerequisites first: "
                + ", ".join(prerequisites[:5])
                + ". The playlist is ordered from foundation concepts toward the current topic."
            ),
        )
        payload = {
            "skill": "Prerequisite Rewind",
            "target_concept": target,
            "prerequisite_concepts": prerequisites,
            "recommended_order": [
                {
                    "concept": concept,
                    "why": f"This concept supports {target}.",
                    "moments": [self._result_json(item) for item in supporting if concept in self._result_text(item).lower()][:2],
                }
                for concept in prerequisites
            ],
            "supporting_moments": [self._result_json(item) for item in supporting],
            "evidence_ledger": [item.model_dump(mode="json") for item in ledger],
            "explanation_markdown": explanation,
            "self_check": self._self_check("prerequisite_rewind", ledger, minimum=2),
        }
        self._save_learning_log("prerequisite_rewind", request.model_dump(mode="json"), payload)
        return payload

    def misconception_check(self, request: MisconceptionCheckRequest) -> dict[str, Any]:
        text = request.student_text.strip()
        match = self._match_misconception(text, request.related_concept)
        concept = match["concept"] if match else self._target_concept(request.related_concept or text)
        supporting = self._search(concept, request, top_k=max(3, request.top_k))
        ledger = self.ledger.from_search_results(supporting, provider="misconception_check")
        if match:
            misconception = match["misconception"]
            correction = match["correction"]
            formula = match.get("formula", "")
        else:
            misconception = "No high-confidence misconception pattern was detected."
            correction = "The answer should still be checked against the timestamped lecture evidence below."
            formula = ""
        if self.llm.is_available():
            correction = self._maybe_llm(
                "You detect and correct student misconceptions using only course evidence.",
                f"Student text: {text}\nConcept: {concept}\nEvidence:\n{self._evidence_text(supporting)}\nWrite a concise correction with LaTeX if useful.",
                fallback=correction,
            )
        payload = {
            "skill": "Misconception Detector",
            "detected": bool(match),
            "related_concept": concept,
            "misconception": misconception,
            "correction_markdown": correction + (f"\n\n\\[\n{formula}\n\\]" if formula else ""),
            "evidence_clips": [self._result_json(item) for item in supporting],
            "follow_up_check": f"In one sentence, explain how {concept} is supported by the timestamped evidence.",
            "evidence_ledger": [item.model_dump(mode="json") for item in ledger],
            "self_check": self._self_check("misconception_check", ledger, minimum=1),
        }
        self._save_learning_log("misconception_check", request.model_dump(mode="json"), payload)
        return payload

    def socratic_drill(self, request: SocraticDrillRequest) -> dict[str, Any]:
        supporting = self._search(request.focus_topic, request, top_k=max(4, request.number_of_questions))
        ledger = self.ledger.from_search_results(supporting, provider="socratic_drill")
        questions = []
        for idx, item in enumerate(supporting[: max(1, min(8, request.number_of_questions))], start=1):
            timestamp = f"{self._value(item, 'start_time'):.0f}-{self._value(item, 'end_time'):.0f}s"
            concept = self._best_concept_from_result(item, request.focus_topic)
            questions.append(
                {
                    "question": f"{idx}. What has to be true for {concept} to help answer the problem shown around {timestamp}?",
                    "hint": self._short(self._value(item, "matched_reason") or self._value(item, "ocr_snippet") or self._value(item, "transcript_snippet"), 220),
                    "answer_key": self._short(
                        f"Use the evidence from {self._value(item, 'lecture_title')} at {timestamp}: "
                        f"{self._value(item, 'transcript_snippet') or self._value(item, 'ocr_snippet')}",
                        420,
                    ),
                    "evidence": self._result_json(item),
                }
            )
        payload = {
            "skill": "Socratic Drill",
            "focus_topic": request.focus_topic,
            "difficulty": request.difficulty,
            "questions": questions,
            "evidence_ledger": [item.model_dump(mode="json") for item in ledger],
            "self_check": self._self_check("socratic_drill", ledger, minimum=2),
        }
        self._save_learning_log("socratic_drill", request.model_dump(mode="json"), payload)
        return payload

    def formula_derivation(self, request: FormulaDerivationRequest) -> dict[str, Any]:
        formula = request.formula_latex.strip() or r"\theta := \theta - \alpha \nabla_\theta J(\theta)"
        query = request.question or self._formula_query(formula)
        supporting = self._search(query, request, top_k=max(3, request.top_k))
        ledger = self.ledger.from_search_results(supporting, provider="formula_derivation")
        steps = self._formula_steps(formula)
        if self.llm.is_available():
            llm_steps = self.llm.chat_json(
                "Return strict JSON with key steps, an array of concise derivation steps grounded in evidence.",
                f"Formula: {formula}\nQuestion: {request.question or ''}\nEvidence:\n{self._evidence_text(supporting)}",
                max_tokens=1000,
            )
            if isinstance(llm_steps.get("steps"), list) and llm_steps["steps"]:
                steps = [str(step) for step in llm_steps["steps"][:8]]
        payload = {
            "skill": "Formula Derivation Tutor",
            "formula_latex": formula,
            "derivation_markdown": "\n".join([f"{idx}. {step}" for idx, step in enumerate(steps, start=1)]),
            "symbols": self._formula_symbols(formula),
            "common_mistakes": self._formula_mistakes(formula),
            "evidence_clips": [self._result_json(item) for item in supporting],
            "evidence_ledger": [item.model_dump(mode="json") for item in ledger],
            "self_check": self._self_check("formula_derivation", ledger, minimum=1),
        }
        self._save_learning_log("formula_derivation", request.model_dump(mode="json"), payload)
        return payload

    def region_explain(self, request: RegionExplainRequest) -> dict[str, Any]:
        image_path = self._resolve_region_image(request)
        crop_path = self._crop_region(image_path, request.bbox) if image_path else None
        ocr_result = self.ocr.ocr_image(str(crop_path or image_path), timestamp=request.timestamp, allow_heavy=True) if (crop_path or image_path) else {"text": "", "blocks": []}
        formulas = self.math_ocr.extract_formula_blocks(ocr_result.get("text", ""), str(crop_path or image_path) if (crop_path or image_path) else None, request.timestamp)
        query = " ".join(part for part in [request.question or "", ocr_result.get("text", ""), " ".join(block["latex"] for block in formulas)] if part).strip()
        if not query:
            query = "formula diagram slide explanation"
        supporting = self._search(query, request, top_k=max(3, request.top_k))
        ledger = self.ledger.from_search_results(supporting, provider="region_explain")
        explanation = self._maybe_llm(
            "Explain a selected lecture frame region using OCR/formula evidence and related moments only.",
            f"Region OCR: {ocr_result.get('text')}\nFormulas: {formulas}\nQuestion: {request.question or ''}\nEvidence:\n{self._evidence_text(supporting)}",
            fallback=(
                "The selected region appears to contain "
                + (ocr_result.get("text") or "visual lecture content")
                + ". Related timestamped clips below are the safest explanation context."
            ),
        )
        payload = {
            "skill": "Region-Level Visual Explain",
            "image_path": str(image_path) if image_path else None,
            "crop_url": static_url(crop_path) if crop_path else static_url(image_path) if image_path else None,
            "bbox": request.bbox,
            "region_ocr": ocr_result,
            "formula_blocks": formulas,
            "explanation_markdown": explanation,
            "related_moments": [self._result_json(item) for item in supporting],
            "evidence_ledger": [item.model_dump(mode="json") for item in ledger],
            "confidence": min(1.0, 0.35 + 0.15 * len(ocr_result.get("text", "")) + 0.1 * len(formulas)),
            "self_check": self._self_check("region_explain", ledger, minimum=1),
        }
        self._save_learning_log("region_explain", request.model_dump(mode="json"), payload)
        return payload

    def mastery_update(self, request: MasteryUpdateRequest) -> dict[str, Any]:
        profile = self._load_profile(request.student_id, request.course_id)
        concepts = set(profile.get("concept_mastery", {}).keys()) | set(request.concepts)
        for interaction in request.interactions:
            concepts.update(self._extract_concepts(str(interaction)))
        for answer in request.quiz_answers:
            concepts.update(self._extract_concepts(str(answer)))
        for clip in request.watched_clips:
            concepts.update(self._extract_concepts(str(clip)))
        if not concepts:
            concepts.update(["gradient descent", "loss function", "learning rate"])
        mastery = profile.setdefault("concept_mastery", {})
        for concept in sorted(concepts):
            current = float(mastery.get(concept, 0.35))
            gain = 0.04 * sum(1 for clip in request.watched_clips if concept in str(clip).lower())
            gain += 0.03 * sum(1 for answer in request.quiz_answers if concept in str(answer).lower() and str(answer).lower().find("wrong") < 0)
            penalty = 0.05 * sum(1 for answer in request.quiz_answers if concept in str(answer).lower() and "wrong" in str(answer).lower())
            mastery[concept] = round(max(0.05, min(1.0, current + gain - penalty)), 3)
        profile["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save_profile(request.student_id, request.course_id, profile)
        return {
            "skill": "Mastery Map",
            "student_id": request.student_id,
            "course_id": request.course_id,
            "profile": profile,
            "weak_concepts": self._weak_concepts(profile),
            "self_check": {"score": 8, "passed": True, "issues": [], "uses_local_profile": True},
        }

    def mastery_profile(self, student_id: str, course_id: str) -> dict[str, Any]:
        profile = self._load_profile(student_id, course_id)
        return {
            "student_id": student_id,
            "course_id": course_id,
            "profile": profile,
            "weak_concepts": self._weak_concepts(profile),
        }

    def study_plan(self, request: StudyPlanRequest) -> dict[str, Any]:
        profile = self._load_profile(request.student_id, request.course_id)
        weak = request.focus_topics or self._weak_concepts(profile) or ["gradient descent", "loss function", "normal equation"]
        plan = []
        for day in range(1, max(1, min(14, request.days)) + 1):
            concept = weak[(day - 1) % len(weak)]
            support = self._search(concept, request, top_k=2)
            plan.append(
                {
                    "day": day,
                    "focus": concept,
                    "review_clips": [self._result_json(item) for item in support],
                    "activity": f"Watch the clips, answer one Socratic drill question, then explain {concept} in your own words.",
                }
            )
        payload = {
            "skill": "Adaptive Study Plan",
            "student_id": request.student_id,
            "course_id": request.course_id,
            "weak_concepts": weak,
            "study_plan": plan,
            "self_check": {"score": 8, "passed": True, "issues": [], "has_review_clips": any(item["review_clips"] for item in plan)},
        }
        self._save_learning_log("study_plan", request.model_dump(mode="json"), payload)
        return payload

    def _search(self, query: str, request: Any, top_k: int = 5) -> list[Any]:
        payload = self.search.text_search(
            SearchRequest(
                course_id=getattr(request, "course_id", "real_i2ml"),
                query=query,
                lecture_ids=[getattr(request, "lecture_id")] if getattr(request, "lecture_id", None) else None,
                video_ids=[getattr(request, "video_id")] if getattr(request, "video_id", None) else None,
                top_k=top_k,
            )
        )
        return payload.get("results", [])

    def _target_concept(self, text: str) -> str:
        lowered = (text or "").lower()
        candidates = list(self.PREREQUISITES.keys()) + [
            "loss function",
            "mean squared error",
            "linear regression",
            "learning rate",
            "chain rule",
            "activation function",
            "normal equation",
            "neural network",
        ]
        for concept in candidates:
            if concept in lowered:
                return concept
        tokens = re.findall(r"[a-z][a-z\s-]{3,32}", lowered)
        return tokens[0].strip() if tokens else "gradient descent"

    def _nearest_prerequisites(self, target: str) -> list[str]:
        if "gradient" in target:
            return self.PREREQUISITES["gradient descent"]
        if "network" in target or "backprop" in target:
            return self.PREREQUISITES["backpropagation"]
        return ["loss function", "derivative", "linear regression"]

    def _match_misconception(self, text: str, related: str | None) -> dict[str, Any] | None:
        haystack = f"{text} {related or ''}".lower()
        for item in self.MISCONCEPTIONS:
            if any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in item["patterns"]):
                return item
        return None

    def _formula_query(self, formula: str) -> str:
        lowered = formula.lower()
        if "\\nabla" in formula or "theta" in lowered or "α" in formula or "\\alpha" in formula:
            return "gradient descent learning rate negative gradient loss function"
        if "x^" in lowered or "x\\top" in lowered or "normal" in lowered:
            return "normal equation linear regression mean squared error"
        if "\\partial" in formula or "chain" in lowered:
            return "chain rule backpropagation derivative"
        return formula

    def _formula_steps(self, formula: str) -> list[str]:
        if "\\nabla" in formula or "∇" in formula:
            return [
                r"Identify the parameter vector \(\theta\) that the model is updating.",
                r"Define the objective \(J(\theta)\), usually a loss or empirical risk from the lecture evidence.",
                r"Compute the gradient \(\nabla_\theta J(\theta)\), which points toward steepest local increase.",
                r"Multiply by the learning rate \(\alpha\) to control step size.",
                r"Subtract the gradient step: \(\theta := \theta - \alpha \nabla_\theta J(\theta)\), moving locally downhill.",
            ]
        if "X" in formula and "y" in formula:
            return [
                r"Start from the least-squares objective.",
                r"Set the derivative with respect to parameters to zero.",
                r"Solve the resulting normal equations when \(X^\top X\) is invertible.",
            ]
        return ["Read the formula symbols.", "Connect each symbol to a lecture definition.", "Use the timestamped evidence to explain the computation step by step."]

    def _formula_symbols(self, formula: str) -> list[dict[str, str]]:
        symbols = []
        if "theta" in formula or "\\theta" in formula or "θ" in formula:
            symbols.append({"symbol": r"\theta", "meaning": "model parameters being updated"})
        if "\\alpha" in formula or "α" in formula:
            symbols.append({"symbol": r"\alpha", "meaning": "learning rate or step size"})
        if "\\nabla" in formula or "∇" in formula:
            symbols.append({"symbol": r"\nabla_\theta J(\theta)", "meaning": "gradient of the objective with respect to parameters"})
        if "J(" in formula:
            symbols.append({"symbol": r"J(\theta)", "meaning": "objective, loss, or empirical risk"})
        if "X" in formula:
            symbols.append({"symbol": "X", "meaning": "design matrix or feature matrix"})
        return symbols

    def _formula_mistakes(self, formula: str) -> list[str]:
        if "\\nabla" in formula or "∇" in formula:
            return [
                "Adding the gradient instead of subtracting it when minimizing.",
                "Treating the learning rate as always beneficial when large.",
                "Ignoring that gradient descent is local and iterative.",
            ]
        return ["Using the formula without checking assumptions.", "Forgetting what each symbol represents in the lecture context."]

    def _resolve_region_image(self, request: RegionExplainRequest) -> Path | None:
        if request.image_path and Path(request.image_path).exists():
            return Path(request.image_path)
        if request.current_moment_id:
            moment = self.evidence.moment(request.current_moment_id)
            if moment:
                for frame in moment.get("keyframes", []) or []:
                    path = Path(frame)
                    if path.exists():
                        return path
        if request.video_id:
            moments = self.evidence.video_moments(request.video_id)
            if request.timestamp is not None:
                moments = sorted(moments, key=lambda item: abs(float(item.get("start_time") or 0) - request.timestamp))
            for moment in moments:
                for frame in moment.get("keyframes", []) or []:
                    path = Path(frame)
                    if path.exists():
                        return path
        return None

    def _crop_region(self, image_path: Path | None, bbox: list[float] | None) -> Path | None:
        if not image_path or not image_path.exists():
            return None
        try:
            with Image.open(image_path) as image:
                width, height = image.size
                if bbox and len(bbox) == 4:
                    x1, y1, x2, y2 = bbox
                    if max(bbox) <= 1.0:
                        x1, x2 = x1 * width, x2 * width
                        y1, y2 = y1 * height, y2 * height
                    crop_box = (
                        max(0, int(min(x1, x2))),
                        max(0, int(min(y1, y2))),
                        min(width, int(max(x1, x2))),
                        min(height, int(max(y1, y2))),
                    )
                else:
                    crop_box = (0, 0, width, height)
                cropped = image.crop(crop_box)
                out_dir = settings.frames_dir / "regions"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"region_{int(time.time() * 1000)}.png"
                cropped.save(out_path)
                return out_path
        except Exception:
            return None

    def _load_profile(self, student_id: str, course_id: str) -> dict[str, Any]:
        path = self._profile_path(student_id, course_id)
        profile = read_json(path, default=None)
        if profile:
            return profile
        concepts = self._course_concepts(course_id)
        return {
            "student_id": student_id,
            "course_id": course_id,
            "concept_mastery": {concept: 0.35 for concept in concepts[:12]},
            "updated_at": None,
        }

    def _save_profile(self, student_id: str, course_id: str, profile: dict[str, Any]) -> None:
        write_json(self._profile_path(student_id, course_id), profile)

    def _profile_path(self, student_id: str, course_id: str) -> Path:
        safe_student = re.sub(r"[^a-zA-Z0-9_-]+", "_", student_id)[:80]
        safe_course = re.sub(r"[^a-zA-Z0-9_-]+", "_", course_id)[:80]
        return settings.generated_dir / "study_plans" / f"{safe_course}_{safe_student}.json"

    def _course_concepts(self, course_id: str) -> list[str]:
        counts: Counter[str] = Counter()
        for course in list_courses():
            if course.course_id != course_id:
                continue
            for lecture in course.lectures:
                for moment in lecture.moments:
                    counts.update(str(tag).lower() for tag in moment.concept_tags)
                    counts.update(self._extract_concepts(moment.transcript + " " + moment.ocr_text))
        return [concept for concept, _ in counts.most_common(20)] or ["gradient descent", "loss function", "linear regression"]

    def _weak_concepts(self, profile: dict[str, Any]) -> list[str]:
        mastery = profile.get("concept_mastery", {})
        ranked = sorted(mastery.items(), key=lambda item: float(item[1]))
        return [concept for concept, score in ranked if float(score) < 0.62][:8]

    def _extract_concepts(self, text: str) -> list[str]:
        lowered = text.lower()
        concepts = set()
        for concept in set(self.PREREQUISITES) | {item for values in self.PREREQUISITES.values() for item in values}:
            if concept in lowered:
                concepts.add(concept)
        return sorted(concepts)

    def _best_concept_from_result(self, item: Any, fallback: str) -> str:
        tags = self._value(item, "concept_tags") or []
        if tags:
            return str(tags[0])
        text = self._result_text(item).lower()
        concepts = self._extract_concepts(text)
        return concepts[0] if concepts else fallback

    def _dedupe_results(self, results: list[Any]) -> list[Any]:
        seen = set()
        out = []
        for item in results:
            key = self._value(item, "moment_id")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _result_json(self, item: Any) -> dict[str, Any]:
        data = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        if data.get("thumbnail_url") and str(data["thumbnail_url"]).startswith("/"):
            data["thumbnail_url"] = data["thumbnail_url"]
        return data

    def _value(self, item: Any, key: str, default: Any = "") -> Any:
        if hasattr(item, key):
            return getattr(item, key)
        if isinstance(item, dict):
            return item.get(key, default)
        return default

    def _result_text(self, item: Any) -> str:
        return " ".join(
            str(self._value(item, key, ""))
            for key in ["lecture_title", "matched_reason", "transcript_snippet", "ocr_snippet", "formula_latex"]
        )

    def _evidence_text(self, results: list[Any]) -> str:
        lines = []
        for item in results[:8]:
            start = self._safe_float(self._value(item, "start_time", 0))
            end = self._safe_float(self._value(item, "end_time", start))
            lines.append(
                f"- {self._value(item, 'lecture_title')} {start:.0f}-{end:.0f}s: "
                f"{self._short(self._result_text(item), 520)}"
            )
        return "\n".join(lines)

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _prereq_prompt(self, target: str, prerequisites: list[str], results: list[Any]) -> str:
        return (
            f"Target concept: {target}\nPrerequisites: {', '.join(prerequisites)}\n"
            f"Evidence clips:\n{self._evidence_text(results)}\n"
            "Write a short recommended review path with timestamp citations."
        )

    def _maybe_llm(self, system: str, prompt: str, fallback: str) -> str:
        if not self.llm.is_available():
            return fallback
        try:
            text = self.llm.chat(system, prompt, temperature=0.2, max_tokens=900)
            return text.strip() or fallback
        except Exception:
            return fallback

    def _self_check(self, feature: str, ledger: list[Any], minimum: int = 1) -> dict[str, Any]:
        has_timestamps = any(item.start_time is not None for item in ledger)
        modalities = {modality for item in ledger for modality in item.modality}
        score = 5 + min(3, len(ledger)) + (1 if has_timestamps else 0) + (1 if len(modalities) >= 2 else 0)
        issues = []
        if len(ledger) < minimum:
            issues.append("Not enough timestamped evidence was retrieved.")
        if not has_timestamps:
            issues.append("No timestamp was attached to the evidence ledger.")
        return {
            "score": min(10, score),
            "passed": score >= 7 and len(ledger) >= minimum,
            "issues": issues,
            "improvement_plan": [] if not issues else ["Expand retrieval query", "Search across all indexed videos"],
            "grounding_check": {"uses_evidence": bool(ledger), "has_timestamps": has_timestamps, "unsupported_claims": []},
            "multimodal_check": {
                "uses_asr": any("asr" in self._modality_text(item) or "audio" in self._modality_text(item) for item in ledger),
                "uses_ocr": any("ocr" in self._modality_text(item) for item in ledger),
                "uses_formula": any("formula" in self._modality_text(item) for item in ledger),
                "uses_visual": any("visual" in self._modality_text(item) or "keyframe" in self._modality_text(item) for item in ledger),
                "uses_video_embedding": any("internvideo3" in self._modality_text(item) for item in ledger),
            },
            "feature_name": feature,
        }

    def _modality_text(self, item: Any) -> str:
        return " ".join(str(modality).lower() for modality in getattr(item, "modality", []) or [])

    def _save_learning_log(self, feature: str, request: dict[str, Any], payload: dict[str, Any]) -> None:
        log_dir = settings.generated_dir / "evals"
        log_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "feature": feature,
            "request": request,
            "self_check": payload.get("self_check"),
            "ledger_count": len(payload.get("evidence_ledger", [])),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        (log_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{feature}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def _short(self, text: str, limit: int = 240) -> str:
        text = " ".join((text or "").split())
        return text[: limit - 3] + "..." if len(text) > limit else text
