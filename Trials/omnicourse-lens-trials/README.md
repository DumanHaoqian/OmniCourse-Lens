# OmniCourse Atlas / Lens Trials

Runnable multimodal learning workspace for the real lecture videos under `/home/haoqian/Data/OmniCourse-Lens/Dataset`. It searches lecture videos by text/image, generates LaTeX STEM cheatsheets, builds readable concept graphs, and answers questions with timestamped course evidence.

## Features

- Dataset Loader: discovers the real Dataset videos, ingests selected/all videos, extracts keyframes, and rebuilds indexes.
- Search Video: hybrid retrieval over ASR transcript, associated slide/PDF text, frame OCR, formulas, visual captions, keyframe descriptors, concept tags, and optional InternVideo3 scoring.
- Cheatsheet: evidence-grounded LaTeX generation with GPT-4o when available and deterministic fallback when unavailable.
- Knowledge Graph: Cytoscape/fcose graph for course, lecture, moment, concept, formula, and visual-evidence nodes with pruning and node inspection.
- AI Tutor: text/image QA agent that retrieves first, answers from evidence, cites timestamps, renders Markdown + LaTeX, and self-checks grounding.
- Self-validation: search, cheatsheet, graph, and QA outputs receive heuristic evaluation logs; GPT-4o can be used as a stronger generator/judge when credentials work.

## Real Dataset Flow

The main product flow uses:

```text
/home/haoqian/Data/OmniCourse-Lens/Dataset
```

The backend endpoint `GET /api/dataset/videos` recursively discovers `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, and `.m4v` files only inside that fixed root. Each item includes `video_id`, absolute/relative path, size, duration, ingestion status, indexed status, thumbnail, title, lecture id, and associated slides PDF when present.

The endpoint `POST /api/dataset/ingest` ingests one selected real video. `POST /api/jobs/start-ingest-all` starts a background ingest-all job. `POST /api/index/rebuild` rebuilds the search index.

The committed real-data baseline ingests:

```text
08_i2ml_01_ml_basics_07_optimization__video.mp4
```

as course `real_i2ml`, with 10 timestamped moments and extracted keyframes. Associated slides text is injected as `slide_pdf_text` OCR evidence so the app can retrieve real lecture concepts even when heavy OCR/ASR providers are unavailable.

## Architecture

Backend is FastAPI under `backend/app`. Storage is JSON-first for hackathon reliability: courses live in `backend/app/data/courses`, indexes in `backend/app/data/indexes`, generated artifacts in `backend/app/data/generated`, static keyframes in `backend/app/static/frames`, and optional clips in `backend/app/static/clips`.

The multimodal record for every moment combines:

- audio ASR segments,
- OCR blocks from video frames/slides/PDF text,
- formula/math OCR blocks when available,
- keyframe paths and visual captions,
- concept tags and metadata,
- optional InternVideo3 video signals.

Search fusion uses weighted modality scores. Text search defaults to transcript, OCR, formula, dense text, concept, and optional InternVideo3 weights. Image search adds image visual similarity and image OCR.

## Setup

```bash
cd /home/haoqian/Data/OmniCourse-Lens/Trials/omnicourse-lens-trials
python -m pip install -r backend/requirements.txt
cd frontend
npm install
```

Optional heavy providers are discovered lazily. The MVP works without CUDA, InternVideo3, DeepSeek OCR, LaTeX, or GPT-4o.

## Demo And Real Data

```bash
cd /home/haoqian/Data/OmniCourse-Lens/Trials/omnicourse-lens-trials
python scripts/create_demo_data.py
python scripts/rebuild_index.py
```

The generated demo course is `ml_foundations` with lectures on linear regression, gradient descent, and neural networks. It is only a fallback/smoke-test dataset.

For the real Dataset flow:

```bash
python - <<'PY'
import sys
sys.path.insert(0, "backend")
from app.services.dataset_service import DatasetService
svc = DatasetService()
print(len(svc.list_videos()))
print(svc.ingest_video(video_id=[v for v in svc.list_videos() if "optimization" in v["relative_path"]][0]["video_id"]))
print(svc.rebuild_index())
PY
```

## Run

Backend:

```bash
cd /home/haoqian/Data/OmniCourse-Lens/Trials/omnicourse-lens-trials
scripts/run_backend.sh
```

Frontend:

```bash
cd /home/haoqian/Data/OmniCourse-Lens/Trials/omnicourse-lens-trials
scripts/run_frontend.sh
```

Open `http://localhost:5173`. The backend default is `http://localhost:8000`.

The UI is a product workspace:

- main area: Dataset video loader, real video player, evidence/result workspace
- right sidebar: exactly four feature tabs, Search Video, Cheatsheet, Knowledge Graph, AI Tutor

All-in-one:

```bash
scripts/run_all.sh
```

## Ingest A Real Video

```bash
python scripts/ingest_video.py \
  --video /path/to/video.mp4 \
  --course-id my_course \
  --lecture-id lec_01 \
  --title "Lecture 1: Introduction"

python scripts/rebuild_index.py
```

The ingestion pipeline probes metadata, extracts mono 16kHz WAV with `ffmpeg`, runs ASR fallback order, extracts keyframes, reads associated slides PDF text when present, runs DeepSeek/Paddle/EasyOCR/Tesseract/fallback OCR, extracts formula-like text, constructs overlapping moments, and updates course JSON.

## Providers

GPT-4o / Azure OpenAI:

- environment first: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`
- fallback file: `/home/haoqian/Data/OmniCourse-Lens/openai_keys.txt`
- full Azure chat-completions URLs are normalized to SDK base endpoints
- keys are never sent to the frontend and should never be committed

DeepSeek OCR:

- `DEEPSEEK_OCR_ENDPOINT`
- `DEEPSEEK_OCR_API_KEY` or `DEEPSEEK_API_KEY`
- `DEEPSEEK_OCR_MODEL`
- `DEEPSEEK_OCR_MODEL_PATH`

If unavailable, OCR falls back to Tesseract when installed and then deterministic demo OCR.

InternVideo3:

- `INTERNVIDEO3_ENDPOINT` for an embedding/scoring HTTP service
- `INTERNVIDEO3_CLI` for a local script wrapper
- `INTERNVIDEO3_MODEL_PATH` for checkpoint discovery
- `INTERNVIDEO3_ENABLE_LOCAL=1` to opt into local import mode

The existing checkpoint at `Trials/checkpoints/InternVideo3-8B-Instruct` is detected but not loaded during API startup. Search proceeds without it if no endpoint/CLI is configured.

## API

- `GET /api/health`
- `GET /api/courses`
- `GET /api/courses/{course_id}`
- `POST /api/ingest/video`
- `GET /api/dataset/videos`
- `GET /api/dataset/videos/{video_id}/stream`
- `POST /api/dataset/ingest`
- `POST /api/dataset/ingest-all`
- `POST /api/jobs/start-ingest-all`
- `GET /api/jobs/{job_id}`
- `POST /api/index/rebuild`
- `POST /api/search/text`
- `POST /api/search/image`
- `POST /api/cheatsheet`
- `POST /api/cheatsheet/compile`
- `GET /api/generated/cheatsheets/{filename}`
- `POST /api/knowledge-graph`
- `POST /api/qa`

Static frames and clips are served from `/static`.

## Validation

```bash
python scripts/smoke_test.py
pytest tests/test_api_smoke.py
cd frontend && npm run build
```

The overnight smoke test verifies real Dataset discovery, real video ingest/index status, real text search, real keyframe image search, QA with LaTeX-friendly output, cheatsheet generation plus compile endpoint, graph pruning, provider status, and writes `backend/app/data/generated/evals/overnight_smoke_test_summary.json`.

## Security

Do not commit API keys, cookies, model weights, checkpoints, uploads, large clips, virtual environments, or `node_modules`. The project `.gitignore` excludes those by default. Provider status may show that a key exists and its last four characters, but never the full key.

## Known Limitations

- JSON storage is intentional for the MVP; production should use a vector DB and durable metadata store.
- Image retrieval uses a PIL color-histogram fallback unless CLIP/SigLIP integration is added later.
- InternVideo3 is adapted as an optional scorer, not loaded as a default embedding model.
- ASR/OCR quality depends on installed optional providers; demo mode remains deterministic.
- LaTeX PDF output requires `tectonic` or `pdflatex`.
- If no local LaTeX compiler exists, the UI reports the compile error, supports `.tex` download, copy LaTeX, and an Overleaf import workflow.

## Git Workflow

Development is on `feature/omnicourse-lens-trials-mvp`. Milestone commits cover scaffold, demo data/indexing, ingestion, search, cheatsheet, graph, QA, frontend, and validation.
