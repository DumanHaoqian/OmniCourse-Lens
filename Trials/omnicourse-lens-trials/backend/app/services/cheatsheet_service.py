from __future__ import annotations

import re
import shutil
import subprocess
import time
import os
from pathlib import Path
from typing import Any

from ..config import settings
from ..schemas import CheatsheetRequest, CheatsheetResponse, EvidenceItem, Moment
from ..storage import generated_url, load_course
from .llm_service import LLMService
from .self_improvement_service import SelfImprovementService


class CheatsheetService:
    def __init__(self) -> None:
        self.llm = LLMService()
        self.improver = SelfImprovementService()

    def describe_provider(self) -> dict[str, Any]:
        return {
            "tectonic_available": shutil.which("tectonic") is not None,
            "pdflatex_available": shutil.which("pdflatex") is not None,
            "xelatex_available": shutil.which("xelatex") is not None,
            "online_workflow": "download_tex_or_copy_to_overleaf",
        }

    def generate(self, request: CheatsheetRequest) -> CheatsheetResponse:
        course = load_course(request.course_id)
        lectures = [lecture for lecture in course.lectures if lecture.lecture_id in request.lecture_ids]
        moments = [
            moment
            for lecture in lectures
            for moment in lecture.moments
            if not request.video_ids or moment.video_id in request.video_ids or moment.metadata.get("video_id") in request.video_ids
        ]
        evidence = [self._evidence(moment, lecture.title) for lecture in lectures for moment in lecture.moments[:8] if moment in moments]
        if self.llm.is_available():
            tex = self._generate_with_llm(request, moments)
            mode = "gpt-4o"
        else:
            tex = self._generate_fallback(course.title, request, moments)
            mode = "fallback"
        improved = self.improver.improve_cheatsheet(request, tex, evidence)
        tex = self._clean_tex(improved["tex_content"])
        tex_path, pdf_path, compile_error = self._save_and_compile(request, tex)
        self.improver.evaluator.save_log(
            "cheatsheet",
            request,
            {"tex_chars": len(tex), "source_moments": len(evidence)},
            improved["self_check"],
            improved["actions_taken"] + ([f"latex_compile_error:{compile_error[:120]}"] if compile_error else []),
        )
        return CheatsheetResponse(
            tex_content=tex,
            tex_file_url=generated_url("cheatsheets", tex_path.name),
            pdf_file_url=generated_url("cheatsheets", pdf_path.name) if pdf_path else None,
            source_moments=evidence,
            generation_mode=mode,
            self_check={**improved["self_check"], "pdf_compile_error": compile_error},
        )

    def compile_existing(self, tex_content: str | None = None, filename: str | None = None) -> dict[str, Any]:
        out_dir = settings.generated_dir / "cheatsheets"
        out_dir.mkdir(parents=True, exist_ok=True)
        if tex_content:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            tex_path = out_dir / f"manual_compile_{stamp}.tex"
            tex_path.write_text(self._clean_tex(tex_content), encoding="utf-8")
        elif filename:
            tex_path = out_dir / Path(filename).name
            if not tex_path.exists():
                return {"ok": False, "compile_error": f"File not found: {tex_path.name}"}
        else:
            return {"ok": False, "compile_error": "tex_content or filename is required."}
        pdf_path, compile_error = self._compile_tex(tex_path)
        return {
            "ok": pdf_path is not None,
            "tex_file_url": generated_url("cheatsheets", tex_path.name),
            "pdf_file_url": generated_url("cheatsheets", pdf_path.name) if pdf_path else None,
            "compile_error": compile_error,
            "provider": self.describe_provider(),
        }

    def _generate_with_llm(self, request: CheatsheetRequest, moments: list[Moment]) -> str:
        evidence = "\n\n".join(self._moment_pack(moment) for moment in moments)
        prompt = (
            "Generate a compact LaTeX STEM cheatsheet using only this evidence. "
            f"Focus topics: {request.focus_topics or 'all selected lecture topics'}. Max pages: {request.max_pages}.\n\n"
            f"{evidence}"
        )
        tex = self.llm.chat(
            "You generate concise LaTeX STEM cheatsheets from lecture evidence. Use only ASR transcript, OCR snippets, formulas, concepts, and visual captions.",
            prompt,
            temperature=0.2,
            max_tokens=2200,
        )
        tex = self._clean_tex(tex)
        return tex if "\\section*" in tex else self._generate_fallback(request.course_id, request, moments)

    def _generate_fallback(self, title: str, request: CheatsheetRequest, moments: list[Moment]) -> str:
        concepts = self._unique([tag for moment in moments for tag in moment.concept_tags])
        formulas = self._unique([formula for moment in moments for formula in [moment.formula_latex] if formula])
        focus = self._escape(request.focus_topics or "selected lectures")
        definitions = [self._escape(self._short(moment.transcript or moment.ocr_text, 180)) for moment in moments if moment.transcript or moment.ocr_text]
        algorithms = [item for item in concepts if item in {"gradient descent", "backpropagation", "normal equation"}]
        return "\n".join(
            [
                "\\documentclass[10pt]{article}",
                "\\usepackage[margin=0.55in]{geometry}",
                "\\usepackage{amsmath,amssymb}",
                "\\usepackage{enumitem}",
                "\\setlist{nosep,leftmargin=*}",
                "\\begin{document}",
                f"\\section*{{{self._escape(title)} Cheatsheet}}",
                f"Focus: {focus}.",
                "\\section*{Core Concepts}",
                "\\begin{itemize}",
                *[f"\\item \\textbf{{{self._escape(concept.title())}}}: {definitions[i % len(definitions)] if definitions else 'Evidence-backed lecture concept.'}" for i, concept in enumerate(concepts[:10])],
                "\\end{itemize}",
                "\\section*{Key Formulas}",
                "\\begin{itemize}",
                *[f"\\item \\[{formula}\\]" for formula in formulas[:8]],
                "\\end{itemize}",
                "\\section*{Algorithms}",
                "\\begin{enumerate}",
                *[f"\\item {self._escape(name.title())}: identify the objective, compute the needed derivative or closed-form step, and check assumptions from the lecture evidence." for name in algorithms[:5]],
                "\\end{enumerate}",
                "\\section*{Important Intuitions}",
                "\\begin{itemize}",
                *[f"\\item {definition}" for definition in definitions[:6]],
                "\\end{itemize}",
                "\\section*{Common Pitfalls}",
                "\\begin{itemize}",
                "\\item Confusing the loss function with the optimizer used to minimize it.",
                "\\item Choosing a learning rate so large that gradient descent overshoots.",
                "\\item Forgetting dimensions in matrix formulas such as the normal equation.",
                "\\end{itemize}",
                "\\section*{Mini Quiz}",
                "\\begin{enumerate}",
                "\\item Why does gradient descent move opposite to the gradient?",
                "\\item When is the normal equation preferable to an iterative optimizer?",
                "\\item Where does the chain rule appear in backpropagation?",
                "\\end{enumerate}",
                "\\end{document}",
            ]
        )

    def _save_and_compile(self, request: CheatsheetRequest, tex: str) -> tuple[Path, Path | None, str | None]:
        out_dir = settings.generated_dir / "cheatsheets"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        tex_path = out_dir / f"{request.course_id}_{stamp}.tex"
        tex_path.write_text(self._clean_tex(tex), encoding="utf-8")
        pdf_path, compile_error = self._compile_tex(tex_path)
        return tex_path, pdf_path, compile_error

    def _clean_tex(self, tex: str) -> str:
        tex = (tex or "").strip()
        fence = re.match(r"^```(?:latex|tex)?\s*(.*?)\s*```$", tex, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            tex = fence.group(1).strip()
        document_start = tex.find("\\documentclass")
        if document_start > 0:
            tex = tex[document_start:].strip()
        document_end = tex.rfind("\\end{document}")
        if document_end >= 0:
            tex = tex[: document_end + len("\\end{document}")].strip()
        return self._strip_unresolved_graphics(tex)

    def _strip_unresolved_graphics(self, tex: str) -> str:
        """Keep LLM-produced cheatsheets compilable by removing hallucinated image files."""
        placeholder = "\\textit{Visual evidence is available in the OmniCourse Lens video and keyframe panel.}"
        tex = re.sub(
            r"\\includegraphics(?:\[[^\]]*\])?\{[^}]+\}",
            lambda _match: placeholder,
            tex,
        )
        tex = re.sub(
            r"\\caption\{([^}]*)\}",
            lambda match: f"\\textit{{{match.group(1)}}}",
            tex,
        )
        tex = re.sub(
            r"\\begin\{center\}\s*" + re.escape(placeholder) + r"\s*\\end\{center\}",
            lambda _match: placeholder,
            tex,
            flags=re.DOTALL,
        )
        return tex

    def _compile_tex(self, tex_path: Path) -> tuple[Path | None, str | None]:
        out_dir = tex_path.parent
        logs = []
        timeout = int(os.getenv("OMNICOURSE_LATEX_TIMEOUT", "180"))
        for command in (
            ["tectonic", tex_path.name],
            ["pdflatex", "-interaction=nonstopmode", tex_path.name],
            ["xelatex", "-interaction=nonstopmode", tex_path.name],
        ):
            try:
                result = subprocess.run(command, cwd=out_dir, check=True, capture_output=True, text=True, timeout=timeout)
                pdf_path = tex_path.with_suffix(".pdf")
                if pdf_path.exists():
                    return pdf_path, None
                logs.append(result.stdout[-1000:] + result.stderr[-1000:])
            except FileNotFoundError:
                continue
            except Exception as exc:
                logs.append(str(exc)[:1000])
                continue
        if logs:
            return None, "\n".join(logs)[-2500:]
        return None, "No LaTeX compiler found (tectonic, pdflatex, or xelatex)."

    def _evidence(self, moment: Moment, lecture_title: str) -> EvidenceItem:
        return EvidenceItem(
            moment_id=moment.moment_id,
            lecture_id=moment.lecture_id,
            lecture_title=lecture_title,
            start_time=moment.start_time,
            end_time=moment.end_time,
            thumbnail_url=moment.thumbnail_url,
            matched_reason=f"Cheatsheet source moment: {', '.join(moment.concept_tags[:3])}",
            matched_modalities=["ASR transcript", "OCR", "Formula", "Visual"],
            transcript_snippet=self._short(moment.transcript),
            ocr_snippet=self._short(moment.ocr_text),
            formula_latex=moment.formula_latex,
            score=1.0,
        )

    def _moment_pack(self, moment: Moment) -> str:
        return (
            f"Moment {moment.lecture_id} {moment.start_time:.0f}-{moment.end_time:.0f}s\n"
            f"Transcript: {moment.transcript}\nOCR: {moment.ocr_text}\nFormula: {moment.formula_latex}\n"
            f"Concepts: {', '.join(moment.concept_tags)}\nVisual: {moment.visual_caption}"
        )

    def _unique(self, items: list[str]) -> list[str]:
        seen = set()
        result = []
        for item in items:
            item = item.strip()
            if item and item not in seen:
                seen.add(item)
                result.append(item)
        return result

    def _short(self, text: str, max_chars: int = 220) -> str:
        text = " ".join((text or "").split())
        return text[: max_chars - 3] + "..." if len(text) > max_chars else text

    def _escape(self, text: str) -> str:
        return re.sub(r"([_%&#])", r"\\\1", text or "")
