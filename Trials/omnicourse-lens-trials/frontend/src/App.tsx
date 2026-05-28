import { Bot, BrainCircuit, Download, FileText, Loader2, Network, Play, RefreshCcw, Search, UploadCloud } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  apiGet,
  apiPost,
  API_BASE,
  compileCheatsheet,
  Course,
  DatasetVideo,
  datasetVideos,
  EvidenceItem,
  ingestAllDataset,
  ingestDatasetVideo,
  rebuildIndex,
  SearchResult,
  textSearch
} from "./api";
import CytoscapeGraph, { GraphNode } from "./components/CytoscapeGraph";
import MarkdownMath from "./components/MarkdownMath";
import StatusBadge from "./components/StatusBadge";
import UploadPanel from "./components/UploadPanel";
import VideoEvidenceCard from "./components/VideoEvidenceCard";

type Feature = "search" | "cheatsheet" | "graph" | "qa";

const featureItems = [
  { key: "search" as const, label: "Search Video", icon: Search },
  { key: "cheatsheet" as const, label: "Cheatsheet", icon: FileText },
  { key: "graph" as const, label: "Knowledge Graph", icon: Network },
  { key: "qa" as const, label: "AI Tutor", icon: Bot }
];

export default function App() {
  const [feature, setFeature] = useState<Feature>("search");
  const [videos, setVideos] = useState<DatasetVideo[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<DatasetVideo | null>(null);
  const [course, setCourse] = useState<Course | null>(null);
  const [health, setHealth] = useState<any>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("gradient descent optimization");
  const [image, setImage] = useState<File | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const [cheatsheet, setCheatsheet] = useState<any>(null);
  const [graph, setGraph] = useState<any>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [question, setQuestion] = useState("Why does gradient descent move opposite to the gradient?");
  const [qa, setQa] = useState<any>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const load = useCallback(async () => {
    const [videoItems, healthInfo] = await Promise.all([datasetVideos(), apiGet<any>("/api/health")]);
    setVideos(videoItems);
    setHealth(healthInfo);
    const preferred = videoItems.find((video) => video.ingestion_status === "ingested") || videoItems[0] || null;
    setSelectedVideo(preferred);
    try {
      const courseId = preferred?.course_id || "real_i2ml";
      setCourse(await apiGet<Course>(`/api/courses/${courseId}`));
    } catch {
      setCourse(null);
    }
  }, []);

  useEffect(() => {
    load().catch((err) => setStatus(String(err)));
  }, [load]);

  useEffect(() => {
    if (selectedResult?.video_url && videoRef.current) {
      videoRef.current.src = `${API_BASE}${selectedResult.video_url}#t=${Math.max(0, Math.floor(selectedResult.start_time))}`;
      videoRef.current.load();
      videoRef.current.currentTime = Math.max(0, selectedResult.start_time);
    }
  }, [selectedResult]);

  const lectureId = selectedVideo?.lecture_id || course?.lectures?.[0]?.lecture_id || "";
  const courseId = selectedVideo?.course_id || course?.course_id || "real_i2ml";
  const videoIds = selectedVideo ? [selectedVideo.video_id] : undefined;

  const runIngestSelected = async () => {
    if (!selectedVideo) return;
    setBusy(true);
    setStatus(`Ingesting ${selectedVideo.title}`);
    try {
      await ingestDatasetVideo(selectedVideo.video_id);
      await load();
      setStatus("Selected real video ingested and indexed.");
    } finally {
      setBusy(false);
    }
  };

  const runSearch = async () => {
    setBusy(true);
    setStatus("Searching real video moments...");
    try {
      let payload: any;
      if (image) {
        const { imageSearch } = await import("./api");
        payload = await imageSearch({ course_id: courseId, query, video_ids: videoIds, top_k: 6, image });
      } else {
        payload = await textSearch({ course_id: courseId, query, video_ids: videoIds, top_k: 6 });
      }
      setResults(payload.results || []);
      setSelectedResult(payload.results?.[0] || null);
      setFeature("search");
      setStatus(`Search self-check: ${payload.self_check?.score ?? "n/a"}/10`);
    } finally {
      setBusy(false);
    }
  };

  const runCheatsheet = async () => {
    setBusy(true);
    setStatus("Generating evidence-grounded cheatsheet...");
    try {
      const payload = await apiPost<any>("/api/cheatsheet", {
        course_id: courseId,
        lecture_ids: [lectureId].filter(Boolean),
        video_ids: videoIds,
        focus_topics: query,
        max_pages: 2,
        style: "exam"
      });
      setCheatsheet(payload);
      setFeature("cheatsheet");
      setStatus(`Cheatsheet self-check: ${payload.self_check?.score ?? "n/a"}/10`);
    } finally {
      setBusy(false);
    }
  };

  const runCompile = async () => {
    if (!cheatsheet?.tex_content) return;
    setBusy(true);
    try {
      const result = await compileCheatsheet({ tex_content: cheatsheet.tex_content });
      setCheatsheet({ ...cheatsheet, compile_result: result, pdf_file_url: result.pdf_file_url || cheatsheet.pdf_file_url });
      setStatus(result.ok ? "LaTeX compiled locally." : "Local compile unavailable; use TEX download or Overleaf workflow.");
    } finally {
      setBusy(false);
    }
  };

  const runGraph = async () => {
    setBusy(true);
    setStatus("Building pruned knowledge graph...");
    try {
      const payload = await apiPost<any>("/api/knowledge-graph", {
        course_id: courseId,
        lecture_ids: [lectureId].filter(Boolean),
        video_ids: videoIds,
        focus_topic: query,
        max_concepts: 24,
        include_moments: true
      });
      setGraph(payload);
      setSelectedNode(payload.nodes?.[0] || null);
      setFeature("graph");
      setStatus(`Graph: ${payload.nodes?.length || 0} nodes, ${payload.edges?.length || 0} edges`);
    } finally {
      setBusy(false);
    }
  };

  const runQa = async () => {
    setBusy(true);
    setStatus("Retrieving evidence and asking the tutor...");
    try {
      const { askTutor } = await import("./api");
      const payload = await askTutor({
        course_id: courseId,
        question,
        video_id: selectedVideo?.video_id,
        top_k: 5,
        image
      });
      setQa(payload);
      setFeature("qa");
      setStatus(`QA confidence ${Math.round((payload.confidence || 0) * 100)}%; self-check ${payload.self_check?.score ?? "n/a"}/10`);
    } finally {
      setBusy(false);
    }
  };

  const jumpToEvidence = (item: SearchResult | EvidenceItem) => {
    const result: SearchResult = {
      ...(item as SearchResult),
      course_id: courseId,
      video_url: (item as SearchResult).video_url || (item as any).video_url || (selectedVideo ? `/api/dataset/videos/${selectedVideo.video_id}/stream` : undefined),
      concept_tags: (item as SearchResult).concept_tags || [],
      score_breakdown: (item as SearchResult).score_breakdown || {}
    };
    setSelectedResult(result);
  };

  const activeVideoUrl = selectedResult?.video_url
    ? `${API_BASE}${selectedResult.video_url}#t=${Math.max(0, Math.floor(selectedResult.start_time))}`
    : selectedVideo
      ? `${API_BASE}/api/dataset/videos/${selectedVideo.video_id}/stream`
      : "";

  const selectedVideoMoments = useMemo(() => {
    const lecture = course?.lectures?.find((item) => item.lecture_id === selectedVideo?.lecture_id);
    return lecture?.moments || [];
  }, [course, selectedVideo]);

  return (
    <div className="atlas-shell">
      <main className="atlas-main">
        <header className="atlas-header">
          <div>
            <h1>OmniCourse Atlas</h1>
            <p>Real Dataset videos from `/home/haoqian/Data/OmniCourse-Lens/Dataset`</p>
          </div>
          <div className="provider-row">
            <StatusBadge label="GPT-4o" ok={Boolean(health?.providers?.llm?.available)} muted={Boolean(!health?.providers?.llm?.available)} />
            <StatusBadge label="Dataset" ok={Boolean(health?.providers?.dataset?.exists)} />
            <StatusBadge label="InternVideo3" ok={Boolean(health?.providers?.search?.internvideo3?.available)} muted={Boolean(health?.providers?.search?.internvideo3?.local_checkpoint_detected)} />
            <StatusBadge label="DeepSeek OCR" ok={Boolean(health?.providers?.deepseek_ocr?.available)} />
          </div>
        </header>

        <section className="dataset-panel">
          <div className="panel-head">
            <h2>Dataset Video Loader</h2>
            <div className="panel-actions">
              <button onClick={load} disabled={busy}><RefreshCcw size={16} /> Refresh</button>
              <button onClick={runIngestSelected} disabled={busy || !selectedVideo}><UploadCloud size={16} /> Ingest Selected</button>
              <button onClick={() => ingestAllDataset(9).then(() => setStatus("Ingest-all job started."))} disabled={busy}><UploadCloud size={16} /> Ingest All</button>
              <button onClick={() => rebuildIndex().then(() => setStatus("Index rebuilt."))} disabled={busy}><RefreshCcw size={16} /> Rebuild Index</button>
            </div>
          </div>
          <div className="video-strip">
            {videos.map((video) => (
              <button
                key={video.video_id}
                className={`video-pill ${selectedVideo?.video_id === video.video_id ? "selected" : ""}`}
                onClick={() => setSelectedVideo(video)}
              >
                <span>{video.title}</span>
                <small>{video.ingestion_status} / {Math.round((video.duration || 0) / 60)} min</small>
              </button>
            ))}
          </div>
        </section>

        <section className="workspace-stage">
          <div className="video-stage">
            {activeVideoUrl ? <video ref={videoRef} src={activeVideoUrl} controls poster={selectedResult?.thumbnail_url ? `${API_BASE}${selectedResult.thumbnail_url}` : undefined} /> : <div className="preview-empty">Select a Dataset video</div>}
            <div className="video-meta">
              <strong>{selectedVideo?.title || "No video selected"}</strong>
              {selectedResult && <span>{selectedResult.start_time.toFixed(0)}-{selectedResult.end_time.toFixed(0)}s</span>}
            </div>
          </div>
          <div className="workspace-output">
            {feature === "search" && <SearchWorkspace results={results} selected={selectedResult} onJump={jumpToEvidence} moments={selectedVideoMoments} />}
            {feature === "cheatsheet" && <CheatsheetWorkspace cheatsheet={cheatsheet} onCompile={runCompile} />}
            {feature === "graph" && <GraphWorkspace graph={graph} selectedNode={selectedNode} setSelectedNode={setSelectedNode} />}
            {feature === "qa" && <QAWorkspace qa={qa} onJump={jumpToEvidence} />}
          </div>
        </section>
      </main>

      <aside className="feature-sidebar">
        <div className="feature-tabs">
          {featureItems.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.key} className={feature === item.key ? "active" : ""} onClick={() => setFeature(item.key)}>
                <Icon size={18} />
                {item.label}
              </button>
            );
          })}
        </div>
        <div className="sidebar-controls">
          <label>Active real video</label>
          <select value={selectedVideo?.video_id || ""} onChange={(event) => setSelectedVideo(videos.find((video) => video.video_id === event.target.value) || null)}>
            {videos.map((video) => <option key={video.video_id} value={video.video_id}>{video.title}</option>)}
          </select>
          {feature === "search" && (
            <>
              <label>Search query</label>
              <textarea value={query} onChange={(event) => setQuery(event.target.value)} />
              <UploadPanel file={image} onFile={setImage} label="Optional image query" />
              <button onClick={runSearch} disabled={busy}>{busy ? <Loader2 className="spin" size={16} /> : <Search size={16} />} Search Moments</button>
            </>
          )}
          {feature === "cheatsheet" && (
            <>
              <label>Focus topics</label>
              <textarea value={query} onChange={(event) => setQuery(event.target.value)} />
              <button onClick={runCheatsheet} disabled={busy}>{busy ? <Loader2 className="spin" size={16} /> : <FileText size={16} />} Generate Cheatsheet</button>
              <button onClick={runCompile} disabled={busy || !cheatsheet?.tex_content}>Compile LaTeX</button>
            </>
          )}
          {feature === "graph" && (
            <>
              <label>Graph focus</label>
              <input value={query} onChange={(event) => setQuery(event.target.value)} />
              <button onClick={runGraph} disabled={busy}>{busy ? <Loader2 className="spin" size={16} /> : <Network size={16} />} Generate Graph</button>
            </>
          )}
          {feature === "qa" && (
            <>
              <label>Tutor question</label>
              <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
              <UploadPanel file={image} onFile={setImage} label="Optional question image" />
              <button onClick={runQa} disabled={busy}>{busy ? <Loader2 className="spin" size={16} /> : <BrainCircuit size={16} />} Ask AI Tutor</button>
            </>
          )}
        </div>
        {status && <div className="status-note">{status}</div>}
      </aside>
    </div>
  );
}

function SearchWorkspace({ results, selected, onJump, moments }: { results: SearchResult[]; selected: SearchResult | null; onJump: (item: SearchResult) => void; moments: any[] }) {
  return (
    <div className="workspace-grid">
      <div className="result-column">
        {(results.length ? results : moments.slice(0, 6)).map((item: any) => {
          const result = item.moment_id && item.score === undefined
            ? {
                ...item,
                lecture_title: item.lecture_id,
                score: 0.5,
                matched_reason: "Indexed real Dataset moment",
                matched_modalities: ["ASR transcript", "Slide OCR", "Keyframe"],
                transcript_snippet: item.transcript,
                ocr_snippet: item.ocr_text,
                formula_latex: item.formula_latex,
                score_breakdown: {},
                video_url: item.video_id ? `/api/dataset/videos/${item.video_id}/stream` : undefined
              }
            : item;
          return <VideoEvidenceCard key={result.moment_id} item={result} onSelect={() => onJump(result)} />;
        })}
      </div>
      <div className="detail-panel">
        <h3>{selected ? "Selected Evidence" : "Real Video Evidence"}</h3>
        {selected ? (
          <>
            <p>{selected.matched_reason}</p>
            <div className="score-grid compact">
              {Object.entries(selected.score_breakdown || {}).map(([key, value]) => (
                <div key={key}><span>{key.replace(/_/g, " ")}</span><meter min={0} max={1} value={value} /></div>
              ))}
            </div>
          </>
        ) : (
          <p>Select a moment to jump the main player and inspect score breakdowns.</p>
        )}
      </div>
    </div>
  );
}

function CheatsheetWorkspace({ cheatsheet, onCompile }: { cheatsheet: any; onCompile: () => void }) {
  if (!cheatsheet) return <EmptyState title="Generate a cheatsheet" text="Use the right sidebar to generate LaTeX from the selected real Dataset video." />;
  return (
    <div className="cheatsheet-workspace">
      <div className="cheatsheet-toolbar">
        {cheatsheet.tex_file_url && <a href={`${API_BASE}${cheatsheet.tex_file_url}`} target="_blank"><Download size={16} /> Download .tex</a>}
        {cheatsheet.pdf_file_url && <a href={`${API_BASE}${cheatsheet.pdf_file_url}`} target="_blank"><Download size={16} /> Download .pdf</a>}
        <button onClick={onCompile}>Compile LaTeX</button>
        <button onClick={() => navigator.clipboard.writeText(cheatsheet.tex_content)}>Copy LaTeX</button>
      </div>
      <div className="compile-note">
        <strong>Compile status:</strong> {cheatsheet.compile_result?.ok ? "Local PDF generated." : cheatsheet.self_check?.pdf_compile_error || cheatsheet.compile_result?.compile_error || "Use Download .tex, then import into Overleaf as main.tex."}
      </div>
      <div className="latex-columns">
        <pre className="latex-preview">{cheatsheet.tex_content}</pre>
        <MarkdownMath text={latexToMarkdownPreview(cheatsheet.tex_content)} />
      </div>
    </div>
  );
}

function GraphWorkspace({ graph, selectedNode, setSelectedNode }: { graph: any; selectedNode: GraphNode | null; setSelectedNode: (node: GraphNode) => void }) {
  if (!graph) return <EmptyState title="Generate a knowledge graph" text="Cytoscape fcose layout will build a zoomable, pannable graph from the selected real video evidence." />;
  return (
    <div className="graph-workspace">
      <CytoscapeGraph nodes={graph.nodes || []} edges={graph.edges || []} onSelect={setSelectedNode} />
      <aside className="graph-inspector">
        <h3>{selectedNode?.label || "Graph Summary"}</h3>
        <p>{selectedNode ? selectedNode.type.replace("_", " ") : graph.summary}</p>
        {selectedNode?.timestamp !== undefined && <p>{selectedNode.timestamp.toFixed(0)}s</p>}
        {Boolean(selectedNode?.metadata?.thumbnail_url) && <img src={`${API_BASE}${String(selectedNode?.metadata?.thumbnail_url)}`} alt={selectedNode?.label || "graph node"} />}
        <div className="graph-metrics">{(graph.nodes || []).length} nodes / {(graph.edges || []).length} edges</div>
      </aside>
    </div>
  );
}

function QAWorkspace({ qa, onJump }: { qa: any; onJump: (item: EvidenceItem) => void }) {
  if (!qa) return <EmptyState title="Ask the AI Tutor" text="The answer will render Markdown and LaTeX with evidence cards and timestamp jumps." />;
  return (
    <div className="qa-workspace">
      <div className="answer-card">
        <div className="answer-head"><Bot size={18} /><strong>{qa.generation_mode}</strong><span>{Math.round((qa.confidence || 0) * 100)}%</span></div>
        <MarkdownMath text={qa.answer} />
      </div>
      <div className="result-column">
        {(qa.evidence || []).map((item: EvidenceItem) => <VideoEvidenceCard key={item.moment_id} item={item} onSelect={() => onJump(item)} />)}
      </div>
    </div>
  );
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="empty-state"><Play size={26} /><h3>{title}</h3><p>{text}</p></div>;
}

function latexToMarkdownPreview(tex: string) {
  return tex
    .replace(/\\section\*\{([^}]+)\}/g, "## $1")
    .replace(/\\item/g, "-")
    .replace(/\\begin\{[^}]+\}|\\end\{[^}]+\}/g, "")
    .replace(/\\\[/g, "\n$$")
    .replace(/\\\]/g, "$$\n")
    .slice(0, 5000);
}
