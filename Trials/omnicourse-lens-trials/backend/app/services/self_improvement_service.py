from __future__ import annotations

from typing import Any

from ..schemas import EvidenceItem, SearchResult
from .evaluation_service import EvaluationService


class SelfImprovementService:
    def __init__(self, threshold: float = 7.0) -> None:
        self.threshold = threshold
        self.evaluator = EvaluationService()

    def improve_search(self, query: str, initial_results: list[SearchResult], context: dict[str, Any] | None = None) -> dict[str, Any]:
        evaluation = self.evaluator.evaluate_search(query, initial_results)
        actions = []
        final_results = initial_results
        if evaluation["score"] < self.threshold and context and context.get("rerun"):
            actions.append("expanded_query_and_reran_hybrid_search")
            final_results = context["rerun"](query)
            evaluation = self.evaluator.evaluate_search(query, final_results)
        evaluation["actions_taken"] = actions
        return {"results": final_results, "self_check": evaluation, "actions_taken": actions}

    def improve_cheatsheet(self, request: Any, initial_tex: str, source_moments: list[EvidenceItem]) -> dict[str, Any]:
        evaluation = self.evaluator.evaluate_cheatsheet(request, initial_tex, source_moments)
        actions = []
        tex = initial_tex
        missing_sections = [issue.replace("Missing section: ", "") for issue in evaluation.get("issues", []) if issue.startswith("Missing section:")]
        if evaluation["score"] < self.threshold:
            for section in missing_sections:
                tex += f"\n\\section*{{{section}}}\nReview the selected evidence and add compact notes here.\n"
            if "No formula-like LaTeX was included." in evaluation.get("issues", []):
                formulas = [item.formula_latex for item in source_moments if item.formula_latex]
                if formulas:
                    tex += "\n\\section*{Formula Evidence}\n" + "\n".join(f"\\[{formula}\\]" for formula in formulas[:6]) + "\n"
            actions.append("patched_missing_sections_and_formula_evidence")
            evaluation = self.evaluator.evaluate_cheatsheet(request, tex, source_moments)
        evaluation["actions_taken"] = actions
        return {"tex_content": tex, "self_check": evaluation, "actions_taken": actions}

    def improve_graph(self, request: Any, initial_graph: Any) -> dict[str, Any]:
        evaluation = self.evaluator.evaluate_graph(initial_graph)
        actions = []
        evaluation["actions_taken"] = actions
        return {"graph": initial_graph, "self_check": evaluation, "actions_taken": actions}

    def improve_qa(self, request: Any, initial_answer: str, evidence: list[EvidenceItem]) -> dict[str, Any]:
        evaluation = self.evaluator.evaluate_qa(getattr(request, "question", ""), initial_answer, evidence)
        actions = []
        answer = initial_answer
        if evaluation["score"] < self.threshold and evidence:
            citations = ", ".join(f"{item.lecture_title} {item.start_time:.0f}-{item.end_time:.0f}s" for item in evidence[:3])
            answer = f"{answer}\n\nEvidence to review: {citations}."
            actions.append("added_explicit_timestamp_evidence")
            evaluation = self.evaluator.evaluate_qa(getattr(request, "question", ""), answer, evidence)
        evaluation["actions_taken"] = actions
        return {"answer": answer, "self_check": evaluation, "actions_taken": actions}
