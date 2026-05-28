from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..config import settings
from ..schemas import SearchRequest, SearchResult
from ..storage import list_courses, static_url
from .embedding_service import EmbeddingService, normalize_text
from .internvideo3_service import InternVideo3Service
from .ocr_service import OCRService
from .self_improvement_service import SelfImprovementService


class SearchService:
    def __init__(self) -> None:
        self.embedding = EmbeddingService()
        self.ocr = OCRService()
        self.internvideo3 = InternVideo3Service()
        self.improver = SelfImprovementService()
        self._cache: dict[str, Any] | None = None
        self._cache_signature: dict[str, float | None] | None = None

    def describe_provider(self) -> dict[str, Any]:
        return {
            "search": "hybrid_json_index",
            "embedding": self.embedding.describe_provider(),
            "ocr": self.ocr.describe_provider(),
            "internvideo3": self.internvideo3.describe_provider(),
        }

    def text_search(self, request: SearchRequest) -> dict[str, Any]:
        results = self._rank(request.course_id, request.query, request.lecture_ids, request.video_ids, request.top_k, image_path=None, image_ocr_text="")
        improved = self.improver.improve_search(
            request.query,
            results,
            context={
                "rerun": lambda query: self._rank(
                    request.course_id,
                    f"{query} {self._broad_expansion(query)}",
                    request.lecture_ids,
                    request.video_ids,
                    request.top_k,
                    image_path=None,
                    image_ocr_text="",
                )
            },
        )
        return {"results": improved["results"], "self_check": improved["self_check"], "provider_status": self.describe_provider()}

    def image_search(
        self,
        course_id: str,
        image_path: str,
        text_query: str = "",
        lecture_ids: list[str] | None = None,
        video_ids: list[str] | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        ocr_result = self.ocr.ocr_image(image_path)
        image_ocr_text = ocr_result.get("text", "")
        composed_query = " ".join(part for part in [text_query, image_ocr_text] if part).strip()
        results = self._rank(course_id, composed_query, lecture_ids, video_ids, top_k, image_path=image_path, image_ocr_text=image_ocr_text)
        improved = self.improver.improve_search(
            composed_query or text_query or "image query",
            results,
            context={
                "rerun": lambda query: self._rank(
                    course_id,
                    f"{query} {image_ocr_text}",
                    lecture_ids,
                    video_ids,
                    top_k,
                    image_path=image_path,
                    image_ocr_text=image_ocr_text,
                )
            },
        )
        return {
            "results": improved["results"],
            "image_ocr": ocr_result,
            "self_check": improved["self_check"],
            "provider_status": self.describe_provider(),
        }

    def _rank(
        self,
        course_id: str,
        query: str,
        lecture_ids: list[str] | None,
        video_ids: list[str] | None,
        top_k: int,
        image_path: str | None,
        image_ocr_text: str,
    ) -> list[SearchResult]:
        index = self._load_index()
        moments = [
            moment
            for moment in index["moments"]
            if moment.get("course_id") == course_id
            and (not lecture_ids or moment.get("lecture_id") in lecture_ids)
            and (not video_ids or moment.get("video_id") in video_ids or moment.get("metadata", {}).get("video_id") in video_ids)
        ]
        if not moments:
            self._ensure_index(force=True)
            index = self._load_index(force=True)
            moments = [
                moment
                for moment in index["moments"]
                if moment.get("course_id") == course_id
                and (not lecture_ids or moment.get("lecture_id") in lecture_ids)
                and (not video_ids or moment.get("video_id") in video_ids or moment.get("metadata", {}).get("video_id") in video_ids)
            ]
        query = self._expand_query(query)
        image_descriptor = self.embedding.image_descriptor(image_path) if image_path else None
        query_dense = self.embedding.dense_text_embedding(query)
        scored = []
        for moment in moments:
            breakdown = self._score_moment(moment, query, index, image_descriptor, image_ocr_text, query_dense)
            final_score = self._weighted_score(breakdown, image_mode=bool(image_path))
            result = self._to_result(moment, final_score, breakdown)
            scored.append(result)
        scored.sort(key=lambda item: item.score, reverse=True)
        scored = self._rerank_with_internvideo3(query, scored, moments, image_mode=bool(image_path))
        return scored[: max(1, min(top_k, 20))]

    def _score_moment(
        self,
        moment: dict[str, Any],
        query: str,
        index: dict[str, Any],
        image_descriptor: list[float] | None,
        image_ocr_text: str,
        query_dense: list[float],
    ) -> dict[str, float]:
        transcript = moment.get("transcript", "")
        ocr_text = moment.get("ocr_text", "")
        formula = moment.get("formula_latex", "")
        concepts = " ".join(moment.get("concept_tags", []))
        visual = moment.get("visual_caption", "")
        document = "\n".join([transcript, ocr_text, formula, concepts, visual, moment.get("lecture_title", "")])
        lexical = self.embedding.lexical_relevance
        idf = index.get("lexical", {}).get("idf", {})
        moment_idx = self._moment_index(index, moment.get("moment_id"))
        doc_vector = index.get("lexical", {}).get("docs", [{}])[moment_idx]
        sparse_text_score = self.embedding.sparse_cosine(self.embedding.text_sparse_vector(query, idf), doc_vector)
        dense_vectors = index.get("dense_text_embeddings", [])
        dense_text_score = 0.0
        if query_dense and moment_idx < len(dense_vectors):
            dense_text_score = self.embedding.dense_similarity(query_dense, dense_vectors[moment_idx])
        if dense_text_score <= 0:
            dense_text_score = sparse_text_score
        image_visual_score = 0.0
        if image_descriptor:
            frame_descriptors = index.get("image_descriptors", {})
            sims = [self.embedding.vector_similarity(image_descriptor, frame_descriptors.get(frame, [])) for frame in moment.get("keyframes", [])]
            image_visual_score = max(sims) if sims else 0.0
        intern_score = None
        if self._inline_internvideo3_enabled():
            intern_score = self.internvideo3.score_text_video(
                query=query,
                video_path=moment.get("video_path") or "",
                start_time=float(moment.get("start_time") or 0),
                end_time=float(moment.get("end_time") or 0),
                keyframe_paths=moment.get("keyframes", []),
            )
        return {
            "audio_transcript": lexical(query, transcript),
            "ocr_text": lexical(query, ocr_text),
            "formula": max(lexical(query, formula), self._formula_alias_score(query, formula)),
            "dense_text": dense_text_score,
            "concept_tag": lexical(query, concepts),
            "internvideo3": intern_score if intern_score is not None else 0.0,
            "image_visual": image_visual_score,
            "image_ocr_text": lexical(image_ocr_text or query, document) if image_descriptor else 0.0,
        }

    def _rerank_with_internvideo3(
        self,
        query: str,
        scored: list[SearchResult],
        moments: list[dict[str, Any]],
        image_mode: bool,
    ) -> list[SearchResult]:
        provider = self.internvideo3.describe_provider()
        if provider.get("mode") != "local_hf_lazy" or not provider.get("local_search_rerank"):
            return scored
        moment_by_id = {moment.get("moment_id"): moment for moment in moments}
        max_calls = int(os.getenv("INTERNVIDEO3_LOCAL_RERANK_TOP_N", "1"))
        for result in scored[: max(0, min(max_calls, 5))]:
            moment = moment_by_id.get(result.moment_id)
            if not moment:
                continue
            score = self.internvideo3.score_text_video(
                query=query,
                video_path=moment.get("video_path") or "",
                start_time=float(moment.get("start_time") or 0),
                end_time=float(moment.get("end_time") or 0),
                keyframe_paths=moment.get("keyframes", []),
            )
            if score is None:
                continue
            result.score_breakdown["internvideo3"] = round(score, 4)
            result.score = self._weighted_score(result.score_breakdown, image_mode=image_mode)
            if "InternVideo3" not in result.matched_modalities and score >= 0.18:
                result.matched_modalities.append("InternVideo3")
            if score >= max(result.score_breakdown.values()):
                result.matched_reason = "InternVideo3 video relevance: local clip-level model reranked this timestamp for the query."
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored

    def _inline_internvideo3_enabled(self) -> bool:
        status = self.internvideo3.describe_provider()
        return status.get("mode") in {"http", "cli"}

    def _weighted_score(self, breakdown: dict[str, float], image_mode: bool) -> float:
        if image_mode:
            weights = {
                "image_visual": 0.20,
                "image_ocr_text": 0.20,
                "ocr_text": 0.15,
                "formula": 0.15,
                "dense_text": 0.10,
                "concept_tag": 0.10,
                "internvideo3": 0.10,
            }
        else:
            weights = {
                "audio_transcript": 0.30,
                "ocr_text": 0.20,
                "formula": 0.15,
                "dense_text": 0.15,
                "concept_tag": 0.10,
                "internvideo3": 0.10,
            }
        active = {key: weight for key, weight in weights.items() if key != "internvideo3" or breakdown.get("internvideo3", 0.0) > 0}
        weight_sum = sum(active.values()) or 1.0
        score = sum((active[key] / weight_sum) * breakdown.get(key, 0.0) for key in active)
        return round(max(0.0, min(1.0, score)), 4)

    def _to_result(self, moment: dict[str, Any], score: float, breakdown: dict[str, float]) -> SearchResult:
        lecture_title = moment.get("lecture_title") or moment.get("lecture_id", "")
        modalities = [self._modality_name(key, moment) for key, value in breakdown.items() if value >= 0.18]
        if not modalities:
            modalities = [self._modality_name(max(breakdown, key=breakdown.get), moment)]
        reason = self._matched_reason(moment, breakdown)
        video_id = moment.get("video_id") or moment.get("metadata", {}).get("video_id")
        video_url = f"/api/dataset/videos/{video_id}/stream" if video_id else static_url(moment.get("video_path"))
        return SearchResult(
            moment_id=moment["moment_id"],
            video_id=video_id,
            course_id=moment["course_id"],
            lecture_id=moment["lecture_id"],
            lecture_title=lecture_title,
            start_time=float(moment["start_time"]),
            end_time=float(moment["end_time"]),
            score=score,
            score_breakdown={key: round(float(value), 4) for key, value in breakdown.items()},
            matched_reason=reason,
            matched_modalities=modalities,
            transcript_snippet=self._snippet(moment.get("transcript", "")),
            ocr_snippet=self._snippet(moment.get("ocr_text", "")),
            formula_latex=moment.get("formula_latex", ""),
            concept_tags=moment.get("concept_tags", []),
            thumbnail_url=moment.get("thumbnail_url") or static_url(moment.get("keyframes", [None])[0]),
            video_url=video_url,
        )

    def _matched_reason(self, moment: dict[str, Any], breakdown: dict[str, float]) -> str:
        best = max(breakdown, key=breakdown.get)
        if best == "audio_transcript":
            transcript_label = self._transcript_label(moment)
            return f"{transcript_label} match: {self._snippet(self._preferred_transcript_text(moment), 160)}"
        if best in {"ocr_text", "image_ocr_text"}:
            return f"{self._ocr_label(moment)} match: {self._snippet(moment.get('ocr_text', '') or moment.get('visual_caption', ''), 160)}"
        if best == "formula":
            return f"Formula match: {moment.get('formula_latex', '')}"
        if best == "concept_tag":
            return f"Concept tag match: {', '.join(moment.get('concept_tags', [])[:4])}"
        if best == "image_visual":
            return "Visual similarity: uploaded image resembles this lecture keyframe."
        if best == "internvideo3":
            return "InternVideo3 video relevance: clip-level signal matched the query."
        return f"Multimodal evidence match: {self._snippet(moment.get('visual_caption', ''), 160)}"

    def _snippet(self, text: str, max_chars: int = 220) -> str:
        text = " ".join((text or "").split())
        return text[: max_chars - 3] + "..." if len(text) > max_chars else text

    def _formula_alias_score(self, query: str, formula: str) -> float:
        alias_text = normalize_text(formula)
        aliases = {
            "gradient descent": ["theta", "alpha", "gradient", "nabla"],
            "learning rate": ["alpha"],
            "normal equation": ["transpose", "inverse", "x"],
            "mean squared error": ["mse", "sum", "squared"],
            "backpropagation": ["chain", "partial", "delta"],
        }
        query_norm = normalize_text(query)
        hits = 0
        total = 0
        for phrase, terms in aliases.items():
            if phrase in query_norm:
                total += len(terms)
                hits += sum(1 for term in terms if term in alias_text)
        return min(1.0, hits / total) if total else 0.0

    def _expand_query(self, query: str) -> str:
        expansions = {
            "gradient descent": "theta alpha nabla loss update step opposite gradient",
            "normal equation": "closed form linear regression X transpose inverse",
            "chain rule": "derivative composition backpropagation partial",
            "learning rate": "alpha step size convergence divergence",
            "loss function": "objective cost error mean squared mse",
            "activation function": "relu sigmoid nonlinearity neural network",
        }
        lower = normalize_text(query)
        extras = [text for key, text in expansions.items() if key in lower]
        return " ".join([query, *extras]).strip()

    def _broad_expansion(self, query: str) -> str:
        lower = normalize_text(query)
        if "gradient" in lower:
            return "descent learning rate loss function update rule"
        if "normal" in lower:
            return "linear regression closed form matrix equation"
        if "network" in lower or "backprop" in lower:
            return "activation function chain rule neural network"
        return "lecture formula slide concept transcript visual evidence"

    def _modality_name(self, key: str, moment: dict[str, Any] | None = None) -> str:
        mapping = {
            "audio_transcript": self._transcript_label(moment or {}) if moment is not None else "Audio transcript",
            "ocr_text": self._ocr_label(moment or {}) if moment is not None else "OCR",
            "formula": "Formula",
            "dense_text": "Text embedding",
            "concept_tag": "Concept tag",
            "internvideo3": "InternVideo3",
            "image_visual": "Image visual",
            "image_ocr_text": "Image OCR",
        }
        return mapping.get(key, key)

    def _transcript_label(self, moment: dict[str, Any]) -> str:
        providers = {segment.get("provider") for segment in moment.get("asr_segments", []) if isinstance(segment, dict)}
        if any(provider and ("whisper" in provider or provider == "transcript_file") for provider in providers):
            return "Audio transcript"
        if "slide_pdf_text" in providers:
            return "Slide/PDF text"
        if "fallback_asr" in providers:
            return "Fallback ASR"
        return "Audio transcript"

    def _ocr_label(self, moment: dict[str, Any]) -> str:
        providers = {block.get("provider") for block in moment.get("ocr_blocks", []) if isinstance(block, dict)}
        if "deepseek_ocr" in providers:
            return "DeepSeek frame OCR"
        if any(provider in {"tesseract", "paddleocr", "easyocr"} for provider in providers):
            return "Frame OCR"
        if "slide_pdf_text" in providers:
            return "Slide/PDF OCR"
        if "demo_ocr" in providers:
            return "Demo OCR"
        if "empty_ocr" in providers:
            return "OCR unavailable"
        return "OCR"

    def _preferred_transcript_text(self, moment: dict[str, Any]) -> str:
        segments = moment.get("asr_segments", [])
        useful = [
            segment.get("text", "")
            for segment in segments
            if isinstance(segment, dict) and segment.get("provider") not in {"fallback_asr"} and segment.get("text")
        ]
        if useful:
            return " ".join(useful)
        return moment.get("transcript", "")

    def _load_index(self, force: bool = False) -> dict[str, Any]:
        signature = self._index_signature()
        if self._cache is not None and not force and self._cache_signature == signature:
            return self._cache
        index = {
            "moments": self._read_json(settings.indexes_dir / "moments.json", []),
            "lexical": self._read_json(settings.indexes_dir / "lexical_index.json", {"idf": {}, "docs": []}),
            "image_descriptors": self._read_json(settings.indexes_dir / "image_descriptors.json", {}),
            "dense_text_embeddings": self._read_json(settings.indexes_dir / "dense_text_embeddings.json", []),
        }
        index["moment_positions"] = {moment.get("moment_id"): idx for idx, moment in enumerate(index["moments"])}
        self._cache = index
        self._cache_signature = signature
        return index

    def _moment_index(self, index: dict[str, Any], moment_id: str | None) -> int:
        return int(index.get("moment_positions", {}).get(moment_id, 0))

    def _ensure_index(self, force: bool = False) -> None:
        if not force and (settings.indexes_dir / "moments.json").exists():
            return
        script = settings.project_root / "scripts" / "rebuild_index.py"
        if script.exists():
            subprocess.run([sys.executable, str(script)], cwd=settings.project_root, check=False)
            self._cache = None
            self._cache_signature = None

    def _index_signature(self) -> dict[str, float | None]:
        paths = {
            "moments": settings.indexes_dir / "moments.json",
            "lexical": settings.indexes_dir / "lexical_index.json",
            "image_descriptors": settings.indexes_dir / "image_descriptors.json",
            "dense_text_embeddings": settings.indexes_dir / "dense_text_embeddings.json",
        }
        return {name: path.stat().st_mtime if path.exists() else None for name, path in paths.items()}

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def all_courses_summary(self) -> list[dict[str, Any]]:
        courses = []
        for course in list_courses():
            courses.append(
                {
                    "course_id": course.course_id,
                    "title": course.title,
                    "description": course.description,
                    "lecture_count": len(course.lectures),
                    "moment_count": sum(len(lecture.moments) for lecture in course.lectures),
                }
            )
        return courses
