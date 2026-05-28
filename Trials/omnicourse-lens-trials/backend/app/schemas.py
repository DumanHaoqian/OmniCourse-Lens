from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ASRSegment(BaseModel):
    start_time: float
    end_time: float
    text: str
    confidence: Optional[float] = None
    provider: str = "fallback"


class OCRBlock(BaseModel):
    text: str
    bbox: Optional[list[float]] = None
    confidence: Optional[float] = None
    provider: str = "fallback"
    frame_path: Optional[str] = None
    timestamp: Optional[float] = None


class FormulaBlock(BaseModel):
    latex: str
    source_frame: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: Optional[float] = None
    provider: Optional[str] = None


class Moment(BaseModel):
    moment_id: str
    video_id: Optional[str] = None
    course_id: str
    lecture_id: str
    start_time: float
    end_time: float
    transcript: str = ""
    asr_segments: list[ASRSegment] = Field(default_factory=list)
    ocr_text: str = ""
    ocr_blocks: list[OCRBlock] = Field(default_factory=list)
    formula_latex: str = ""
    formula_blocks: list[FormulaBlock] = Field(default_factory=list)
    visual_caption: str = ""
    concept_tags: list[str] = Field(default_factory=list)
    keyframes: list[str] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None
    video_embedding: Optional[list[float]] = None
    embedding_provider: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Lecture(BaseModel):
    lecture_id: str
    course_id: str
    title: str
    video_path: Optional[str] = None
    duration: float = 0.0
    moments: list[Moment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Course(BaseModel):
    course_id: str
    title: str
    description: str = ""
    lectures: list[Lecture] = Field(default_factory=list)


class SearchRequest(BaseModel):
    course_id: str
    query: str = ""
    lecture_ids: Optional[list[str]] = None
    video_ids: Optional[list[str]] = None
    top_k: int = 5
    search_mode: Optional[str] = "hybrid"


class SearchResult(BaseModel):
    moment_id: str
    video_id: Optional[str] = None
    course_id: str
    lecture_id: str
    lecture_title: str
    start_time: float
    end_time: float
    score: float
    score_breakdown: dict[str, float]
    matched_reason: str
    matched_modalities: list[str]
    transcript_snippet: str
    ocr_snippet: str
    formula_latex: str = ""
    concept_tags: list[str] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None
    video_url: Optional[str] = None


class CheatsheetRequest(BaseModel):
    course_id: str
    lecture_ids: list[str]
    video_ids: Optional[list[str]] = None
    focus_topics: Optional[str] = None
    style: str = "exam"
    max_pages: int = 2


class EvidenceItem(BaseModel):
    moment_id: str
    lecture_id: str
    lecture_title: str
    start_time: float
    end_time: float
    thumbnail_url: Optional[str] = None
    matched_reason: str
    matched_modalities: list[str] = Field(default_factory=list)
    transcript_snippet: str = ""
    ocr_snippet: str = ""
    formula_latex: str = ""
    score: float = 0.0


class EvaluationResult(BaseModel):
    feature_name: str
    score: float
    passed: bool
    issues: list[str] = Field(default_factory=list)
    improvement_plan: list[str] = Field(default_factory=list)
    actions_taken: list[str] = Field(default_factory=list)
    raw_judge_output: Optional[Any] = None


class CheatsheetResponse(BaseModel):
    tex_content: str
    tex_file_url: str
    pdf_file_url: Optional[str] = None
    source_moments: list[EvidenceItem]
    generation_mode: str
    self_check: Optional[dict[str, Any]] = None


class GraphRequest(BaseModel):
    course_id: str
    lecture_ids: list[str]
    video_ids: Optional[list[str]] = None
    focus_topic: Optional[str] = None
    max_concepts: int = 35
    include_moments: bool = True


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    lecture_id: Optional[str] = None
    timestamp: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    summary: str
    self_check: Optional[dict[str, Any]] = None


class QARequest(BaseModel):
    course_id: str
    question: str
    lecture_id: Optional[str] = None
    video_id: Optional[str] = None
    current_timestamp: Optional[float] = None
    top_k: Optional[int] = 5


class QAResponse(BaseModel):
    answer: str
    evidence: list[EvidenceItem]
    suggested_review: list[EvidenceItem] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    confidence: float
    self_check: dict[str, Any]
    generation_mode: str
