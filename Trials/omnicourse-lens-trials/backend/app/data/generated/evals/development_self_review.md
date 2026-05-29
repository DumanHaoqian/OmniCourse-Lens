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
- ASR: local `faster-whisper` runner is active through the `omniC` environment; default model is `small.en` with auto CUDA/float16 and CPU fallback. OpenAI Whisper remains a fallback.
- DeepSeek OCR: local `deepseek-ai/DeepSeek-OCR` checkpoint detected at `Trials/checkpoints/DeepSeek-OCR`; backend provider mode is `local_hf_lazy`.
- OCR fallback: PaddleOCR/EasyOCR/Tesseract not detected; DeepSeek-OCR is now the active frame/image OCR provider, with associated slide PDF text as supplemental evidence.
- InternVideo3: local `InternVideo3-8B-Instruct` checkpoint detected at `Trials/checkpoints/InternVideo3-8B-Instruct`; backend provider mode is `local_hf_lazy`. Local reranking runs through the `omniC` Python environment to avoid Transformers-version conflicts with DeepSeek-OCR.
- LaTeX compiler: `tectonic` is installed and detected; backend compile endpoint generates PDFs. The UI still keeps `.tex` download, copy LaTeX, and Overleaf workflow as fallback/export options.

## Git Commits In This Rebuild

- `2ea142c` feat: ingest and index real Dataset lecture videos
- `9595deb` feat: redesign workspace UI with LaTeX and Cytoscape graph
- Final validation/docs commit: includes updated smoke tests, README, provider checks, and this review.

## Known Remaining Issues

- Real `real_i2ml` ASR has now been refreshed across all 9 Dataset videos: 79 real moments use 1659 `faster_whisper_small.en_cuda_float16` subtitle segments and no `fallback_asr` remains in the real course/index.
- DeepSeek-OCR local inference is active, but it is a heavy model and should be used selectively for ingestion/image OCR rather than on every UI refresh.
- InternVideo3 local inference is active and verified through a subprocess runner. A persistent FastAPI scorer is available via `scripts/run_internvideo3_server.sh` so the 8B checkpoint can be loaded once for demos.
- Dense text retrieval now uses `sentence-transformers/all-MiniLM-L6-v2`; the rebuilt index contains 91 vectors with dimension 384.
- Image retrieval now uses OpenCLIP `ViT-B-32/laion2b_s34b_b79k`; the rebuilt index contains 91 frame vectors with dimension 512.
- PaddleOCR/EasyOCR/Tesseract are still unavailable; DeepSeek-OCR plus slide PDF text currently provide OCR evidence.
- Local LaTeX PDF generation is now active through `tectonic`; first compile may be slower while Tectonic initializes its bundle cache.
- The search stack is now hybrid lexical + sentence-transformers dense text + OpenCLIP visual + OCR/formula/concept + InternVideo3 reranking. A production vector DB is still a future scalability step.
- Vite build passes but warns that the main JS bundle is large because Cytoscape, KaTeX, and motion libraries are included.

## Next Steps

- Keep InternVideo3 server warm during demos to avoid 8B cold-start latency.
- Add a real InternVideo3 scoring microservice using the existing checkpoint.
- Add a stronger OCR provider for actual frame text extraction.
- Add CLIP/SigLIP image embeddings for better visual search.
- Replace heuristic self-evaluation fast paths with real GPT-4o judge calls where latency allows.
- Split frontend bundles for faster initial load.

## Real DeepSeek-OCR and PDF Compile Completion Pass - May 29, 2026

Implemented after finding that real course moments mostly contained slide/PDF text but not true keyframe OCR:

- Added `scripts/refresh_real_ocr.py` to run the local `deepseek-ai/DeepSeek-OCR` checkpoint across extracted Dataset keyframes.
- Refreshed `real_i2ml` with true frame OCR and rebuilt the index.
- Provider counts after refresh:
  - Real course/index moments: 79
  - Empty OCR moments: 0
  - `deepseek_ocr` blocks: 190
  - `slide_pdf_text` blocks: 41
  - `deepseek_ocr_formula_heuristic` formula blocks: 280
  - `heuristic_math_ocr` formula blocks: 71
- Updated Search result labeling so OCR evidence from the local model is shown as `DeepSeek frame OCR`.
- Verified text search for "gradient descent optimization learning goals" returns optimization timestamps with modalities: audio transcript, DeepSeek frame OCR, formula, text embedding, and concept tag.
- Verified QA for "Why does gradient descent move opposite to the gradient?" returns GPT-4o Markdown with display LaTeX, timestamp citations, and DeepSeek frame OCR evidence.
- Installed `tectonic` and increased backend LaTeX compile timeout to 180 seconds.
- Cleaned GPT-4o cheatsheet output so markdown fences such as `\`\`\`latex` are stripped before saving/compiling.
- Verified `/api/cheatsheet/compile` creates a real PDF.
- Verified cheatsheet generation for the real optimization lecture creates both `.tex` and `.pdf` with self-check score 10/10.

Validation:

- `python -m py_compile backend/app/services/*.py scripts/*.py`
- `cd frontend && npm run build`
- `pytest tests/test_api_smoke.py -q` passed in 140.59s

## InternVideo3 Persistent Server Validation - May 29, 2026

Implemented/validated after adding the persistent scorer script:

- Started `scripts/run_internvideo3_server.sh` on `127.0.0.1:8011`.
- Verified `GET /health` returned status `ok` and detected the local `InternVideo3-8B-Instruct` checkpoint.
- Called `POST /score` on a real optimization lecture clip:
  - Video: `08_i2ml_01_ml_basics_07_optimization__video.mp4`
  - Time window: `900-930s`
  - Query: `gradient descent learning rate update rule`
  - Cold start: 93.13s to load the 8B checkpoint and score.
  - Warm call: 2.93s with score `0.95`.
  - Model reason: "The clip shows the gradient descent update rule ... and explains the learning rate alpha."
- Stopped the validation server afterward to avoid holding GPU memory. For demos, run it again and set `INTERNVIDEO3_ENDPOINT=http://127.0.0.1:8011/score`.

## DeepSeek-OCR and InternVideo3 Activation Pass - May 29, 2026

Implemented after the provider badges still showed warning states:

- Added a real local DeepSeek-OCR provider in `backend/app/services/deepseek_ocr_service.py` using the official Transformers-style `AutoModel` / `AutoTokenizer` / `model.infer(...)` path.
- Downloaded the DeepSeek-OCR checkpoint under `Trials/checkpoints/DeepSeek-OCR` and kept it out of Git.
- Added OCR output cleanup so user-facing evidence does not show DeepSeek grounding tags such as `<|det|>`.
- Added a real InternVideo3 local scoring runner at `scripts/internvideo3_score.py`.
- Updated `InternVideo3Service` to expose `local_hf_lazy` provider status and call the runner through `/home/haoqian/miniconda3/envs/omniC/bin/python`.
- Limited local InternVideo3 reranking defaults to top-1 and 8 sampled frames because cold-start loading the 8B checkpoint is expensive.
- Fixed the frontend provider badges so DeepSeek OCR and InternVideo3 reflect real backend availability instead of appearing disabled.

Validation:

- `/api/health` reports `deepseek_ocr.available=true`, `deepseek_ocr.mode=local_hf_lazy`.
- `/api/health` reports `search.internvideo3.available=true`, `search.internvideo3.mode=local_hf_lazy`.
- DeepSeek-OCR was run on a real extracted keyframe and read course text including "Introduction to Machine Learning", "Learning goals", "loss function", and "empirical risk minimization".
- InternVideo3 was run on a real Dataset video clip with query "machine learning introduction" and returned JSON score `1.0`.
- `python -m py_compile backend/app/services/deepseek_ocr_service.py backend/app/services/internvideo3_service.py backend/app/services/search_service.py scripts/internvideo3_score.py`
- `cd frontend && npm run build`

## ASR / Speech-To-Text Activation Pass - May 29, 2026

Implemented after the ASR provider was still effectively falling back:

- Installed `faster-whisper` in the `omniC` environment.
- Added `scripts/asr_transcribe.py`, a standalone ASR runner that returns JSON subtitle segments with start/end timestamps and optional word timestamps.
- Updated `AudioASRService` to call the runner by default during ingestion, cache `.asr.json` transcripts beside extracted WAV files, and fall back to OpenAI Whisper or deterministic segments only when needed.
- Added ASR provider status to `/api/health`: active provider, model, runner Python, CTranslate2 availability, model cache path, VAD, and word-timestamp settings.
- Documented ASR configuration in `.env.example` and README.

Validation:

- `faster_whisper=True` and `ctranslate2=True` in `/home/haoqian/miniconda3/envs/omniC`.
- `scripts/asr_transcribe.py` was run on the first 20 seconds of a real Dataset lecture audio file.
- Output included timestamped speech: "Welcome to Introduction to Machine Learning. I'm Ludwig Bortmann..." and word-level timestamps.
- Backend `AudioASRService.transcribe(...)` integration returned 4 real `faster_whisper_small.en_cpu_int8` subtitle segments for a 20-second real audio clip.
- Initial CUDA CTranslate2 failed because `libcublas.so.12` was not visible to CTranslate2.

Follow-up completion:

- Added CUDA library path injection for CTranslate2.
- Verified `faster_whisper_small.en_cuda_float16` on real audio.
- Refreshed all 9 real Dataset lectures with true ASR and rebuilt the index.

## Embedding Completion Pass - May 29, 2026

- Added `scripts/embed_text.py` and indexed all 91 moments with sentence-transformers `all-MiniLM-L6-v2`, dimension 384.
- Added `scripts/embed_image.py` and indexed all 91 keyframes with OpenCLIP `ViT-B-32/laion2b_s34b_b79k`, dimension 512.
- Updated `SearchService` so `dense_text` is real dense similarity, not sparse TF-IDF.
- Updated image query descriptors so OpenCLIP is the primary visual search path.
- Added `scripts/internvideo3_server.py` and `scripts/run_internvideo3_server.sh` for a persistent local InternVideo3 scorer.

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

## Evidence Playback And Reliability Pass - May 29, 2026

Implemented after the UI/search/graph/model chain still felt brittle:

- Added `EvidenceService` with real per-video evidence and dynamic subtitle APIs:
  - `GET /api/dataset/videos/{video_id}/subtitles`
  - `GET /api/dataset/videos/{video_id}/subtitles.vtt`
  - `GET /api/dataset/videos/{video_id}/evidence`
  - `GET /api/moments/{moment_id}`
- Updated the frontend video workspace to load backend subtitle cues, add a native WebVTT track, and show a custom subtitle bar that updates with video playback time.
- Search result selection now switches the central player to the result video and timestamp, fixing the “change video then search breaks” failure mode.
- Added cross-video fallback search: when the current video has weak results, Search Video explains the scope fallback and shows the best moments across all indexed Dataset videos.
- Reworked search snippets and matched reasons so they are query-centered instead of dumping the first OCR/transcript chunk.
- Cleaned noisy formula OCR blocks in `real_i2ml`: 351 raw formula candidates were reduced to 97 stronger formula-like blocks, and the index was rebuilt.
- Pruned default knowledge graph responses to readable defaults: the optimization graph smoke path now stays at 51 nodes / 200 edges with no runaway edge density.
- Hardened LaTeX compilation:
  - GPT-generated nonexistent `\includegraphics` references are replaced with a visual-evidence note.
  - Bare `\caption{...}` outside a float is converted to normal text.
  - Markdown fences and broken replacement escapes are cleaned before compile.
- Added DeepSeek-OCR cache and interactive heavy-OCR control. Offline ingest/refresh can still run local DeepSeek-OCR; online image search avoids blocking on a multi-minute OCR call unless explicitly enabled.
- Added Azure GPT-4o timeout/retry controls (`AZURE_OPENAI_TIMEOUT`, `AZURE_OPENAI_MAX_RETRIES`) and provider `last_error` reporting.
- Made heavy OpenCLIP index rebuild opt-in with `OMNICOURSE_ENABLE_OPEN_CLIP_INDEX=true`; default rebuild now uses fast PIL visual descriptors.
- Made online query dense embeddings opt-in with `OMNICOURSE_ENABLE_QUERY_DENSE=true`; search remains hybrid through ASR/OCR/formula/concept/visual/sparse text and optional InternVideo3.

Validation:

- `python -m py_compile backend/app/services/*.py scripts/*.py tests/test_api_smoke.py`
- `OMNICOURSE_ENABLE_OPEN_CLIP_INDEX=false python scripts/rebuild_index.py`
- `pytest tests/test_api_smoke.py -q` passed in 5.79s.
- `AZURE_OPENAI_TIMEOUT=12 python scripts/smoke_test.py` passed.
- `cd frontend && npm run build` passed in 31.39s, with the expected large-bundle warning from Cytoscape/KaTeX/motion dependencies.

Latest smoke-test facts:

- Dataset videos discovered: 9
- Tested real video: `08_i2ml_01_ml_basics_07_optimization_647ec61326`
- Real tested video duration: 1675.62s
- Tested video moments: 10
- Dynamic subtitle API: audio cues and OCR cues present; VTT starts with `WEBVTT`.
- GPT-4o detected: yes
- DeepSeek-OCR checkpoint detected: yes, `local_hf_lazy`
- InternVideo3 checkpoint detected: yes, `local_hf_lazy`
- ASR active provider: `faster_whisper`

## Research-Informed Skill-Agent Rebuild Pass - May 29, 2026

Implemented after reframing the paper/product as:

`OmniCourse-Atlas: A Skill-Augmented Multimodal Agent with Video Moment Retrieval for Course Learning`

Research-informed design notes:

- VideoRAG-style principle: raw videos are converted into timestamped moments and compact multimodal evidence before LLM reasoning.
- GraphRAG-style principle: concept/formula/prerequisite graph evidence supports retrieval and learning features instead of acting only as decoration.
- DeepSeek-OCR principle: use the local OCR checkpoint for frame/page reading where possible, but keep cached/fallback OCR so interactive product flows do not block forever.
- InternVideo3 principle: use the local checkpoint as optional lazy video reranking/scoring, not as a hard startup dependency.
- Cytoscape/fCoSE principle: keep graph defaults pruned and inspectable, with zoom/pan/filtering rather than rendering every raw node.

New architecture pieces:

- Added `backend/app/services/skill_router.py`.
- Added `EvidenceLedgerItem` and `SkillDefinition` schemas.
- Added an explicit skill registry exposed through `GET /api/skills`.
- Added `EvidenceLedgerBuilder` so generated learning artifacts cite normalized evidence records with timestamp, modality, provider, score, and reason.

Six new learning features:

- `POST /api/learning/prerequisite-rewind`
- `POST /api/learning/misconception-check`
- `POST /api/learning/socratic-drill`
- `POST /api/learning/formula-derivation`
- `POST /api/learning/region-explain`
- `POST /api/learning/mastery/update`
- `GET /api/learning/mastery/{student_id}`
- `POST /api/learning/study-plan`

Frontend additions:

- Added `frontend/src/components/learning/LearningToolsPanel.tsx`.
- Integrated the learning tools under the existing AI Tutor tab, preserving exactly four primary right-sidebar tabs.
- Learning outputs reuse Markdown + LaTeX rendering and evidence cards with timestamp jump.
- Region explain supports optional image upload and current-frame fallback.

Validation:

- `python -m py_compile backend/app/main.py backend/app/services/learning_features_service.py backend/app/services/skill_router.py backend/app/schemas.py`
- `cd frontend && npm run build` passed.
- `python scripts/smoke_test.py` passed.

Latest full smoke test added checks for:

- skill registry,
- prerequisite rewind,
- misconception detector,
- Socratic drill,
- formula derivation,
- region explain,
- mastery update,
- adaptive study plan.

Latest provider status from smoke test:

- Dataset videos discovered: 9
- Tested real Dataset video: `08_i2ml_01_ml_basics_07_optimization_647ec61326`
- GPT-4o: available through Azure credential loader; only key suffix logged.
- DeepSeek-OCR: available, `local_hf_lazy`, checkpoint under `Trials/checkpoints/DeepSeek-OCR`.
- InternVideo3: available, `local_hf_lazy`, checkpoint under `Trials/checkpoints/InternVideo3-8B-Instruct`.
- ASR: active provider `faster_whisper`.
- LaTeX compiler: `tectonic` available.

Commits in this branch so far:

- `11995ea` chore: audit project and scaffold research-informed rebuild
- `21f746d` feat: add student learning assistant features

UI inspection note:

- Browser Use / Computer Use tooling is not available in this Codex session. I validated frontend compilation with `npm run build` and preserved the existing center-video workspace/right-sidebar layout in source. Manual browser inspection should be run from the local dev server for final visual polish.

Remaining limitations:

- The learning feature outputs are MVP-functional and evidence-grounded, but the UI can still be polished with richer interaction states and a larger result surface.
- Region-level explain currently uses a default bounding box when no explicit user-drawn box is available; a real drag-to-select annotation layer is the next frontend step.
- Mastery profiles are local JSON files, suitable for the hackathon MVP but not multi-user production storage.
- LaTeX compiler: `tectonic`

## Efficiency And Engineering Pass - May 29, 2026

Implemented after profiling the hot paths:

- Added mtime-aware JSON/course caching in `storage.py`.
- Changed `write_json()` invalidation from global cache clearing to file-level invalidation; writing eval logs no longer flushes all course caches.
- Added TTL caching for Dataset video discovery. `GET /api/dataset/videos` no longer rescans/probes repeatedly within the cache window.
- Optimized Dataset thumbnails by loading the real course once per video-list refresh instead of once per video.
- Added cached evidence indexes in `EvidenceService` for `video_id -> moments`, `moment_id -> moment`, subtitles, summaries, and WebVTT.
- Added provider-status TTL caching in `main.py` and `SearchService.describe_provider()`.
- Removed repeated InternVideo3 provider probing from per-moment search scoring. The inline/HTTP/CLI provider decision is now computed once per search.
- Changed local 8B InternVideo3 subprocess reranking to opt-in by default:
  - `INTERNVIDEO3_LOCAL_RERANK=1`
  - `INTERNVIDEO3_LOCAL_RERANK_TOP_N=1`
  Warm HTTP scoring remains the recommended demo path.
- Moved query sparse-vector construction out of per-moment scoring and into the search-level `_rank()` call.
- Added `scripts/perf_check.py` for repeatable latency checks.

Performance check after the pass:

- `health_cached`: median 1.46 ms
- `dataset_videos_cached`: median 4.21 ms
- `subtitles_cached`: median 6.30 ms
- `text_search_current_video`: median 17.96 ms, mean 25.98 ms
- `pytest tests/test_api_smoke.py -q`: passed in 1.13s
- `AZURE_OPENAI_TIMEOUT=12 python scripts/smoke_test.py`: passed
- `cd frontend && npm run build`: passed in 14.62s
