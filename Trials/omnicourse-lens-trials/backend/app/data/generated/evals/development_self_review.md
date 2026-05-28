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

## Real Videos Ingested

After the core-functionality repair pass on May 29, 2026, all discovered Dataset videos were ingested and indexed:

- Videos ingested: 9 / 9
- Course: `real_i2ml`
- Lectures: 9
- Real Dataset moments: 79
- Total indexed moments including smoke-test demo fallback course: 91
- Associated slides PDF text is used as `slide_pdf_text` OCR/evidence for the Dataset lectures.
- Extracted keyframes are available locally under `backend/app/static/frames/real_i2ml/`.

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
- `python scripts/smoke_test.py` after all-video Dataset ingestion
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

- All 9 videos are now ingested locally, but ASR is still not true speech transcription by default. The current evidence is a blend of fallback ASR segments and slide PDF text. Enable Whisper with `OMNICOURSE_ENABLE_WHISPER=1` for actual speech transcripts.
- DeepSeek OCR and InternVideo3 are adapter-ready but require endpoint/CLI configuration for active use.
- Frame OCR is unavailable in this environment because PaddleOCR/EasyOCR/Tesseract/DeepSeek OCR are not configured. Slide PDF text currently provides the strongest OCR-like evidence.
- No local LaTeX compiler is installed in this environment, so PDF generation reports a clear unavailable status.
- The search stack is still hybrid lexical/TF-IDF + image color histogram fallback, not a full production dense multimodal retrieval stack.
- Vite build passes but warns that the main JS bundle is large because Cytoscape, KaTeX, and motion libraries are included.

## Next Steps

- Run Whisper transcription for all 9 videos or import official captions if available.
- Add a real InternVideo3 scoring microservice using the existing checkpoint.
- Add a stronger OCR provider for actual frame text extraction.
- Add CLIP/SigLIP image embeddings for better visual search.
- Replace heuristic self-evaluation fast paths with real GPT-4o judge calls where latency allows.
- Split frontend bundles for faster initial load.

## Knowledge Graph Repair Pass - May 29, 2026

Implemented after reviewing open-source graph visualization approaches including Cytoscape.js/fCoSE and react-force-graph:

- Rebuilt `GraphService` so the graph is generated from real timestamped evidence instead of sparse toy tags.
- Added concept normalization, STEM phrase extraction, slide-title concept mapping, prerequisite edges, co-occurrence edges, formula cleanup, visual evidence nodes, graph metrics, and safer lecture/video filtering.
- Added `max_moments` and graph `metrics` to the API schema.
- Replaced the basic graph renderer with a product graph panel: searchable nodes, node-type filters, fCoSE layout tuning, hover labels, edge-label toggle, Fit/Focus/Reset controls, neighborhood highlighting, and a richer inspector.
- Added timestamp jump support from graph nodes back into the central video workspace.

Validation:

- `python -m py_compile backend/app/services/graph_service.py backend/app/schemas.py`
- Direct graph generation for `08_i2ml_01_ml_basics_07_optimization`: 43 nodes, 167 edges, 15 concepts, 6 formulas, 10 moment nodes, 10 visual evidence nodes.
- `POST /api/knowledge-graph` returned the same graph metrics through the running backend.
- `cd frontend && npm run build`
- `pytest tests/test_api_smoke.py -q`
- `python scripts/smoke_test.py`
