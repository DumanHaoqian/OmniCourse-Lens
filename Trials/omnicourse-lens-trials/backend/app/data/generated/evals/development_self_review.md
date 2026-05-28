# Overnight Quality Rebuild Self-Review

## Rebuild Summary

This pass moved OmniCourse from a mock-first demo to a real Dataset-first product workspace. The app now discovers, ingests, indexes, searches, and displays videos from:

```text
/home/haoqian/Data/OmniCourse-Lens/Dataset
```

Mock `ml_foundations` data remains only as fallback and smoke-test support.

## Real Dataset Videos Discovered

- Total videos discovered: 9
- Extensions scanned: `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, `.m4v`
- Dataset root is fixed in backend config and arbitrary filesystem browsing is not exposed.

## Real Video Ingested

Ingested and indexed:

- `08_i2ml_01_ml_basics_07_optimization__video.mp4`
- Course: `real_i2ml`
- Lecture: `08_i2ml_01_ml_basics_07_optimization`
- Duration: 1675.621587 seconds
- Moments: 10
- Extracted keyframes: 10
- Associated slides PDF text used as `slide_pdf_text` OCR evidence.

## Improvements Implemented

- Added `/api/dataset/videos`, `/api/dataset/ingest`, `/api/dataset/ingest-all`, `/api/jobs/start-ingest-all`, `/api/jobs/{job_id}`, `/api/index/rebuild`, and `/api/dataset/videos/{video_id}/stream`.
- Added `DatasetService` with stable `video_id`, safe Dataset-root validation, PDF slide text extraction, status tracking, and index rebuild integration.
- Extended schemas and search filtering with `video_id` / `video_ids`.
- Improved ingestion with supplemental slide/PDF evidence, real keyframes, formula extraction, and explicit provider metadata.
- Updated OCR fallback so real extracted frames are not mislabeled as fake OCR when no OCR provider is available.
- Added optional OpenAI Whisper path gated by `OMNICOURSE_ENABLE_WHISPER=1`.
- Added backend LaTeX compile endpoint with `tectonic`, `pdflatex`, and `xelatex` attempts.
- Rebuilt frontend into a real workspace: main Dataset loader/video/evidence area plus right sidebar with exactly four feature tabs.
- Added Markdown + LaTeX rendering with `react-markdown`, `remark-math`, `rehype-katex`, and KaTeX CSS.
- Replaced the toy graph with Cytoscape.js + fcose layout, zoom/pan, pruned graph generation, node colors, and inspector.
- Improved QA answer structure so it includes direct answer, formula explanation, evidence, review clip, and follow-up question.
- Updated smoke tests to exercise the real Dataset path instead of only mock data.

## Validation Results

Passed:

- `python -m py_compile backend/app/main.py backend/app/services/evaluation_service.py scripts/smoke_test.py tests/test_api_smoke.py`
- `cd frontend && npm run build`
- `python scripts/smoke_test.py`
- `pytest tests/test_api_smoke.py -q`

Smoke checks passed:

- health endpoint
- real Dataset video discovery
- real video ingest/index status
- real text search for gradient descent
- real text search for slide evidence terms
- image search using an extracted real keyframe
- QA answer with LaTeX-friendly math
- cheatsheet generation and compile-status endpoint
- pruned knowledge graph generation
- provider status endpoint

## Provider Status

- GPT-4o: credentials detected from `/home/haoqian/Data/OmniCourse-Lens/openai_keys.txt`; full key was not committed or printed.
- ASR: `openai-whisper` import is available, but Whisper execution is disabled unless `OMNICOURSE_ENABLE_WHISPER=1`; faster-whisper not detected.
- DeepSeek OCR: endpoint/model not configured, so disabled fallback.
- OCR fallback: PaddleOCR/EasyOCR/Tesseract not detected; associated slides PDF text provides real slide evidence for this Dataset.
- InternVideo3: local checkpoint detected; no endpoint/CLI configured, so disabled fallback by default.
- LaTeX compiler: `tectonic`, `pdflatex`, and `xelatex` not detected; web UI provides compile status, `.tex` download, copy LaTeX, and Overleaf workflow.

## Git Commits In This Rebuild

- `2ea142c` feat: ingest and index real Dataset lecture videos
- `9595deb` feat: redesign workspace UI with LaTeX and Cytoscape graph
- Final validation/docs commit: includes updated smoke tests, README, provider checks, and this review.

## Known Remaining Issues

- Only the optimization video is pre-ingested in the committed baseline; the UI and endpoints can ingest all 9 videos, but all-video ingestion may take longer.
- Real ASR is not run by default to avoid long blocking Whisper jobs. Enable with `OMNICOURSE_ENABLE_WHISPER=1`.
- DeepSeek OCR and InternVideo3 are adapter-ready but require endpoint/CLI configuration for active use.
- No local LaTeX compiler is installed in this environment, so PDF generation reports a clear unavailable status.
- Vite build passes but warns that the main JS bundle is large because Cytoscape and KaTeX are included.

## Next Steps

- Run background ingest-all overnight to pre-index all nine videos.
- Add a real InternVideo3 scoring microservice using the existing checkpoint.
- Add a stronger OCR provider for actual frame text extraction.
- Add CLIP/SigLIP image embeddings for better visual search.
- Split frontend bundles for faster initial load.
