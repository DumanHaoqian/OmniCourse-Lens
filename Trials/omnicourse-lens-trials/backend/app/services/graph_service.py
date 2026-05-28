from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from typing import Any

from ..config import settings
from ..schemas import GraphEdge, GraphNode, GraphRequest, GraphResponse, Moment
from ..storage import load_course
from .llm_service import LLMService
from .self_improvement_service import SelfImprovementService


class GraphService:
    def __init__(self) -> None:
        self.llm = LLMService()
        self.improver = SelfImprovementService()

    def generate(self, request: GraphRequest) -> GraphResponse:
        course = load_course(request.course_id)
        lectures = [lecture for lecture in course.lectures if lecture.lecture_id in request.lecture_ids]
        nodes: dict[str, GraphNode] = {
            f"course:{course.course_id}": GraphNode(id=f"course:{course.course_id}", label=course.title, type="course")
        }
        edges: dict[tuple[str, str, str], GraphEdge] = {}
        concept_to_moments: dict[str, list[Moment]] = defaultdict(list)
        focus = (request.focus_topic or "").lower().strip()

        for lecture in lectures:
            lecture_id = f"lecture:{lecture.lecture_id}"
            nodes[lecture_id] = GraphNode(id=lecture_id, label=lecture.title, type="lecture", lecture_id=lecture.lecture_id)
            self._edge(edges, f"course:{course.course_id}", lecture_id, "contains", 1.0)
            for moment in lecture.moments:
                if focus and focus not in self._moment_text(moment).lower():
                    continue
                moment_id = f"moment:{moment.moment_id}"
                nodes[moment_id] = GraphNode(
                    id=moment_id,
                    label=f"{lecture.title} {moment.start_time:.0f}-{moment.end_time:.0f}s",
                    type="moment",
                    lecture_id=lecture.lecture_id,
                    timestamp=moment.start_time,
                    metadata={"thumbnail_url": moment.thumbnail_url, "moment_id": moment.moment_id},
                )
                self._edge(edges, lecture_id, moment_id, "contains", 1.0)
                concepts = self._concepts(moment)
                for concept in concepts:
                    concept_id = f"concept:{self._slug(concept)}"
                    nodes.setdefault(concept_id, GraphNode(id=concept_id, label=concept.title(), type="concept"))
                    self._edge(edges, concept_id, moment_id, "appears_in", 0.9)
                    self._edge(edges, moment_id, concept_id, "explained_by", 0.5)
                    concept_to_moments[concept].append(moment)
                if moment.formula_latex:
                    formula_id = f"formula:{self._slug(moment.formula_latex[:50])}"
                    nodes.setdefault(
                        formula_id,
                        GraphNode(
                            id=formula_id,
                            label=self._formula_label(moment.formula_latex),
                            type="formula",
                            lecture_id=lecture.lecture_id,
                            timestamp=moment.start_time,
                            metadata={"latex": moment.formula_latex},
                        ),
                    )
                    self._edge(edges, formula_id, moment_id, "appears_in", 0.8)
                    for concept in concepts[:3]:
                        self._edge(edges, f"concept:{self._slug(concept)}", formula_id, "uses_formula", 0.7)
                for frame in moment.keyframes[:1]:
                    frame_id = f"visual:{self._slug(frame)}"
                    nodes.setdefault(
                        frame_id,
                        GraphNode(
                            id=frame_id,
                            label=f"Keyframe {moment.start_time:.0f}s",
                            type="visual_evidence",
                            lecture_id=lecture.lecture_id,
                            timestamp=moment.start_time,
                            metadata={"thumbnail_url": moment.thumbnail_url, "frame_path": frame},
                        ),
                    )
                    self._edge(edges, frame_id, moment_id, "shown_in_frame", 0.6)

        self._add_cooccurrence_edges(edges, concept_to_moments)
        self._add_prerequisites(edges, nodes)
        if self.llm.is_available():
            self._llm_refine(edges, nodes, request)

        response = GraphResponse(
            nodes=list(nodes.values()),
            edges=list(edges.values()),
            summary=f"Built a lightweight course graph with {len(nodes)} nodes and {len(edges)} edges from {len(lectures)} lectures.",
        )
        improved = self.improver.improve_graph(request, response)
        response.self_check = improved["self_check"]
        self._save_graph(request, response, improved["actions_taken"])
        return response

    def _concepts(self, moment: Moment) -> list[str]:
        concepts = list(moment.concept_tags)
        text = self._moment_text(moment).lower()
        candidates = [
            "derivative",
            "loss function",
            "gradient descent",
            "learning rate",
            "linear regression",
            "normal equation",
            "mean squared error",
            "neural network",
            "activation function",
            "chain rule",
            "backpropagation",
        ]
        for candidate in candidates:
            if candidate in text and candidate not in concepts:
                concepts.append(candidate)
        return concepts[:8]

    def _moment_text(self, moment: Moment) -> str:
        return " ".join([moment.transcript, moment.ocr_text, moment.formula_latex, moment.visual_caption, " ".join(moment.concept_tags)])

    def _add_cooccurrence_edges(self, edges: dict[tuple[str, str, str], GraphEdge], concept_to_moments: dict[str, list[Moment]]) -> None:
        moment_to_concepts: dict[str, list[str]] = defaultdict(list)
        for concept, moments in concept_to_moments.items():
            for moment in moments:
                moment_to_concepts[moment.moment_id].append(concept)
        pair_counts: Counter[tuple[str, str]] = Counter()
        for concepts in moment_to_concepts.values():
            for i, left in enumerate(concepts):
                for right in concepts[i + 1 :]:
                    pair_counts[tuple(sorted([left, right]))] += 1
        for (left, right), count in pair_counts.items():
            self._edge(edges, f"concept:{self._slug(left)}", f"concept:{self._slug(right)}", "related_to", min(1.0, 0.35 + 0.15 * count))

    def _add_prerequisites(self, edges: dict[tuple[str, str, str], GraphEdge], nodes: dict[str, GraphNode]) -> None:
        pairs = [
            ("derivative", "gradient descent"),
            ("chain rule", "backpropagation"),
            ("loss function", "gradient descent"),
            ("linear regression", "normal equation"),
            ("activation function", "neural network"),
        ]
        for source, target in pairs:
            source_id = f"concept:{self._slug(source)}"
            target_id = f"concept:{self._slug(target)}"
            if source_id in nodes and target_id in nodes:
                self._edge(edges, source_id, target_id, "prerequisite_of", 0.85, {"heuristic": True})

    def _llm_refine(self, edges: dict[tuple[str, str, str], GraphEdge], nodes: dict[str, GraphNode], request: GraphRequest) -> None:
        labels = [node.label for node in nodes.values() if node.type == "concept"][:40]
        prompt = (
            "Given these concept labels from lecture evidence, return strict JSON with optional prerequisite_edges "
            "as pairs of existing labels. Keep it small.\n"
            f"Focus: {request.focus_topic or 'all'}\nLabels: {labels}"
        )
        data = self.llm.chat_json(
            "You refine a lightweight educational concept graph. Keep labels short and add only plausible prerequisite edges supported by lecture evidence.",
            prompt,
            temperature=0.1,
            max_tokens=800,
        )
        for pair in data.get("prerequisite_edges", []) if isinstance(data, dict) else []:
            if not isinstance(pair, list) or len(pair) != 2:
                continue
            source_id = f"concept:{self._slug(str(pair[0]).lower())}"
            target_id = f"concept:{self._slug(str(pair[1]).lower())}"
            if source_id in nodes and target_id in nodes:
                self._edge(edges, source_id, target_id, "prerequisite_of", 0.75, {"llm_refined": True})

    def _save_graph(self, request: GraphRequest, response: GraphResponse, actions_taken: list[str]) -> None:
        out_dir = settings.generated_dir / "graphs"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        payload = response.model_dump(mode="json")
        payload["actions_taken"] = actions_taken
        (out_dir / f"{request.course_id}_{stamp}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.improver.evaluator.save_log(
            "knowledge_graph",
            request,
            {"nodes": len(response.nodes), "edges": len(response.edges)},
            response.self_check or {},
            actions_taken,
        )

    def _edge(
        self,
        edges: dict[tuple[str, str, str], GraphEdge],
        source: str,
        target: str,
        edge_type: str,
        weight: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        key = (source, target, edge_type)
        if key not in edges:
            edges[key] = GraphEdge(source=source, target=target, type=edge_type, weight=weight, metadata=metadata or {})

    def _slug(self, text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
        return slug[:80] or "node"

    def _formula_label(self, latex: str) -> str:
        latex = " ".join(latex.split())
        return latex[:55] + "..." if len(latex) > 58 else latex
