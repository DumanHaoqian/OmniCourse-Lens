from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import ensure_directories, settings
from .schemas import CheatsheetRequest, GraphRequest, QARequest, SearchRequest
from .services.cheatsheet_service import CheatsheetService
from .services.dataset_service import DatasetService
from .services.graph_service import GraphService
from .services.llm_service import LLMService
from .services.qa_agent import QAAgent
from .services.deepseek_ocr_service import DeepSeekOCRService
from .services.evidence_service import EvidenceService
from .services.search_service import SearchService
from .services.video_ingest import VideoIngestService
from .storage import load_course, list_courses


ensure_directories()
app = FastAPI(title="OmniCourse Lens Trials API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

search_service = SearchService()
cheatsheet_service = CheatsheetService()
graph_service = GraphService()
qa_agent = QAAgent()
dataset_service = DatasetService()
evidence_service = EvidenceService()
_PROVIDER_CACHE: tuple[float, dict] | None = None
_PROVIDER_CACHE_TTL = 15.0


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "project": "omnicourse-lens-trials",
        "demo_mode": settings.demo_mode,
        "providers": _provider_status_cached(),
    }


@app.get("/api/provider-status")
def provider_status() -> dict:
    return _provider_status_cached()


def _provider_status_cached() -> dict:
    global _PROVIDER_CACHE
    now = time.time()
    if _PROVIDER_CACHE and now - _PROVIDER_CACHE[0] < _PROVIDER_CACHE_TTL:
        return _PROVIDER_CACHE[1]
    providers = {
        "search": search_service.describe_provider(),
        "deepseek_ocr": DeepSeekOCRService().describe_provider(),
        "dataset": {"root": str(settings.dataset_dir), "exists": settings.dataset_dir.exists()},
        "latex": cheatsheet_service.describe_provider(),
        "llm": LLMService().describe_provider(),
        "ingest": VideoIngestService().describe_provider(),
    }
    _PROVIDER_CACHE = (now, providers)
    return providers


@app.get("/api/courses")
def courses() -> list[dict]:
    return search_service.all_courses_summary()


@app.get("/api/dataset/videos")
def dataset_videos() -> list[dict]:
    return dataset_service.list_videos()


@app.get("/api/dataset/videos/{video_id}/stream")
def dataset_video_stream(video_id: str) -> FileResponse:
    try:
        path = dataset_service.resolve_video(video_id=video_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.get("/api/dataset/videos/{video_id}/subtitles")
def dataset_video_subtitles(video_id: str) -> dict:
    return evidence_service.subtitles(video_id)


@app.get("/api/dataset/videos/{video_id}/subtitles.vtt")
def dataset_video_subtitles_vtt(video_id: str) -> Response:
    return Response(evidence_service.subtitles_vtt(video_id), media_type="text/vtt; charset=utf-8")


@app.get("/api/dataset/videos/{video_id}/evidence")
def dataset_video_evidence(video_id: str) -> dict:
    return {"video_id": video_id, "moments": evidence_service.video_moments(video_id), "summary": evidence_service.video_summary(video_id)}


@app.get("/api/moments/{moment_id}")
def moment_detail(moment_id: str) -> dict:
    moment = evidence_service.moment(moment_id)
    if not moment:
        raise HTTPException(status_code=404, detail="Moment not found")
    return moment


@app.post("/api/dataset/ingest")
async def dataset_ingest(request: Request) -> dict:
    payload = await request.json()
    try:
        result = dataset_service.ingest_video(
            video_id=payload.get("video_id"),
            video_path=payload.get("video_path"),
            course_id=payload.get("course_id"),
            lecture_id=payload.get("lecture_id"),
            title=payload.get("title"),
            force_reingest=bool(payload.get("force_reingest", False)),
            frame_interval=float(payload.get("frame_interval", 120.0)),
            window_sec=float(payload.get("window_sec", 120.0)),
        )
        return {"result": result, "rebuild_index": dataset_service.rebuild_index()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/dataset/ingest-all")
async def dataset_ingest_all(request: Request) -> dict:
    payload = await request.json()
    return dataset_service.ingest_all(
        limit=payload.get("limit"),
        force_reingest=bool(payload.get("force_reingest", False)),
    )


@app.post("/api/jobs/start-ingest-all")
async def start_ingest_all(request: Request) -> dict:
    payload = await request.json()
    return dataset_service.start_ingest_all_job(
        limit=payload.get("limit"),
        force_reingest=bool(payload.get("force_reingest", False)),
    )


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = dataset_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/index/rebuild")
def rebuild_index() -> dict:
    return dataset_service.rebuild_index()


@app.get("/api/courses/{course_id}")
def course(course_id: str) -> dict:
    try:
        return load_course(course_id).model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/search/text")
def search_text(request: SearchRequest) -> dict:
    return search_service.text_search(request)


@app.post("/api/cheatsheet")
def cheatsheet(request: CheatsheetRequest) -> dict:
    return cheatsheet_service.generate(request).model_dump(mode="json")


@app.post("/api/cheatsheet/compile")
async def compile_cheatsheet(request: Request) -> dict:
    payload = await request.json()
    return cheatsheet_service.compile_existing(
        tex_content=payload.get("tex_content"),
        filename=payload.get("filename"),
    )


@app.post("/api/knowledge-graph")
def knowledge_graph(request: GraphRequest) -> dict:
    return graph_service.generate(request).model_dump(mode="json")


@app.post("/api/qa")
async def qa(request: Request) -> dict:
    content_type = request.headers.get("content-type", "")
    image_path = None
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("image")
        if hasattr(upload, "file"):
            suffix = Path(upload.filename or "qa_image.png").suffix or ".png"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=settings.uploads_dir) as tmp:
                shutil.copyfileobj(upload.file, tmp)
                image_path = tmp.name
        qa_request = QARequest(
            course_id=str(form.get("course_id")),
            question=str(form.get("question")),
            lecture_id=str(form.get("lecture_id")) if form.get("lecture_id") else None,
            video_id=str(form.get("video_id")) if form.get("video_id") else None,
            current_timestamp=float(form.get("current_timestamp")) if form.get("current_timestamp") else None,
            top_k=int(form.get("top_k") or 5),
        )
    else:
        payload = await request.json()
        image_path = payload.get("image_path")
        qa_request = QARequest.model_validate(payload)
    return qa_agent.answer(qa_request, image_path=image_path).model_dump(mode="json")


@app.post("/api/search/image")
async def search_image(
    course_id: str = Form(...),
    query: str = Form(""),
    lecture_ids: Optional[str] = Form(None),
    video_ids: Optional[str] = Form(None),
    top_k: int = Form(5),
    image: UploadFile = File(...),
) -> dict:
    suffix = Path(image.filename or "query.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=settings.uploads_dir) as tmp:
        shutil.copyfileobj(image.file, tmp)
        tmp_path = tmp.name
    lectures = [item.strip() for item in lecture_ids.split(",") if item.strip()] if lecture_ids else None
    videos = [item.strip() for item in video_ids.split(",") if item.strip()] if video_ids else None
    return search_service.image_search(course_id, tmp_path, text_query=query, lecture_ids=lectures, video_ids=videos, top_k=top_k)


@app.post("/api/ingest/video")
def ingest_video(
    video_path: str = Form(...),
    course_id: str = Form(...),
    lecture_id: str = Form(...),
    title: str = Form(...),
    transcript_file: Optional[str] = Form(None),
    frame_interval: float = Form(10.0),
    window_sec: float = Form(20.0),
) -> dict:
    if not Path(video_path).exists():
        raise HTTPException(status_code=400, detail=f"Video file does not exist: {video_path}")
    course_obj = VideoIngestService().ingest_video(
        video_path=video_path,
        course_id=course_id,
        lecture_id=lecture_id,
        title=title,
        transcript_file=transcript_file,
        frame_interval=frame_interval,
        window_sec=window_sec,
    )
    return {"course": course_obj.model_dump(mode="json"), "provider_status": VideoIngestService().describe_provider()}


@app.get("/api/generated/{kind}/{filename}")
def generated_file(kind: str, filename: str) -> FileResponse:
    allowed = {"cheatsheets", "graphs", "qa", "evals"}
    if kind not in allowed:
        raise HTTPException(status_code=404, detail="Unknown generated file category.")
    path = settings.generated_dir / kind / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generated file not found.")
    return FileResponse(path)
