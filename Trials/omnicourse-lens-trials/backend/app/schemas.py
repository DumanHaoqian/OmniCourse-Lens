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
    max_moments: int = 45
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
    metrics: dict[str, Any] = Field(default_factory=dict)
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


class EvidenceLedgerItem(BaseModel):
    evidence_id: str
    source_type: str = "video_moment"
    video_id: Optional[str] = None
    lecture_id: Optional[str] = None
    lecture_title: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    modality: list[str] = Field(default_factory=list)
    content: str = ""
    confidence: float = 0.0
    provider: str = "indexed_evidence"
    score: float = 0.0
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillDefinition(BaseModel):
    name: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    tools_used: list[str] = Field(default_factory=list)
    execution_procedure: list[str] = Field(default_factory=list)
    evidence_output_schema: dict[str, Any] = Field(default_factory=dict)
    validator: str = "evaluation_service"
    repair_policy: str = "retrieve_more_and_regenerate"


class LearningBaseRequest(BaseModel):
    course_id: str = "real_i2ml"
    video_id: Optional[str] = None
    lecture_id: Optional[str] = None
    current_moment_id: Optional[str] = None
    top_k: int = 5


class PrerequisiteRewindRequest(LearningBaseRequest):
    question: Optional[str] = None
    target_concept: Optional[str] = None


class MisconceptionCheckRequest(LearningBaseRequest):
    student_text: str
    related_concept: Optional[str] = None


class SocraticDrillRequest(LearningBaseRequest):
    focus_topic: str = "gradient descent"
    difficulty: str = "medium"
    number_of_questions: int = 4


class FormulaDerivationRequest(LearningBaseRequest):
    formula_latex: str = r"\theta := \theta - \alpha \nabla_\theta J(\theta)"
    question: Optional[str] = None


class RegionExplainRequest(LearningBaseRequest):
    image_path: Optional[str] = None
    bbox: Optional[list[float]] = None
    question: Optional[str] = None
    timestamp: Optional[float] = None


class MasteryUpdateRequest(BaseModel):
    student_id: str = "demo_student"
    course_id: str = "real_i2ml"
    interactions: list[dict[str, Any]] = Field(default_factory=list)
    quiz_answers: list[dict[str, Any]] = Field(default_factory=list)
    watched_clips: list[dict[str, Any]] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)


class StudyPlanRequest(BaseModel):
    student_id: str = "demo_student"
    course_id: str = "real_i2ml"
    focus_topics: list[str] = Field(default_factory=list)
    days: int = 3
