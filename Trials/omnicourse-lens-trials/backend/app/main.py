from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import ensure_directories, settings
from .schemas import CheatsheetRequest, GraphRequest, QARequest, SearchRequest
from .services.cheatsheet_service import CheatsheetService
from .services.graph_service import GraphService
from .services.qa_agent import QAAgent
from .services.deepseek_ocr_service import DeepSeekOCRService
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


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "project": "omnicourse-lens-trials",
        "demo_mode": settings.demo_mode,
        "providers": {
            "search": search_service.describe_provider(),
            "deepseek_ocr": DeepSeekOCRService().describe_provider(),
        },
    }


@app.get("/api/provider-status")
def provider_status() -> dict:
    return health()["providers"]


@app.get("/api/courses")
def courses() -> list[dict]:
    return search_service.all_courses_summary()


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
    top_k: int = Form(5),
    image: UploadFile = File(...),
) -> dict:
    suffix = Path(image.filename or "query.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=settings.uploads_dir) as tmp:
        shutil.copyfileobj(image.file, tmp)
        tmp_path = tmp.name
    lectures = [item.strip() for item in lecture_ids.split(",") if item.strip()] if lecture_ids else None
    return search_service.image_search(course_id, tmp_path, text_query=query, lecture_ids=lectures, top_k=top_k)


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
