# OmniCourse-Atlas Research-Informed Rebuild Audit

## Current baseline

The project already has a real Dataset-aware FastAPI backend, React/Vite frontend, dataset video discovery, ingestion endpoints, ASR/OCR/keyframe moment construction, hybrid search, QA, cheatsheet generation, graph generation, provider status, dynamic subtitles, and a center-video workspace with a right feature sidebar.

## Research directions folded into the rebuild

- VideoRAG principle: do not send a whole long lecture into an LLM for every request. Convert videos into timestamped moments, retrieve compact multimodal evidence, then answer or generate artifacts.
- DeepSeek-OCR principle: prefer a strong vision-text OCR provider for slides/frames, but keep fallback OCR and confidence guards because OCR can fail or hallucinate.
- InternVideo3 principle: treat video understanding as an optional clip-level scoring/reranking provider, lazy-loaded so the app still runs without heavyweight checkpoints.
- GraphRAG principle: concepts, formulas, moments, and prerequisite edges should be part of retrieval and learning, not a decorative graph only.
- Cytoscape/fCoSE principle: graph readability comes from pruning, clustering, zoom/pan, hover labels, and controlled default density.

## Gaps to fix in this rebuild

1. The system needs a clear Skill Library abstraction instead of isolated endpoints.
2. Generated answers and learning artifacts need a formal Evidence Ledger so every claim can be traced to timestamped multimodal evidence.
3. The six learning assistant features requested by the user are missing as callable product features.
4. The smoke test needs to validate real dataset discovery plus learning endpoints, not just the original four features.
5. The frontend needs a compact learning tools section that lives inside the existing AI Tutor flow while preserving the four primary sidebar tabs.
6. Development self-review needs to record provider status, real videos discovered, tests, commits, and limitations.

## Safety and repository notes

- Branch for this rebuild: `feature/research-informed-multimodal-rebuild`.
- Do not commit raw Dataset videos, checkpoints, model weights, API keys, generated caches, `node_modules`, or virtual environments.
- Current untracked file outside this project, `../../gpt4o.py`, is ignored for this task and must not be committed.
