from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from ..config import settings
from ..schemas import GraphEdge, GraphNode, GraphRequest, GraphResponse, Lecture, Moment
from ..storage import load_course
from .llm_service import LLMService
from .self_improvement_service import SelfImprovementService


@dataclass(frozen=True)
class MomentContext:
    lecture: Lecture
    moment: Moment
    concepts: list[str]
    formulas: list[str]
    relevance: float


class GraphService:
    """Build a lightweight educational concept graph from indexed lecture evidence."""

    CORE_CONCEPTS = [
        "empirical risk minimization",
        "risk minimization",
        "parameter optimization",
        "gradient descent",
        "stochastic gradient descent",
        "batch gradient",
        "learning rate",
        "step size",
        "negative gradient",
        "stationary point",
        "local minimum",
        "global minimum",
        "hessian",
        "derivative",
        "gradient",
        "loss function",
        "mean squared error",
        "normal equation",
        "linear regression",
        "least squares",
        "bias variance",
        "regularization",
        "ridge regression",
        "lasso",
        "classification",
        "logistic regression",
        "sigmoid",
        "neural network",
        "activation function",
        "relu",
        "chain rule",
        "backpropagation",
        "computational graph",
        "overfitting",
        "underfitting",
        "training data",
        "validation data",
    ]

    PREREQUISITES = [
        ("derivative", "gradient"),
        ("gradient", "gradient descent"),
        ("negative gradient", "gradient descent"),
        ("loss function", "gradient descent"),
        ("learning rate", "gradient descent"),
        ("linear regression", "normal equation"),
        ("mean squared error", "normal equation"),
        ("parameter optimization", "empirical risk minimization"),
        ("chain rule", "backpropagation"),
        ("activation function", "neural network"),
        ("computational graph", "backpropagation"),
        ("regularization", "overfitting"),
    ]

    STOP_CONCEPTS = {
        "introduction to machine learning",
        "machine learning",
        "slide",
        "example",
        "basics",
        "lecture",
        "course",
    }

    def __init__(self) -> None:
        self.llm = LLMService()
        self.improver = SelfImprovementService()

    def generate(self, request: GraphRequest) -> GraphResponse:
        course = load_course(request.course_id)
        lectures = self._resolve_lectures(course.lectures, request)
        contexts = self._collect_contexts(lectures, request)
        selected_contexts = self._select_contexts(contexts, request)
        concept_frequency = Counter(concept for ctx in selected_contexts for concept in ctx.concepts)
        allowed_concepts = self._allowed_concepts(concept_frequency, request)

        nodes: dict[str, GraphNode] = {
            f"course:{course.course_id}": GraphNode(
                id=f"course:{course.course_id}",
                label=course.title,
                type="course",
                metadata={
                    "lecture_count": len(lectures),
                    "moment_count": len(selected_contexts),
                    "concept_count": len(allowed_concepts),
                },
            )
        }
        edges: dict[tuple[str, str, str], GraphEdge] = {}
        concept_to_moments: dict[str, list[MomentContext]] = defaultdict(list)

        for lecture in lectures:
            if not any(ctx.lecture.lecture_id == lecture.lecture_id for ctx in selected_contexts):
                continue
            lecture_id = f"lecture:{lecture.lecture_id}"
            nodes[lecture_id] = GraphNode(
                id=lecture_id,
                label=self._clean_label(lecture.title, 56),
                type="lecture",
                lecture_id=lecture.lecture_id,
                metadata={
                    "duration": lecture.duration,
                    "video_path": lecture.video_path,
                    "moment_count": sum(1 for ctx in selected_contexts if ctx.lecture.lecture_id == lecture.lecture_id),
                },
            )
            self._edge(edges, f"course:{course.course_id}", lecture_id, "contains", 1.0)

        for ctx in selected_contexts:
            lecture_id = f"lecture:{ctx.lecture.lecture_id}"
            moment_node_id = f"moment:{ctx.moment.moment_id}"
            if request.include_moments:
                nodes[moment_node_id] = GraphNode(
                    id=moment_node_id,
                    label=self._moment_label(ctx),
                    type="moment",
                    lecture_id=ctx.lecture.lecture_id,
                    timestamp=ctx.moment.start_time,
                    metadata={
                        "moment_id": ctx.moment.moment_id,
                        "video_id": ctx.moment.video_id or ctx.moment.metadata.get("video_id"),
                        "start_time": ctx.moment.start_time,
                        "end_time": ctx.moment.end_time,
                        "thumbnail_url": ctx.moment.thumbnail_url,
                        "transcript_snippet": self._clean_label(ctx.moment.transcript, 260),
                        "ocr_snippet": self._clean_label(ctx.moment.ocr_text, 260),
                        "visual_caption": self._clean_label(ctx.moment.visual_caption, 180),
                        "relevance": round(ctx.relevance, 3),
                    },
                )
                self._edge(edges, lecture_id, moment_node_id, "contains", 1.0)

            for concept in [concept for concept in ctx.concepts if concept in allowed_concepts][:8]:
                concept_id = f"concept:{self._slug(concept)}"
                examples = [f"{item.moment.start_time:.0f}-{item.moment.end_time:.0f}s" for item in concept_to_moments[concept][:4]]
                nodes.setdefault(
                    concept_id,
                    GraphNode(
                        id=concept_id,
                        label=self._title_concept(concept),
                        type="concept",
                        lecture_id=ctx.lecture.lecture_id,
                        timestamp=ctx.moment.start_time,
                        metadata={
                            "frequency": concept_frequency[concept],
                            "importance": min(1.0, 0.35 + 0.11 * concept_frequency[concept]),
                            "examples": examples,
                            "first_timestamp": ctx.moment.start_time,
                        },
                    ),
                )
                concept_to_moments[concept].append(ctx)
                if request.include_moments:
                    self._edge(edges, concept_id, moment_node_id, "appears_in", self._concept_weight(concept_frequency[concept]))
                else:
                    self._edge(edges, lecture_id, concept_id, "contains", self._concept_weight(concept_frequency[concept]))

            for formula in ctx.formulas[:2]:
                formula_id = f"formula:{self._slug(formula)}"
                nodes.setdefault(
                    formula_id,
                    GraphNode(
                        id=formula_id,
                        label=self._formula_label(formula),
                        type="formula",
                        lecture_id=ctx.lecture.lecture_id,
                        timestamp=ctx.moment.start_time,
                        metadata={
                            "latex": formula,
                            "moment_id": ctx.moment.moment_id,
                            "video_id": ctx.moment.video_id or ctx.moment.metadata.get("video_id"),
                            "thumbnail_url": ctx.moment.thumbnail_url,
                        },
                    ),
                )
                if request.include_moments:
                    self._edge(edges, formula_id, moment_node_id, "appears_in", 0.78)
                else:
                    self._edge(edges, lecture_id, formula_id, "uses_formula", 0.62)
                for concept in [concept for concept in ctx.concepts[:4] if concept in allowed_concepts]:
                    self._edge(edges, f"concept:{self._slug(concept)}", formula_id, "uses_formula", 0.7)

            if request.include_moments and ctx.moment.keyframes:
                frame_id = f"visual:{self._short_hash(ctx.moment.keyframes[0] + ctx.moment.moment_id)}"
                nodes[frame_id] = GraphNode(
                    id=frame_id,
                    label=f"Frame {self._format_time(ctx.moment.start_time)}",
                    type="visual_evidence",
                    lecture_id=ctx.lecture.lecture_id,
                    timestamp=ctx.moment.start_time,
                    metadata={
                        "thumbnail_url": ctx.moment.thumbnail_url,
                        "frame_path": ctx.moment.keyframes[0],
                        "moment_id": ctx.moment.moment_id,
                        "video_id": ctx.moment.video_id or ctx.moment.metadata.get("video_id"),
                    },
                )
                self._edge(edges, frame_id, moment_node_id, "shown_in_frame", 0.58)

        self._add_cooccurrence_edges(edges, concept_to_moments)
        self._add_prerequisites(edges, nodes)
        self._prune_orphans(nodes, edges)
        if self.llm.is_available():
            self._llm_refine(edges, nodes, request)

        metrics = self._metrics(nodes, edges, selected_contexts, allowed_concepts)
        response = GraphResponse(
            nodes=list(nodes.values()),
            edges=list(edges.values()),
            summary=(
                f"Knowledge graph built from {metrics['moment_count']} timestamped moments, "
                f"{metrics['concept_count']} concepts, {metrics['formula_count']} formulas, "
                f"and {metrics['visual_count']} visual evidence nodes."
            ),
            metrics=metrics,
        )
        improved = self.improver.improve_graph(request, response)
        response.self_check = improved["self_check"]
        self._save_graph(request, response, improved["actions_taken"])
        return response

    def _resolve_lectures(self, lectures: list[Lecture], request: GraphRequest) -> list[Lecture]:
        if request.lecture_ids:
            selected = [lecture for lecture in lectures if lecture.lecture_id in request.lecture_ids]
        else:
            selected = list(lectures)
        if not selected and request.video_ids:
            video_ids = set(request.video_ids)
            selected = [
                lecture
                for lecture in lectures
                if any((moment.video_id in video_ids or moment.metadata.get("video_id") in video_ids) for moment in lecture.moments)
            ]
        if not selected:
            selected = list(lectures)
        return selected

    def _collect_contexts(self, lectures: list[Lecture], request: GraphRequest) -> list[MomentContext]:
        focus_terms = self._focus_terms(request.focus_topic)
        contexts: list[MomentContext] = []
        for lecture in lectures:
            for moment in lecture.moments:
                if request.video_ids and moment.video_id not in request.video_ids and moment.metadata.get("video_id") not in request.video_ids:
                    continue
                text = self._moment_text(moment)
                if focus_terms and not any(term in text.lower() for term in focus_terms):
                    continue
                concepts = self._concepts(moment)
                formulas = self._extract_formulas(moment)
                relevance = self._relevance(text, concepts, formulas, focus_terms)
                contexts.append(MomentContext(lecture=lecture, moment=moment, concepts=concepts, formulas=formulas, relevance=relevance))
        return contexts

    def _select_contexts(self, contexts: list[MomentContext], request: GraphRequest) -> list[MomentContext]:
        if not contexts:
            return []
        max_moments = max(8, min(80, request.max_moments))
        if len(contexts) <= max_moments:
            return contexts
        ranked = sorted(contexts, key=lambda ctx: (ctx.relevance, len(ctx.concepts), len(ctx.formulas)), reverse=True)
        selected = ranked[:max_moments]
        return sorted(selected, key=lambda ctx: (ctx.lecture.lecture_id, ctx.moment.start_time))

    def _allowed_concepts(self, concept_frequency: Counter[str], request: GraphRequest) -> set[str]:
        max_concepts = max(8, min(60, request.max_concepts))
        allowed = {concept for concept, _ in concept_frequency.most_common(max_concepts)}
        for term in self._focus_terms(request.focus_topic):
            for concept in concept_frequency:
                if term in concept or concept in term:
                    allowed.add(concept)
        return allowed

    def _concepts(self, moment: Moment) -> list[str]:
        text = self._moment_text(moment).lower()
        concepts = [self._normalize_concept(concept) for concept in moment.concept_tags]
        for phrase in self.CORE_CONCEPTS:
            if phrase in text:
                concepts.append(phrase)
        concepts.extend(self._slide_title_concepts(text))
        concepts.extend(self._ngram_concepts(text))
        return self._dedupe_concepts(concepts)[:14]

    def _moment_text(self, moment: Moment) -> str:
        return " ".join([moment.transcript, moment.ocr_text, moment.formula_latex, moment.visual_caption, " ".join(moment.concept_tags)])

    def _slide_title_concepts(self, text: str) -> list[str]:
        concepts: list[str] = []
        title_aliases = {
            "learning as parameter optimization": ["parameter optimization", "empirical risk minimization"],
            "local minima and stationary points": ["local minimum", "stationary point", "hessian"],
            "gradient descent - learning rate": ["gradient descent", "learning rate"],
            "gradient descent - example": ["gradient descent", "negative gradient"],
            "gradient descent": ["gradient descent"],
            "optimization problem": ["parameter optimization", "empirical risk minimization"],
        }
        for title, mapped in title_aliases.items():
            if title in text:
                concepts.extend(mapped)
        return concepts

    def _ngram_concepts(self, text: str) -> list[str]:
        phrases: list[str] = []
        patterns = [
            r"\b(local minima?|global minima?|stationary points?|hessian|gradient|risk function|empirical risk|parameter optimization)\b",
            r"\b(learning rate|step size|negative gradient|stochastic gradient descent|batch gradient descent|risk minimizer)\b",
            r"\b(normal equation|least squares|mean squared error|activation function|chain rule|backpropagation)\b",
        ]
        for pattern in patterns:
            phrases.extend(match.group(0) for match in re.finditer(pattern, text, flags=re.IGNORECASE))
        return [self._normalize_concept(phrase) for phrase in phrases]

    def _dedupe_concepts(self, concepts: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        clean: list[str] = []
        aliases = {
            "local minima": "local minimum",
            "global minima": "global minimum",
            "stationary points": "stationary point",
            "gradient descent example": "gradient descent",
            "gradient descent learning rate": "learning rate",
            "learning as parameter optimization": "parameter optimization",
            "ml basics optimization": "parameter optimization",
            "erm optimization problem": "empirical risk minimization",
        }
        for concept in concepts:
            normalized = aliases.get(self._normalize_concept(concept), self._normalize_concept(concept))
            if not normalized or normalized in self.STOP_CONCEPTS or len(normalized) < 3:
                continue
            if normalized not in seen:
                seen.add(normalized)
                clean.append(normalized)
        return clean

    def _extract_formulas(self, moment: Moment) -> list[str]:
        text = " ".join([moment.formula_latex, moment.ocr_text])
        if not text.strip():
            return []
        formulas: list[str] = []
        known = [
            r"θ\[t\+1\]\s*=\s*θ\[t\]\s*[−-]\s*α[^.;\n]{0,90}",
            r"dR(?:emp)?\s*/?\s*dθ[^.;\n]{0,90}",
            r"\^\s*θ\s*=\s*arg\s*min[^.;\n]{0,120}",
            r"0\s*gradient[^.;\n]{0,80}",
            r"\\frac\{[^}]+\}\{[^}]+\}[^.;\n]{0,90}",
            r"\\mathrm\{[^}]+\}[^.;\n]{0,70}",
        ]
        for pattern in known:
            formulas.extend(match.group(0) for match in re.finditer(pattern, text, flags=re.IGNORECASE))

        math_lines = []
        for chunk in re.split(r"(?:Slide\s+\d+:|©|\n|\.)", text):
            cleaned = self._clean_label(chunk, 140)
            if self._looks_like_formula(cleaned):
                math_lines.append(cleaned)
        formulas.extend(math_lines)
        return self._dedupe_formulas(formulas)[:4]

    def _looks_like_formula(self, text: str) -> bool:
        if len(text) < 6 or len(text) > 160:
            return False
        has_math_symbol = any(symbol in text for symbol in ["=", "∇", "≤", "≥", "\\frac", "arg min", "dθ", "θ[t+1]"])
        word_count = len(re.findall(r"[A-Za-z]{3,}", text))
        return has_math_symbol and word_count < 16

    def _dedupe_formulas(self, formulas: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        clean: list[str] = []
        for formula in formulas:
            normalized = self._clean_formula(formula)
            key = re.sub(r"\s+", "", normalized.lower())
            if len(normalized) < 6 or key in seen or not self._looks_like_formula(normalized):
                continue
            seen.add(key)
            clean.append(normalized)
        return clean

    def _clean_formula(self, formula: str) -> str:
        extraction_patterns = [
            r"(ˆ?θ\s*=\s*arg\s*min[^.;\n]{0,120})",
            r"(θ\[t\+1\]\s*=\s*[^.;\n]{0,120})",
            r"(dR(?:emp)?\s*/?\s*dθ[^.;\n]{0,110})",
            r"(∀θ\s*∈\s*Θ[^.;\n]{0,100})",
        ]
        for pattern in extraction_patterns:
            match = re.search(pattern, formula, flags=re.IGNORECASE)
            if match:
                formula = match.group(1)
                break
        formula = formula.replace("−", "-")
        formula = re.sub(r"©.*", "", formula)
        formula = re.sub(r"\s+", " ", formula).strip(" ;,:")
        return self._clean_label(formula, 110)

    def _add_cooccurrence_edges(self, edges: dict[tuple[str, str, str], GraphEdge], concept_to_moments: dict[str, list[MomentContext]]) -> None:
        moment_to_concepts: dict[str, list[str]] = defaultdict(list)
        for concept, contexts in concept_to_moments.items():
            for ctx in contexts:
                moment_to_concepts[ctx.moment.moment_id].append(concept)
        pair_counts: Counter[tuple[str, str]] = Counter()
        for concepts in moment_to_concepts.values():
            unique = sorted(set(concepts))
            for i, left in enumerate(unique):
                for right in unique[i + 1 :]:
                    pair_counts[(left, right)] += 1
        for (left, right), count in pair_counts.most_common(42):
            self._edge(
                edges,
                f"concept:{self._slug(left)}",
                f"concept:{self._slug(right)}",
                "related_to",
                min(1.0, 0.32 + 0.12 * count),
                {"cooccurrence_count": count},
            )

    def _add_prerequisites(self, edges: dict[tuple[str, str, str], GraphEdge], nodes: dict[str, GraphNode]) -> None:
        for source, target in self.PREREQUISITES:
            source_id = f"concept:{self._slug(source)}"
            target_id = f"concept:{self._slug(target)}"
            if source_id in nodes and target_id in nodes:
                self._edge(edges, source_id, target_id, "prerequisite_of", 0.9, {"heuristic": True})

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

    def _prune_orphans(self, nodes: dict[str, GraphNode], edges: dict[tuple[str, str, str], GraphEdge]) -> None:
        connected = {edge.source for edge in edges.values()} | {edge.target for edge in edges.values()}
        for node_id in list(nodes.keys()):
            if nodes[node_id].type != "course" and node_id not in connected:
                nodes.pop(node_id, None)
        for key, edge in list(edges.items()):
            if edge.source not in nodes or edge.target not in nodes:
                edges.pop(key, None)

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
            {"nodes": len(response.nodes), "edges": len(response.edges), "metrics": response.metrics},
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
        if source == target:
            return
        key = (source, target, edge_type)
        if key not in edges:
            edges[key] = GraphEdge(source=source, target=target, type=edge_type, weight=round(weight, 3), metadata=metadata or {})

    def _metrics(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[tuple[str, str, str], GraphEdge],
        contexts: list[MomentContext],
        allowed_concepts: set[str],
    ) -> dict[str, Any]:
        node_counts = Counter(node.type for node in nodes.values())
        edge_counts = Counter(edge.type for edge in edges.values())
        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "concept_count": node_counts.get("concept", 0),
            "formula_count": node_counts.get("formula", 0),
            "moment_count": node_counts.get("moment", len(contexts)),
            "visual_count": node_counts.get("visual_evidence", 0),
            "allowed_concept_count": len(allowed_concepts),
            "node_types": dict(node_counts),
            "edge_types": dict(edge_counts),
        }

    def _relevance(self, text: str, concepts: list[str], formulas: list[str], focus_terms: list[str]) -> float:
        base = 0.25 + 0.08 * len(concepts) + 0.1 * len(formulas)
        if focus_terms:
            lower = text.lower()
            base += 0.55 * sum(1 for term in focus_terms if term in lower)
        return min(1.0, base)

    def _focus_terms(self, focus: str | None) -> list[str]:
        if not focus:
            return []
        terms = [self._normalize_concept(part) for part in re.split(r"[,;/]|\band\b", focus.lower())]
        return [term for term in terms if len(term) >= 3]

    def _concept_weight(self, count: int) -> float:
        return min(1.0, 0.52 + 0.08 * count)

    def _normalize_concept(self, text: str) -> str:
        text = re.sub(r"[^a-zA-Z0-9+\-/ ]+", " ", text.lower())
        text = re.sub(r"\s+", " ", text).strip(" -/")
        text = re.sub(r"^\d+\s*", "", text)
        return text

    def _title_concept(self, concept: str) -> str:
        keep_upper = {"sgd": "SGD", "relu": "ReLU"}
        return " ".join(keep_upper.get(part, part.capitalize()) for part in concept.split())

    def _moment_label(self, ctx: MomentContext) -> str:
        concept = ctx.concepts[0] if ctx.concepts else "moment"
        return f"{self._format_time(ctx.moment.start_time)}-{self._format_time(ctx.moment.end_time)} · {self._title_concept(concept)}"

    def _formula_label(self, latex: str) -> str:
        return self._clean_label(latex, 64)

    def _clean_label(self, text: str, max_len: int) -> str:
        cleaned = re.sub(r"\s+", " ", str(text or "")).replace("©", "").strip()
        if len(cleaned) <= max_len:
            return cleaned
        return cleaned[:max_len].rsplit(" ", 1)[0] + "..."

    def _format_time(self, seconds: float) -> str:
        seconds = max(0, int(seconds))
        return f"{seconds // 60}:{seconds % 60:02d}"

    def _slug(self, text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
        return slug[:90] or self._short_hash(text)

    def _short_hash(self, text: str) -> str:
        return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]
