# Development Self-Review

## Implemented

- Scaffolded `omnicourse-lens-trials` as a FastAPI + React/Vite web app.
- Generated deterministic demo course data for `ml_foundations`.
- Added JSON indexing for moments, lexical evidence, and keyframe descriptors.
- Added multimodal ingestion with audio extraction, ASR fallback, keyframe extraction, DeepSeek OCR discovery, generic OCR fallback, and formula heuristics.
- Added optional InternVideo3 adapter with HTTP, CLI, local-checkpoint discovery, and disabled fallback mode.
- Added hybrid text/image moment retrieval with modality score breakdowns and timestamp evidence.
- Added LaTeX cheatsheet generation with GPT-4o/fallback modes and self-check.
- Added lightweight educational concept graph generation with prerequisite edges and self-check.
- Added multimodal QA agent with retrieval-first grounding, timestamp citations, GPT-4o/fallback modes, and self-check.
- Added product UI with Search Video, Cheatsheet, Knowledge Graph, and AI Tutor pages.
- Added smoke tests, pytest API smoke test, run scripts, and documentation.

## Validation Run

- `python scripts/create_demo_data.py`: passed.
- `python scripts/rebuild_index.py`: passed.
- `python scripts/smoke_test.py`: passed.
- `pytest tests/test_api_smoke.py -q`: passed with one Starlette deprecation warning.
- `python -m py_compile $(find backend/app scripts -name '*.py' -not -path '*/__pycache__/*')`: passed.
- `cd frontend && npm run build`: passed.

## Provider Detection

- GPT-4o / Azure OpenAI: credentials detected from `/home/haoqian/Data/OmniCourse-Lens/openai_keys.txt`; smoke judge returned pass. Full key was not written to the project.
- InternVideo3: local checkpoint detected at `Trials/checkpoints/InternVideo3-8B-Instruct`; no endpoint/CLI configured, so runtime mode is disabled fallback.
- DeepSeek OCR: no endpoint/API key/model path configured, so runtime mode is disabled fallback.
- ASR: `openai-whisper` import is available; faster-whisper was not detected. Demo uses deterministic ASR records.
- OCR fallback: PaddleOCR/EasyOCR/Tesseract were not detected; demo OCR fallback is active.

## Improvements Made During Validation

- Fixed backend data paths so generated course/index files land inside this project.
- Fixed graph evaluation handling for Pydantic nodes.
- Fixed QA generation-mode reporting so fallback is not mislabeled as GPT-4o when a model call returns empty.
- Fixed frontend TypeScript issues and aligned backend/frontend default ports.
- Added explicit smoke coverage for text search, image search, cheatsheet, graph, QA, and self-check metadata.

## Commit Milestones

- `0424352` chore: scaffold OmniCourse Lens Trials MVP
- `36d259e` feat: add demo course data and indexing pipeline
- `215ecb1` feat: add multimodal video ingestion with ASR and OCR
- `703e376` feat: implement multimodal lecture moment search
- `bea0024` feat: add evidence-grounded LaTeX cheatsheet generation
- `10b77ce` feat: add educational concept graph generation
- `f9c217b` feat: add evidence-grounded multimodal QA agent
- `4b013e9` feat: add product web UI for OmniCourse Lens Trials
- Final validation/docs commit: this review is included in the final milestone commit.

## Remaining Limitations

- The MVP uses JSON storage and local indexes instead of Qdrant/PostgreSQL/Neo4j.
- InternVideo3 is not loaded by default because the checkpoint is heavy; configure endpoint/CLI for production scoring.
- Image retrieval uses deterministic PIL descriptors unless a stronger visual embedding provider is added.
- DeepSeek OCR is implemented as a provider interface but needs endpoint/API configuration.
- PDF cheatsheet output requires `tectonic` or `pdflatex`; otherwise `.tex` is returned.

## Next Steps

- Add an InternVideo3 scoring microservice around the existing checkpoint.
- Add CLIP/SigLIP image embeddings for stronger image-to-moment retrieval.
- Add persistent vector storage and background ingestion jobs.
- Add richer temporal clipping around retrieved moments.
- Add user accounts/course uploads when moving beyond the hackathon MVP.
