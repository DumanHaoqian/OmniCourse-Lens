# Visual UI Check Notes

Browser Use / Computer Use is not available in the current Codex session, so this file records the manual visual QA checklist to run from the local dev server.

## Start

```bash
cd /home/haoqian/Data/OmniCourse-Lens/Trials/omnicourse-lens-trials
bash scripts/run_backend.sh
bash scripts/run_frontend.sh
```

Open:

```text
http://127.0.0.1:5173
```

## Required visual checks

- The main video player is centered and remains the primary workspace.
- The right sidebar primary tabs are exactly: Search Video, Cheatsheet, Knowledge Graph, AI Tutor.
- The left Dataset loader lists real videos from `/home/haoqian/Data/OmniCourse-Lens/Dataset`.
- Search result clicks switch the central player to the result video and timestamp.
- Dynamic subtitles update below the video while playback time changes.
- AI Tutor output renders Markdown and LaTeX with KaTeX, including:

```latex
\[
\theta := \theta - \alpha \nabla_\theta J(\theta)
\]
```

- AI Tutor sidebar shows the secondary Learning Tools panel.
- Prerequisite Rewind, Misconception Check, Socratic Drill, Formula Tutor, Region Explain, and Study Plan all return evidence-grounded outputs.
- Knowledge Graph uses Cytoscape with zoom/pan, node search/filtering, readable labels, and an inspector.
- Cheatsheet shows LaTeX source, rendered preview, compile status, copy, `.tex`, `.pdf` when available, and Overleaf workflow text.
- Resizable vertical and horizontal handles work without text overlap.

## Latest automated checks

- `npm run build` passed.
- `python scripts/smoke_test.py` passed and includes real Dataset, graph, QA, cheatsheet, provider status, and all learning endpoints.
