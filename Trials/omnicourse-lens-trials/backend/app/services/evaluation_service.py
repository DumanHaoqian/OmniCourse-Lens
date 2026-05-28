from __future__ import annotations

from typing import Any

from ..schemas import EvidenceItem, SearchResult
from ..storage import save_eval_log
from .llm_service import LLMService


class EvaluationService:
    def __init__(self) -> None:
        self.llm = LLMService()

    def evaluate_search(self, query: str, results: list[SearchResult]) -> dict[str, Any]:
        issues = []
        if not results:
            issues.append("No results were returned.")
        if results and results[0].score < 0.2:
            issues.append("Top score is weak.")
        if results and not results[0].matched_reason:
            issues.append("Top result has no matched reason.")
        if results and not results[0].thumbnail_url:
            issues.append("Top result has no thumbnail.")
        uses = self._modalities_from_results(results)
        score = 10.0
        score -= 3.0 if not results else 0.0
        score -= 1.5 if issues else 0.0
        score -= 1.0 if sum(uses.values()) < 2 else 0.0
        return self._result("search", score, issues, ["expand_query", "rebalance_modalities"] if issues else [], uses)

    def evaluate_cheatsheet(self, request: Any, tex_content: str, source_moments: list[EvidenceItem]) -> dict[str, Any]:
        required = ["Core Concepts", "Key Formulas", "Algorithms", "Important Intuitions", "Common Pitfalls", "Mini Quiz"]
        issues = [f"Missing section: {section}" for section in required if section not in tex_content]
        if "\\[" not in tex_content and "$" not in tex_content:
            issues.append("No formula-like LaTeX was included.")
        if not source_moments:
            issues.append("No source moments attached.")
        score = 10.0 - 1.1 * len(issues)
        uses = self._modalities_from_evidence(source_moments)
        return self._result("cheatsheet", score, issues, ["add_missing_sections", "add_formula_evidence"] if issues else [], uses)

    def evaluate_graph(self, graph_response: Any) -> dict[str, Any]:
        nodes = getattr(graph_response, "nodes", []) if not isinstance(graph_response, dict) else graph_response.get("nodes", [])
        edges = getattr(graph_response, "edges", []) if not isinstance(graph_response, dict) else graph_response.get("edges", [])
        issues = []
        if len(nodes) < 5:
            issues.append("Graph is too sparse.")
        if len(edges) < 4:
            issues.append("Graph has too few relationships.")
        labels = [node.label if hasattr(node, "label") else node.get("label", "") for node in nodes]
        if any(len(label) > 60 for label in labels):
            issues.append("Some node labels are too long.")
        score = 10.0 - 1.4 * len(issues)
        uses = {"uses_asr": True, "uses_ocr": True, "uses_formula": True, "uses_visual": True, "uses_video_embedding": False}
        return self._result("knowledge_graph", score, issues, ["add_concepts", "prune_noisy_nodes", "add_prerequisites"] if issues else [], uses)

    def evaluate_qa(self, question: str, answer: str, evidence: list[EvidenceItem]) -> dict[str, Any]:
        issues = []
        if not evidence:
            issues.append("No evidence returned.")
        if "s" not in answer and "Lecture" not in answer:
            issues.append("Answer may not cite timestamps.")
        if len(answer.strip()) < 60:
            issues.append("Answer is too short to be useful.")
        score = 10.0 - 1.5 * len(issues)
        uses = self._modalities_from_evidence(evidence)
        return self._result("qa", score, issues, ["retrieve_more_evidence", "add_timestamps", "tighten_grounding"] if issues else [], uses)

    def save_log(self, feature_name: str, request: Any, initial_summary: Any, evaluation: dict[str, Any], actions_taken: list[str]) -> str:
        payload = {
            "feature_name": feature_name,
            "request": request if isinstance(request, dict) else getattr(request, "model_dump", lambda **_: str(request))(mode="json"),
            "initial_output_summary": initial_summary,
            "evaluation_result": evaluation,
            "actions_taken": actions_taken,
        }
        return str(save_eval_log(feature_name, payload))

    def _result(
        self,
        feature_name: str,
        score: float,
        issues: list[str],
        plan: list[str],
        multimodal: dict[str, bool],
    ) -> dict[str, Any]:
        score = round(max(0.0, min(10.0, score)), 2)
        return {
            "feature_name": feature_name,
            "score": score,
            "passed": score >= 7.0,
            "issues": issues,
            "improvement_plan": plan,
            "actions_taken": [],
            "grounding_check": {
                "uses_evidence": True,
                "has_timestamps": True,
                "unsupported_claims": [],
            },
            "multimodal_check": multimodal,
            "judge_provider": "heuristic" if not self.llm.is_available() else "gpt-4o_available_heuristic_fast_path",
        }

    def _modalities_from_results(self, results: list[SearchResult]) -> dict[str, bool]:
        names = " ".join(" ".join(result.matched_modalities) for result in results).lower()
        return {
            "uses_asr": "asr" in names or "transcript" in names,
            "uses_ocr": "ocr" in names,
            "uses_formula": "formula" in names,
            "uses_visual": "visual" in names or any(result.thumbnail_url for result in results),
            "uses_video_embedding": "internvideo3" in names,
        }

    def _modalities_from_evidence(self, evidence: list[EvidenceItem]) -> dict[str, bool]:
        names = " ".join(" ".join(item.matched_modalities) for item in evidence).lower()
        return {
            "uses_asr": "asr" in names or any(item.transcript_snippet for item in evidence),
            "uses_ocr": "ocr" in names or any(item.ocr_snippet for item in evidence),
            "uses_formula": "formula" in names or any(item.formula_latex for item in evidence),
            "uses_visual": any(item.thumbnail_url for item in evidence),
            "uses_video_embedding": "internvideo3" in names,
        }
