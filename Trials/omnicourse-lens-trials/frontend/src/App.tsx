import { Bot, BrainCircuit, Download, FileText, Loader2, Network, Play, RefreshCcw, Search, UploadCloud } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  apiGet,
  apiPost,
  API_BASE,
  askTutor,
  compileCheatsheet,
  Course,
  DatasetVideo,
  datasetVideos,
  EvidenceItem,
  imageSearch,
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
    setSelectedVideo((current) => {
      const stillAvailable = current ? videoItems.find((video) => video.video_id === current.video_id) : null;
      return stillAvailable || videoItems.find((video) => video.ingestion_status === "ingested") || videoItems[0] || null;
    });
  }, []);

  useEffect(() => {
    load().catch((err) => setStatus(String(err)));
  }, [load]);

  useEffect(() => {
    if (!selectedVideo?.course_id) {
      setCourse(null);
      return;
    }
    apiGet<Course>(`/api/courses/${selectedVideo.course_id}`)
      .then(setCourse)
      .catch(() => setCourse(null));
  }, [selectedVideo?.course_id]);

  useEffect(() => {
    if (selectedResult && videoRef.current) {
      const targetTime = Math.max(0, selectedResult.start_time);
      videoRef.current.currentTime = targetTime;
    }
  }, [selectedResult]);

  const selectVideo = (video: DatasetVideo) => {
    setSelectedVideo(video);
    setSelectedResult(null);
    setResults([]);
  };

  const lectureId = selectedVideo?.lecture_id || course?.lectures?.[0]?.lecture_id || "";
  const courseId = selectedVideo?.course_id || course?.course_id || "real_i2ml";
  const videoIds = selectedVideo ? [selectedVideo.video_id] : undefined;

  const selectedVideoMoments = useMemo(() => {
    const lecture = course?.lectures?.find((item) => item.lecture_id === selectedVideo?.lecture_id);
    return lecture?.moments || [];
  }, [course, selectedVideo]);

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
    setStatus("Searching timestamped moments in the selected real video...");
    try {
      const payload = image
        ? await imageSearch({ course_id: courseId, query, video_ids: videoIds, top_k: 6, image })
        : await textSearch({ course_id: courseId, query, video_ids: videoIds, top_k: 6 });
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
    const raw = item as any;
    const result: SearchResult = {
      moment_id: raw.moment_id,
      video_id: raw.video_id || selectedVideo?.video_id,
      course_id: raw.course_id || courseId,
      lecture_id: raw.lecture_id || selectedVideo?.lecture_id || lectureId,
      lecture_title: raw.lecture_title || selectedVideo?.title || raw.lecture_id || "Selected lecture",
      start_time: Number(raw.start_time || 0),
      end_time: Number(raw.end_time || raw.start_time || 0),
      score: Number(raw.score ?? 0.5),
      score_breakdown: raw.score_breakdown || {},
      matched_reason: raw.matched_reason || "Indexed real Dataset moment",
      matched_modalities: raw.matched_modalities || ["ASR transcript", "OCR", "Keyframe"],
      transcript_snippet: raw.transcript_snippet || raw.transcript || "",
      ocr_snippet: raw.ocr_snippet || raw.ocr_text || "",
      formula_latex: raw.formula_latex || "",
      concept_tags: raw.concept_tags || [],
      thumbnail_url: raw.thumbnail_url,
      video_url: raw.video_url || (raw.video_id || selectedVideo?.video_id ? `/api/dataset/videos/${raw.video_id || selectedVideo?.video_id}/stream` : undefined)
    };
    setSelectedResult(result);
  };

  const activeVideoId = selectedResult?.video_id || selectedVideo?.video_id;
  const activeStreamUrl = selectedResult?.video_url
    ? `${API_BASE}${selectedResult.video_url}`
    : activeVideoId
      ? `${API_BASE}/api/dataset/videos/${activeVideoId}/stream`
      : "";
  const activeVideoUrl = activeStreamUrl && selectedResult ? `${activeStreamUrl}#t=${Math.max(0, Math.floor(selectedResult.start_time))}` : activeStreamUrl;

  const selectedPoster = selectedResult?.thumbnail_url || selectedVideo?.thumbnail;
  const selectedTimestamp = selectedResult ? `${selectedResult.start_time.toFixed(0)}-${selectedResult.end_time.toFixed(0)}s` : "full lecture";

  return (
    <div className="atlas-shell watch-layout">
      <aside className="video-library" aria-label="Dataset video loader">
        <div className="library-brand">
          <div>
            <h1>OmniCourse Lens</h1>
            <p>Real Dataset video workspace</p>
          </div>
          <button className="icon-button" onClick={load} disabled={busy} title="Refresh dataset videos"><RefreshCcw size={17} /></button>
        </div>

        <div className="library-actions">
          <button onClick={runIngestSelected} disabled={busy || !selectedVideo}><UploadCloud size={16} /> Ingest</button>
          <button onClick={() => ingestAllDataset(9).then(() => setStatus("Ingest-all job started."))} disabled={busy}><UploadCloud size={16} /> All</button>
          <button onClick={() => rebuildIndex().then(() => setStatus("Index rebuilt."))} disabled={busy}><RefreshCcw size={16} /> Index</button>
        </div>

        <div className="video-list">
          {videos.map((video) => (
            <button
              key={video.video_id}
              className={`video-row ${selectedVideo?.video_id === video.video_id ? "selected" : ""}`}
              onClick={() => selectVideo(video)}
            >
              {video.thumbnail && <img src={mediaUrl(video.thumbnail)} alt="" />}
              <span>
                <strong>{video.title}</strong>
                <small>{video.ingestion_status} / {video.indexed_status} / {formatDuration(video.duration)}</small>
              </span>
            </button>
          ))}
        </div>

        <EvidenceRail
          results={results}
          moments={selectedVideoMoments}
          selected={selectedResult}
          selectedVideo={selectedVideo}
          courseId={courseId}
          onJump={jumpToEvidence}
        />
      </aside>

      <main className="watch-center" aria-label="Main video workspace">
        <section className="watch-player-card">
          <div className="watch-head">
            <div>
              <span className="eyebrow">Now watching</span>
              <h2>{selectedVideo?.title || "Select a Dataset video"}</h2>
            </div>
            <div className="provider-row compact-providers">
              <StatusBadge label="Dataset" ok={Boolean(health?.providers?.dataset?.exists)} />
              <StatusBadge label="GPT-4o" ok={Boolean(health?.providers?.llm?.available)} muted={Boolean(!health?.providers?.llm?.available)} />
              <StatusBadge label="OCR" ok={Boolean(health?.providers?.deepseek_ocr?.available)} muted={Boolean(!health?.providers?.deepseek_ocr?.available)} />
              <StatusBadge label="InternVideo3" ok={Boolean(health?.providers?.search?.internvideo3?.available)} muted />
            </div>
          </div>

          {activeVideoUrl ? (
            <video
              key={activeVideoUrl}
              ref={videoRef}
              className="main-video"
              src={activeVideoUrl}
              controls
              poster={mediaUrl(selectedPoster)}
              onLoadedMetadata={() => {
                if (selectedResult && videoRef.current) videoRef.current.currentTime = Math.max(0, selectedResult.start_time);
              }}
            />
          ) : (
            <div className="main-video preview-empty">Select a Dataset video</div>
          )}

          <div className="watch-meta">
            <span>{selectedTimestamp}</span>
            <span>{selectedVideo?.relative_path || "/home/haoqian/Data/OmniCourse-Lens/Dataset"}</span>
          </div>
        </section>

        <section className="watch-output">
          {feature === "search" && <SelectedEvidencePanel selected={selectedResult} moments={selectedVideoMoments} />}
          {feature === "cheatsheet" && <CheatsheetWorkspace cheatsheet={cheatsheet} onCompile={runCompile} />}
          {feature === "graph" && <GraphWorkspace graph={graph} selectedNode={selectedNode} setSelectedNode={setSelectedNode} />}
          {feature === "qa" && <QAWorkspace qa={qa} onJump={jumpToEvidence} />}
        </section>
      </main>

      <aside className="feature-sidebar control-sidebar" aria-label="Feature controls">
        <div className="feature-tabs" aria-label="Feature tabs">
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
          <select value={selectedVideo?.video_id || ""} onChange={(event) => selectVideo(videos.find((video) => video.video_id === event.target.value) || videos[0])}>
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

function EvidenceRail({
  results,
  moments,
  selected,
  selectedVideo,
  courseId,
  onJump
}: {
  results: SearchResult[];
  moments: any[];
  selected: SearchResult | null;
  selectedVideo: DatasetVideo | null;
  courseId: string;
  onJump: (item: SearchResult) => void;
}) {
  const items: SearchResult[] = (results.length ? results : moments.slice(0, 10).map((moment: any) => ({
    moment_id: moment.moment_id,
    video_id: moment.video_id || selectedVideo?.video_id,
    course_id: moment.course_id || courseId,
    lecture_id: moment.lecture_id || selectedVideo?.lecture_id || "",
    lecture_title: selectedVideo?.title || moment.lecture_id || "Lecture moment",
    start_time: Number(moment.start_time || 0),
    end_time: Number(moment.end_time || 0),
    score: 0.5,
    score_breakdown: {},
    matched_reason: "Indexed real Dataset moment",
    matched_modalities: ["ASR transcript", "OCR", "Keyframe"],
    transcript_snippet: moment.transcript || "",
    ocr_snippet: moment.ocr_text || "",
    formula_latex: moment.formula_latex || "",
    concept_tags: moment.concept_tags || [],
    thumbnail_url: moment.thumbnail_url,
    video_url: moment.video_id ? `/api/dataset/videos/${moment.video_id}/stream` : selectedVideo ? `/api/dataset/videos/${selectedVideo.video_id}/stream` : undefined
  }))).filter(Boolean);

  return (
    <section className="evidence-rail">
      <div className="rail-head">
        <h3>{results.length ? "Search Results" : "Lecture Moments"}</h3>
        <small>{items.length}</small>
      </div>
      <div className="rail-scroll">
        {items.map((item) => (
          <button
            key={item.moment_id}
            className={`rail-card ${selected?.moment_id === item.moment_id ? "selected" : ""}`}
            onClick={() => onJump(item)}
          >
            {item.thumbnail_url && <img src={mediaUrl(item.thumbnail_url)} alt="" />}
            <span>
              <strong>{item.start_time.toFixed(0)}-{item.end_time.toFixed(0)}s</strong>
              <small>{Math.round(item.score * 100)}% / {item.matched_modalities.slice(0, 2).join(", ")}</small>
              <em>{item.matched_reason}</em>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function SelectedEvidencePanel({ selected, moments }: { selected: SearchResult | null; moments: any[] }) {
  if (!selected) {
    return (
      <div className="selected-evidence empty-watch">
        <Play size={26} />
        <h3>Watch first, search beside it</h3>
        <p>The video stays in the center. Search results and lecture moments appear on the left; feature controls stay on the right.</p>
        <div className="moment-summary">
          {moments.slice(0, 3).map((moment: any) => (
            <span key={moment.moment_id}>{Number(moment.start_time || 0).toFixed(0)}-{Number(moment.end_time || 0).toFixed(0)}s</span>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="selected-evidence">
      <div className="selected-copy">
        <span className="eyebrow">Selected timestamp</span>
        <h3>{selected.lecture_title}</h3>
        <p className="timestamp">{selected.start_time.toFixed(0)}-{selected.end_time.toFixed(0)}s / {Math.round(selected.score * 100)}% match</p>
        <p>{selected.matched_reason}</p>
        <div className="chips">
          {selected.matched_modalities.map((modality) => <span key={modality}>{modality}</span>)}
        </div>
        {selected.transcript_snippet && <blockquote>{selected.transcript_snippet}</blockquote>}
        {selected.ocr_snippet && <blockquote>{selected.ocr_snippet}</blockquote>}
        {selected.formula_latex && <code>{selected.formula_latex}</code>}
      </div>
      <div className="selected-scores">
        <h4>Modality scores</h4>
        {Object.entries(selected.score_breakdown || {}).length ? Object.entries(selected.score_breakdown || {}).map(([key, value]) => (
          <div key={key}>
            <span>{key.replace(/_/g, " ")}</span>
            <meter min={0} max={1} value={value} />
          </div>
        )) : <p>No detailed score breakdown for this moment yet.</p>}
      </div>
    </div>
  );
}

function CheatsheetWorkspace({ cheatsheet, onCompile }: { cheatsheet: any; onCompile: () => void }) {
  if (!cheatsheet) return <EmptyState title="Generate a cheatsheet" text="Use the right sidebar to generate LaTeX from the selected real Dataset video." />;
  return (
    <div className="cheatsheet-workspace">
      <div className="cheatsheet-toolbar">
        {cheatsheet.tex_file_url && <a href={`${API_BASE}${cheatsheet.tex_file_url}`} target="_blank" rel="noreferrer"><Download size={16} /> Download .tex</a>}
        {cheatsheet.pdf_file_url && <a href={`${API_BASE}${cheatsheet.pdf_file_url}`} target="_blank" rel="noreferrer"><Download size={16} /> Download .pdf</a>}
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
        {Boolean(selectedNode?.metadata?.thumbnail_url) && <img src={mediaUrl(String(selectedNode?.metadata?.thumbnail_url))} alt={selectedNode?.label || "graph node"} />}
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

function mediaUrl(path?: string) {
  if (!path) return undefined;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE}${path}`;
}

function formatDuration(seconds?: number) {
  if (!seconds) return "unknown";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${mins}:${secs}`;
}
