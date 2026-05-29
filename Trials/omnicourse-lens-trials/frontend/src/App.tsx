import { Bell, Bot, BrainCircuit, Download, FileText, GripHorizontal, GripVertical, HelpCircle, Loader2, Network, Play, RefreshCcw, Search, Sparkles, UploadCloud, X } from "lucide-react";
import { useAutoAnimate } from "@formkit/auto-animate/react";
import { AnimatePresence, motion } from "framer-motion";
import Lenis from "lenis";
import { type CSSProperties, type PointerEvent as ReactPointerEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  textSearch,
  videoSubtitles
} from "./api";
import CytoscapeGraph, { GraphNode } from "./components/CytoscapeGraph";
import MarkdownMath from "./components/MarkdownMath";
import MathText, { renderModelMarkdown } from "./components/MathText";
import StatusBadge from "./components/StatusBadge";
import UploadPanel from "./components/UploadPanel";
import VideoEvidenceCard from "./components/VideoEvidenceCard";
import LearningToolsPanel from "./components/learning/LearningToolsPanel";

type Feature = "search" | "cheatsheet" | "graph" | "qa";

type SubtitleCue = {
  text: string;
  source: string;
  start_time: number;
  end_time: number;
  provider?: string;
  kind?: "audio" | "ocr" | "supplemental";
};

type WorkspaceSizes = {
  leftWidth: number;
  rightWidth: number;
  videoHeight: number;
  libraryListHeight: number;
  sidebarControlsHeight: number;
  outputSideWidth: number;
};

type ResizeTarget = keyof WorkspaceSizes;

const DEFAULT_WORKSPACE_SIZES: WorkspaceSizes = {
  leftWidth: 318,
  rightWidth: 374,
  videoHeight: 520,
  libraryListHeight: 320,
  sidebarControlsHeight: 520,
  outputSideWidth: 360
};

const featureItems = [
  { key: "search" as const, label: "Search Video", icon: Search },
  { key: "cheatsheet" as const, label: "Cheatsheet", icon: FileText },
  { key: "graph" as const, label: "Knowledge Graph", icon: Network },
  { key: "qa" as const, label: "AI Tutor", icon: Bot }
];

export default function App() {
  const [feature, setFeature] = useState<Feature>("qa");
  const [videos, setVideos] = useState<DatasetVideo[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<DatasetVideo | null>(null);
  const [course, setCourse] = useState<Course | null>(null);
  const [health, setHealth] = useState<any>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("gradient descent optimization");
  const [image, setImage] = useState<File | null>(null);
  const [searchScope, setSearchScope] = useState<"current" | "all">("current");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const [cheatsheet, setCheatsheet] = useState<any>(null);
  const [graph, setGraph] = useState<any>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [question, setQuestion] = useState("Why does gradient descent move opposite to the gradient?");
  const [qa, setQa] = useState<any>(null);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [subtitleCues, setSubtitleCues] = useState<SubtitleCue[]>([]);
  const [activeVideoEvidence, setActiveVideoEvidence] = useState<any>(null);
  const [workspaceSizes, setWorkspaceSizes] = useState<WorkspaceSizes>(() => loadWorkspaceSizes());
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [videoListRef] = useAutoAnimate<HTMLDivElement>({ duration: 240, easing: "ease-out" });

  useEffect(() => {
    window.localStorage.setItem("omnicourse.workspaceSizes", JSON.stringify(workspaceSizes));
  }, [workspaceSizes]);

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
    const lenis = new Lenis({
      autoRaf: true,
      duration: 0.9,
      smoothWheel: true
    });
    return () => lenis.destroy();
  }, []);

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
      setPlaybackTime(targetTime);
    }
  }, [selectedResult]);

  const selectVideo = (video: DatasetVideo) => {
    setSelectedVideo(video);
    setSelectedResult(null);
    setResults([]);
    setPlaybackTime(0);
  };

  const lectureId = selectedVideo?.lecture_id || course?.lectures?.[0]?.lecture_id || "";
  const courseId = selectedVideo?.course_id || course?.course_id || "real_i2ml";
  const videoIds = selectedVideo ? [selectedVideo.video_id] : undefined;
  const searchVideoIds = searchScope === "current" ? videoIds : undefined;

  const selectedVideoMoments = useMemo(() => {
    const lecture = course?.lectures?.find((item) => item.lecture_id === selectedVideo?.lecture_id);
    return lecture?.moments || [];
  }, [course, selectedVideo]);

  const activeVideoId = selectedResult?.video_id || selectedVideo?.video_id;

  useEffect(() => {
    if (!activeVideoId) {
      setSubtitleCues([]);
      setActiveVideoEvidence(null);
      return;
    }
    videoSubtitles(activeVideoId)
      .then((payload) => {
        setSubtitleCues(payload.cues || []);
        setActiveVideoEvidence(payload.summary || null);
      })
      .catch(() => {
        setSubtitleCues([]);
        setActiveVideoEvidence(null);
      });
  }, [activeVideoId]);

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
    setStatus(searchScope === "current" ? "Searching timestamped moments in the selected real video..." : "Searching across all indexed Dataset videos...");
    try {
      const payload = image
        ? await imageSearch({ course_id: courseId, query, video_ids: searchVideoIds, top_k: 6, image })
        : await textSearch({ course_id: courseId, query, video_ids: searchVideoIds, top_k: 6 });
      setResults(payload.results || []);
      setSelectedResult(payload.results?.[0] || null);
      if (payload.results?.[0]?.video_id) {
        const nextVideo = videos.find((video) => video.video_id === payload.results[0].video_id);
        if (nextVideo && nextVideo.video_id !== selectedVideo?.video_id) setSelectedVideo(nextVideo);
      }
      setFeature("search");
      const topScore = payload.results?.[0]?.score ?? 0;
      const weakHint = topScore < 0.12 && searchScope === "current" ? " Low match in this video; try All videos or a video-specific term." : "";
      setStatus(payload.scope_notice || `Search self-check: ${payload.self_check?.score ?? "n/a"}/10.${weakHint}`);
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
        current_timestamp: playbackTime,
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
    if (result.video_id) {
      const nextVideo = videos.find((video) => video.video_id === result.video_id);
      if (nextVideo && nextVideo.video_id !== selectedVideo?.video_id) setSelectedVideo(nextVideo);
    }
  };

  const activeStreamUrl = selectedResult?.video_url
    ? `${API_BASE}${selectedResult.video_url}`
    : activeVideoId
      ? `${API_BASE}/api/dataset/videos/${activeVideoId}/stream`
      : "";
  const activeVideoUrl = activeStreamUrl && selectedResult ? `${activeStreamUrl}#t=${Math.max(0, Math.floor(selectedResult.start_time))}` : activeStreamUrl;

  const selectedPoster = selectedResult?.thumbnail_url || selectedVideo?.thumbnail;
  const selectedTimestamp = selectedResult ? `${selectedResult.start_time.toFixed(0)}-${selectedResult.end_time.toFixed(0)}s` : "full lecture";
  const activeSubtitle = useMemo(
    () => findActiveSubtitleCue(subtitleCues, playbackTime) || findActiveSubtitle(selectedVideoMoments, playbackTime),
    [subtitleCues, selectedVideoMoments, playbackTime]
  );
  const workspaceStyle = useMemo(
    () =>
      ({
        "--left-panel-width": `${workspaceSizes.leftWidth}px`,
        "--right-panel-width": `${workspaceSizes.rightWidth}px`,
        "--video-height": `${workspaceSizes.videoHeight}px`,
        "--library-list-height": `${workspaceSizes.libraryListHeight}px`,
        "--sidebar-controls-height": `${workspaceSizes.sidebarControlsHeight}px`,
        "--output-side-width": `${workspaceSizes.outputSideWidth}px`
      }) as CSSProperties,
    [workspaceSizes]
  );
  const startResize = (target: ResizeTarget, event: ReactPointerEvent) => {
    event.preventDefault();
    const originX = event.clientX;
    const originY = event.clientY;
    const origin = workspaceSizes[target];
    document.body.classList.add("workspace-resizing");

    const onMove = (moveEvent: PointerEvent) => {
      const dx = moveEvent.clientX - originX;
      const dy = moveEvent.clientY - originY;
      setWorkspaceSizes((current) => {
        const next = { ...current };
        const centerMinimum = 560;
        const maxLeft = Math.max(240, window.innerWidth - current.rightWidth - centerMinimum);
        const maxRight = Math.max(300, window.innerWidth - current.leftWidth - centerMinimum);
        if (target === "leftWidth") next.leftWidth = clamp(origin + dx, 250, Math.min(560, maxLeft));
        if (target === "rightWidth") next.rightWidth = clamp(origin - dx, 300, Math.min(620, maxRight));
        if (target === "videoHeight") next.videoHeight = clamp(origin + dy, 260, Math.max(320, window.innerHeight - 260));
        if (target === "libraryListHeight") next.libraryListHeight = clamp(origin + dy, 140, Math.max(220, window.innerHeight - 350));
        if (target === "sidebarControlsHeight") next.sidebarControlsHeight = clamp(origin + dy, 180, Math.max(260, window.innerHeight - 260));
        if (target === "outputSideWidth") {
          const outputMax = Math.max(240, window.innerWidth - current.leftWidth - current.rightWidth - 420);
          next.outputSideWidth = clamp(origin - dx, 260, Math.min(620, outputMax));
        }
        return next;
      });
    };

    const onUp = () => {
      document.body.classList.remove("workspace-resizing");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
  };

  return (
    <motion.div className="atlas-shell watch-layout atlas-reference-ui" style={workspaceStyle} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.36, ease: "easeOut" }}>
      <header className="atlas-topbar">
        <div className="atlas-product-mark">
          <div className="atlas-cube" aria-hidden="true"><span /><span /><span /></div>
          <div>
            <h1>OmniCourse-Atlas</h1>
            <p>A Skill-Augmented Multimodal Agent for Course Learning</p>
          </div>
        </div>
        <div className="top-provider-panel">
          <span>Provider Status</span>
          <div className="provider-row compact-providers">
            <StatusBadge label="GPT-4o" ok={Boolean(health?.providers?.llm?.available)} muted={Boolean(!health?.providers?.llm?.available)} />
            <StatusBadge label="ASR" ok={Boolean(health?.providers?.ingest?.asr?.enabled || health?.providers?.ingest?.asr?.active_provider)} muted={Boolean(!health?.providers?.ingest?.asr?.enabled && !health?.providers?.ingest?.asr?.active_provider)} />
            <StatusBadge label="OCR" ok={Boolean(health?.providers?.ingest?.ocr)} />
            <StatusBadge label="DeepSeek OCR" ok={Boolean(health?.providers?.deepseek_ocr?.available)} muted={Boolean(!health?.providers?.deepseek_ocr?.available)} />
            <StatusBadge label="InternVideo3" ok={Boolean(health?.providers?.search?.internvideo3?.available)} muted={Boolean(!health?.providers?.search?.internvideo3?.available)} />
            <StatusBadge label="LaTeX" ok={Boolean(health?.providers?.latex?.tectonic_available || health?.providers?.latex?.pdflatex_available || health?.providers?.latex?.xelatex_available)} />
          </div>
        </div>
        <div className="topbar-actions">
          <button className="ghost-icon" title="Help"><HelpCircle size={19} /></button>
          <button className="ghost-icon" title="Notifications"><Bell size={19} /></button>
          <div className="user-avatar">AK<span /></div>
        </div>
      </header>

      <ResizeHandle placement="left-edge" label="Resize video library" onPointerDown={(event) => startResize("leftWidth", event)} />
      <ResizeHandle placement="right-edge" label="Resize feature sidebar" onPointerDown={(event) => startResize("rightWidth", event)} />

      <motion.aside className="video-library" aria-label="Dataset video loader" initial={{ x: -24, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: 0.42, ease: "easeOut" }}>
        <div className="library-brand">
          <div>
            <h1>Dataset Loader</h1>
            <p>Real course videos and indexed moments</p>
          </div>
          <button className="icon-button" onClick={load} disabled={busy} title="Refresh dataset videos"><RefreshCcw size={17} /></button>
        </div>

        <div className="library-actions">
          <button onClick={runIngestSelected} disabled={busy || !selectedVideo} title="Prepare the selected video for search, subtitles, QA, cheatsheets, and graph evidence.">
            <UploadCloud size={16} />
            <span>Make Current Video Searchable</span>
          </button>
          <button onClick={() => ingestAllDataset(9).then(() => setStatus("Preparing every Dataset video in the background."))} disabled={busy} title="Prepare every video in the Dataset folder.">
            <UploadCloud size={16} />
            <span>Make All Videos Searchable</span>
          </button>
          <button onClick={() => rebuildIndex().then(() => setStatus("Search library refreshed."))} disabled={busy} title="Refresh the search library after adding or changing videos.">
            <RefreshCcw size={16} />
            <span>Refresh Search Library</span>
          </button>
        </div>

        <div className="video-list" ref={videoListRef}>
          {videos.map((video) => (
            <motion.button
              key={video.video_id}
              layout
              className={`video-row ${selectedVideo?.video_id === video.video_id ? "selected" : ""}`}
              onClick={() => selectVideo(video)}
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.985 }}
            >
              {video.thumbnail && <img src={mediaUrl(video.thumbnail)} alt="" />}
              <span>
                <strong>{video.title}</strong>
                <small>{video.ingestion_status} / {video.indexed_status} / {formatDuration(video.duration)}</small>
              </span>
            </motion.button>
          ))}
        </div>

        <ResizeHandle placement="library-horizontal" label="Resize video list and evidence rail" onPointerDown={(event) => startResize("libraryListHeight", event)} />

        <EvidenceRail
          results={results}
          moments={selectedVideoMoments}
          selected={selectedResult}
          selectedVideo={selectedVideo}
          courseId={courseId}
          onJump={jumpToEvidence}
        />
      </motion.aside>

      <motion.main className="watch-center" aria-label="Main video workspace" initial={{ y: 18, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.44, ease: "easeOut", delay: 0.05 }}>
        <motion.section className="watch-player-card" layout>
          <div className="watch-head">
            <div>
              <span className="eyebrow">Now watching</span>
              <h2>{selectedVideo?.title || "Select a Dataset video"}</h2>
            </div>
            <div className="provider-row compact-providers">
              <StatusBadge label="Dataset" ok={Boolean(health?.providers?.dataset?.exists)} />
              <StatusBadge label="GPT-4o" ok={Boolean(health?.providers?.llm?.available)} muted={Boolean(!health?.providers?.llm?.available)} />
              <StatusBadge label="DeepSeek OCR" ok={Boolean(health?.providers?.deepseek_ocr?.available)} muted={Boolean(!health?.providers?.deepseek_ocr?.available)} />
              <StatusBadge label="InternVideo3" ok={Boolean(health?.providers?.search?.internvideo3?.available)} muted={Boolean(!health?.providers?.search?.internvideo3?.available)} />
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
              onTimeUpdate={(event) => setPlaybackTime(event.currentTarget.currentTime)}
              onSeeked={(event) => setPlaybackTime(event.currentTarget.currentTime)}
              onLoadedMetadata={() => {
                if (selectedResult && videoRef.current) {
                  const targetTime = Math.max(0, selectedResult.start_time);
                  videoRef.current.currentTime = targetTime;
                  setPlaybackTime(targetTime);
                }
              }}
            >
              {activeVideoId && <track kind="captions" src={`${API_BASE}/api/dataset/videos/${activeVideoId}/subtitles.vtt`} srcLang="en" label="Audio transcript" default />}
            </video>
          ) : (
            <div className="main-video preview-empty">Select a Dataset video</div>
          )}

          <SubtitleBar cue={activeSubtitle} currentTime={playbackTime} hasMoments={selectedVideoMoments.length > 0} />

          <div className="watch-meta">
            <span>{selectedTimestamp}</span>
            <span>{activeVideoEvidence ? `${activeVideoEvidence.asr_segment_count || 0} ASR cues · ${activeVideoEvidence.ocr_block_count || 0} OCR blocks · ${activeVideoEvidence.formula_block_count || 0} formulas` : "loading evidence"}</span>
            <span>{selectedVideo?.relative_path || "/home/haoqian/Data/OmniCourse-Lens/Dataset"}</span>
          </div>
        </motion.section>

        <ResizeHandle placement="center-horizontal" label="Resize video player and workspace output" onPointerDown={(event) => startResize("videoHeight", event)} />

        <section className="watch-output">
          <AnimatePresence mode="wait">
            <motion.div
              key={feature}
              className="feature-motion-surface"
              initial={{ opacity: 0, y: 12, filter: "blur(6px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, y: -8, filter: "blur(6px)" }}
              transition={{ duration: 0.22, ease: "easeOut" }}
            >
              {feature === "search" && <SelectedEvidencePanel selected={selectedResult} moments={selectedVideoMoments} />}
              {feature === "cheatsheet" && <CheatsheetWorkspace cheatsheet={cheatsheet} onCompile={runCompile} />}
              {feature === "graph" && <GraphWorkspace graph={graph} selectedNode={selectedNode} setSelectedNode={setSelectedNode} onJump={jumpToEvidence} onResizeSide={(event) => startResize("outputSideWidth", event)} />}
              {feature === "qa" && <QAWorkspace qa={qa} onJump={jumpToEvidence} onResizeSide={(event) => startResize("outputSideWidth", event)} />}
            </motion.div>
          </AnimatePresence>
        </section>
      </motion.main>

      <InsightColumn
        graph={graph}
        cheatsheet={cheatsheet}
        results={results}
        selectedVideo={selectedVideo}
        onGraph={runGraph}
        onCheatsheet={runCheatsheet}
        onCompile={runCompile}
        onJump={jumpToEvidence}
        setFeature={setFeature}
      />

      <motion.aside className="feature-sidebar control-sidebar" aria-label="Feature controls" initial={{ x: 24, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: 0.42, ease: "easeOut", delay: 0.08 }}>
        <div className="feature-tabs" aria-label="Feature tabs">
          {featureItems.map((item) => {
            const Icon = item.icon;
            return (
              <motion.button key={item.key} layout className={feature === item.key ? "active" : ""} onClick={() => setFeature(item.key)} whileHover={{ x: 2 }} whileTap={{ scale: 0.98 }}>
                {feature === item.key && <motion.span className="active-feature-mark" layoutId="activeFeatureMark" />}
                <Icon size={18} />
                <span>{item.label}</span>
              </motion.button>
            );
          })}
        </div>

        <div className="sidebar-panel-title">
          <div>
            <Sparkles size={18} />
            <strong>{featureItems.find((item) => item.key === feature)?.label}</strong>
          </div>
          <button type="button" className="panel-close" title="Keep panel open"><X size={17} /></button>
        </div>

        <div className="sidebar-controls">
          <label>Active real video</label>
          <select value={selectedVideo?.video_id || ""} onChange={(event) => selectVideo(videos.find((video) => video.video_id === event.target.value) || videos[0])}>
            {videos.map((video) => <option key={video.video_id} value={video.video_id}>{video.title}</option>)}
          </select>

          {feature === "search" && (
            <>
              <label>Search scope</label>
              <div className="scope-toggle" role="group" aria-label="Search scope">
                <button type="button" className={searchScope === "current" ? "active" : ""} onClick={() => setSearchScope("current")}>Current video</button>
                <button type="button" className={searchScope === "all" ? "active" : ""} onClick={() => setSearchScope("all")}>All videos</button>
              </div>
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
              <LearningToolsPanel
                courseId={courseId}
                selectedVideo={selectedVideo}
                selectedMomentId={selectedResult?.moment_id}
                question={question}
                query={query}
                playbackTime={playbackTime}
                onJump={jumpToEvidence}
              />
            </>
          )}
        </div>

        <ResizeHandle placement="sidebar-horizontal" label="Resize feature controls and status area" onPointerDown={(event) => startResize("sidebarControlsHeight", event)} />

        {status && <div className="status-note">{status}</div>}
      </motion.aside>
    </motion.div>
  );
}

function InsightColumn({
  graph,
  cheatsheet,
  results,
  selectedVideo,
  onGraph,
  onCheatsheet,
  onCompile,
  onJump,
  setFeature
}: {
  graph: any;
  cheatsheet: any;
  results: SearchResult[];
  selectedVideo: DatasetVideo | null;
  onGraph: () => void;
  onCheatsheet: () => void;
  onCompile: () => void;
  onJump: (item: SearchResult | EvidenceItem | any) => void;
  setFeature: (feature: Feature) => void;
}) {
  const concepts = useMemo((): string[] => {
    const fromGraph = (graph?.nodes || [])
      .filter((node: any) => node.type === "concept")
      .map((node: any) => String(node.label))
      .slice(0, 6);
    if (fromGraph.length >= 4) return fromGraph;
    const tags = results.flatMap((item) => item.concept_tags || []);
    return Array.from(new Set([...fromGraph, ...tags, "Cost Function", "Learning Rate", "Local Minima", "Convergence"])).slice(0, 6);
  }, [graph, results]);
  const reviewClips = results.slice(0, 3);
  const formula = results.find((item) => item.formula_latex)?.formula_latex || cheatsheet?.source_moments?.find?.((item: any) => item.formula_latex)?.formula_latex || "\\theta := \\theta - \\alpha \\nabla J(\\theta)";

  return (
    <motion.aside className="insight-column" aria-label="Course intelligence previews" initial={{ y: 18, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.42, ease: "easeOut", delay: 0.08 }}>
      <section className="preview-card graph-preview-card">
        <div className="preview-card-head">
          <strong>Knowledge Graph Preview</strong>
          <button type="button" onClick={() => { setFeature("graph"); onGraph(); }}>Open Full Graph</button>
        </div>
        <div className="mini-graph">
          <div className="mini-node center">Gradient<br />Descent</div>
          {concepts.map((concept, idx) => (
            <span key={concept} className={`mini-node n${idx + 1}`}>{compactInsightLabel(concept)}</span>
          ))}
        </div>
      </section>

      <section className="preview-card cheatsheet-preview-card">
        <div className="preview-card-head">
          <strong>Cheatsheet Preview</strong>
          <button type="button" onClick={() => { setFeature("cheatsheet"); cheatsheet ? onCompile() : onCheatsheet(); }}>Compile LaTeX</button>
        </div>
        <MathText text={formula} block className="mini-formula" />
        <div className="formula-stack">
          <MathText text={"J(\\theta)=\\frac{1}{m}\\sum_i (h_\\theta(x^{(i)})-y^{(i)})^2"} block />
        </div>
      </section>

      <section className="preview-card review-preview-card">
        <div className="preview-card-head">
          <strong>Suggested Review Clips</strong>
          <button type="button" onClick={() => setFeature("search")}>View all</button>
        </div>
        <div className="review-strip">
          {reviewClips.length ? reviewClips.map((item) => (
            <button key={item.moment_id} type="button" onClick={() => onJump(item)}>
              {item.thumbnail_url && <img src={mediaUrl(item.thumbnail_url)} alt="" />}
              <span>{item.start_time.toFixed(0)}s</span>
            </button>
          )) : (
            <p>{selectedVideo ? "Run Search Video to populate review clips." : "Select a Dataset video first."}</p>
          )}
        </div>
      </section>

      <section className="preview-card rewind-preview-card">
        <div className="preview-card-head">
          <strong>Prerequisite Rewind</strong>
        </div>
        <p>Brush up on topics that strengthen the selected concept before asking the tutor.</p>
        <button type="button" onClick={() => setFeature("qa")}>Review Prerequisites</button>
      </section>
    </motion.aside>
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
  const [railRef] = useAutoAnimate<HTMLDivElement>({ duration: 220, easing: "ease-out" });
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
      <div className="rail-scroll" ref={railRef}>
        {items.map((item) => (
          <motion.button
            key={item.moment_id}
            layout
            className={`rail-card ${selected?.moment_id === item.moment_id ? "selected" : ""}`}
            onClick={() => onJump(item)}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.985 }}
          >
            {item.thumbnail_url && <img src={mediaUrl(item.thumbnail_url)} alt="" />}
            <span>
              <strong>{item.start_time.toFixed(0)}-{item.end_time.toFixed(0)}s</strong>
              <small>{Math.round(item.score * 100)}% / {item.matched_modalities.slice(0, 2).join(", ")}</small>
              <em>{item.matched_reason}</em>
            </span>
          </motion.button>
        ))}
      </div>
    </section>
  );
}

function SelectedEvidencePanel({ selected, moments }: { selected: SearchResult | null; moments: any[] }) {
  if (!selected) {
    return (
      <motion.div className="selected-evidence empty-watch" initial={{ opacity: 0, scale: 0.985 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.24 }}>
        <Play size={26} />
        <h3>Watch first, search beside it</h3>
        <p>The video stays in the center. Search results and lecture moments appear on the left; feature controls stay on the right.</p>
        <div className="moment-summary">
          {moments.slice(0, 3).map((moment: any) => (
            <span key={moment.moment_id}>{Number(moment.start_time || 0).toFixed(0)}-{Number(moment.end_time || 0).toFixed(0)}s</span>
          ))}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div className="selected-evidence" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.24 }}>
      <div className="selected-copy">
        <span className="eyebrow">Selected timestamp</span>
        <h3>{selected.lecture_title}</h3>
        <p className="timestamp">{selected.start_time.toFixed(0)}-{selected.end_time.toFixed(0)}s / {Math.round(selected.score * 100)}% match</p>
        <MathText text={selected.matched_reason} className="selected-reason" />
        <div className="chips">
          {selected.matched_modalities.map((modality) => <span key={modality}>{modality}</span>)}
        </div>
        {selected.transcript_snippet && <blockquote><MathText text={selected.transcript_snippet} /></blockquote>}
        {selected.ocr_snippet && <blockquote><MathText text={selected.ocr_snippet} /></blockquote>}
        {selected.formula_latex && <MathText text={selected.formula_latex} block className="selected-formula" />}
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
    </motion.div>
  );
}

function CheatsheetWorkspace({ cheatsheet, onCompile }: { cheatsheet: any; onCompile: () => void }) {
  if (!cheatsheet) return <EmptyState title="Generate a cheatsheet" text="Use the right sidebar to generate LaTeX from the selected real Dataset video." />;
  return (
    <motion.div className="cheatsheet-workspace" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
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
    </motion.div>
  );
}

function GraphWorkspace({
  graph,
  selectedNode,
  setSelectedNode,
  onJump,
  onResizeSide
}: {
  graph: any;
  selectedNode: GraphNode | null;
  setSelectedNode: (node: GraphNode) => void;
  onJump: (item: any) => void;
  onResizeSide: (event: ReactPointerEvent) => void;
}) {
  if (!graph) return <EmptyState title="Generate a knowledge graph" text="Cytoscape fCoSE will build a searchable, pannable concept graph from the selected real Dataset video evidence." />;
  const metadata = selectedNode?.metadata || {};
  const canJump = Boolean(metadata.moment_id || selectedNode?.timestamp !== undefined);
  const jump = () => {
    if (!selectedNode || !canJump) return;
    onJump({
      moment_id: String(metadata.moment_id || selectedNode.id),
      video_id: String(metadata.video_id || ""),
      lecture_id: selectedNode.lecture_id || "",
      lecture_title: selectedNode.label,
      start_time: Number(metadata.start_time ?? selectedNode.timestamp ?? 0),
      end_time: Number(metadata.end_time ?? selectedNode.timestamp ?? 0) + 30,
      thumbnail_url: String(metadata.thumbnail_url || ""),
      matched_reason: `Knowledge graph node: ${selectedNode.label}`,
      matched_modalities: [selectedNode.type.replace("_", " ")],
      transcript_snippet: String(metadata.transcript_snippet || ""),
      ocr_snippet: String(metadata.ocr_snippet || ""),
      formula_latex: String(metadata.latex || ""),
      score: Number(metadata.relevance || 0.7)
    });
  };
  return (
    <motion.div className="graph-workspace" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <CytoscapeGraph nodes={graph.nodes || []} edges={graph.edges || []} onSelect={setSelectedNode} />
      <ResizeHandle placement="output-vertical" label="Resize graph inspector" onPointerDown={onResizeSide} />
      <aside className="graph-inspector">
        <span className={`node-type-pill ${selectedNode?.type || "summary"}`}>{selectedNode ? selectedNode.type.replace("_", " ") : "Summary"}</span>
        <h3>{selectedNode?.label || "Graph Summary"}</h3>
        <p>{selectedNode ? nodeDescription(selectedNode) : graph.summary}</p>
        {selectedNode?.timestamp !== undefined && <p className="timestamp">Timestamp {selectedNode.timestamp.toFixed(0)}s</p>}
        {Boolean(selectedNode?.metadata?.thumbnail_url) && <img src={mediaUrl(String(selectedNode?.metadata?.thumbnail_url))} alt={selectedNode?.label || "graph node"} />}
        {Boolean(metadata.transcript_snippet) && <blockquote><MathText text={String(metadata.transcript_snippet)} /></blockquote>}
        {Boolean(metadata.ocr_snippet) && <blockquote><MathText text={String(metadata.ocr_snippet)} /></blockquote>}
        {Boolean(metadata.latex) && <MathText text={String(metadata.latex)} block className="graph-formula" />}
        {canJump && <button className="jump-button" type="button" onClick={jump}><Play size={15} /> Jump to timestamp</button>}
        <div className="graph-metrics">
          <strong>{graph.metrics?.concept_count ?? 0}</strong> concepts
          <strong>{graph.metrics?.formula_count ?? 0}</strong> formulas
          <strong>{graph.metrics?.moment_count ?? 0}</strong> moments
          <span>{(graph.nodes || []).length} nodes / {(graph.edges || []).length} edges</span>
        </div>
      </aside>
    </motion.div>
  );
}

function QAWorkspace({ qa, onJump, onResizeSide }: { qa: any; onJump: (item: EvidenceItem) => void; onResizeSide: (event: ReactPointerEvent) => void }) {
  if (!qa) return <EmptyState title="Ask the AI Tutor" text="The answer will render Markdown and LaTeX with evidence cards and timestamp jumps." />;
  return (
    <motion.div className="qa-workspace" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <div className="answer-card">
        <div className="answer-head"><Bot size={18} /><strong>{qa.generation_mode}</strong><span>{Math.round((qa.confidence || 0) * 100)}%</span></div>
        <MarkdownMath text={renderModelMarkdown(qa.answer)} />
      </div>
      <ResizeHandle placement="output-vertical" label="Resize AI Tutor evidence column" onPointerDown={onResizeSide} />
      <div className="result-column">
        {(qa.evidence || []).map((item: EvidenceItem) => <VideoEvidenceCard key={item.moment_id} item={item} onSelect={() => onJump(item)} />)}
      </div>
    </motion.div>
  );
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return <motion.div className="empty-state" initial={{ opacity: 0, scale: 0.985 }} animate={{ opacity: 1, scale: 1 }}><Play size={26} /><h3>{title}</h3><p>{text}</p></motion.div>;
}

function ResizeHandle({
  placement,
  label,
  onPointerDown
}: {
  placement: "left-edge" | "right-edge" | "center-horizontal" | "library-horizontal" | "sidebar-horizontal" | "output-vertical";
  label: string;
  onPointerDown: (event: ReactPointerEvent) => void;
}) {
  const vertical = placement === "left-edge" || placement === "right-edge" || placement === "output-vertical";
  return (
    <button
      type="button"
      className={`resize-handle ${placement}`}
      aria-label={label}
      title={label}
      onPointerDown={onPointerDown}
    >
      {vertical ? <GripVertical size={18} /> : <GripHorizontal size={18} />}
      <span />
    </button>
  );
}

function nodeDescription(node: GraphNode) {
  const frequency = Number(node.metadata?.frequency || 0);
  if (node.type === "concept") return frequency ? `Concept appears in ${frequency} evidence windows.` : "Concept extracted from lecture transcript, slide text, formulas, and visual evidence.";
  if (node.type === "formula") return "Formula node grounded in OCR/formula evidence from the selected lecture moment.";
  if (node.type === "moment") return "Timestamped lecture moment connected to concepts, formulas, and keyframes.";
  if (node.type === "visual_evidence") return "Keyframe evidence sampled from the lecture video.";
  if (node.type === "lecture") return "Lecture/video node containing timestamped evidence moments.";
  return "Course-level graph root.";
}

function compactInsightLabel(label: string) {
  return label
    .replace(/gradient descent/i, "Gradient Descent")
    .replace(/mean squared error/i, "MSE")
    .replace(/empirical risk minimization/i, "ERM")
    .split(/\s+/)
    .slice(0, 2)
    .join("\n");
}

function SubtitleBar({ cue, currentTime, hasMoments }: { cue: SubtitleCue | null; currentTime: number; hasMoments: boolean }) {
  return (
    <div className={`subtitle-strip ${cue ? "active" : ""}`} aria-live="polite">
      <div className="subtitle-meta">
        <span>{formatDuration(currentTime)}</span>
        <span>{cue?.source || (hasMoments ? "Waiting for subtitle evidence" : "No subtitles indexed")}</span>
      </div>
      <AnimatePresence mode="wait">
        <motion.p
          key={cue ? `${cue.start_time}-${cue.end_time}-${cue.text}` : "empty-subtitle"}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.18 }}
        >
          {cue?.text || (hasMoments ? "Subtitles will update here while the video plays." : "Ingest this video to generate timestamped subtitle evidence.")}
        </motion.p>
      </AnimatePresence>
    </div>
  );
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
  if (seconds === undefined || seconds === null || Number.isNaN(seconds)) return "unknown";
  const safeSeconds = Math.max(0, seconds);
  const mins = Math.floor(safeSeconds / 60);
  const secs = Math.floor(safeSeconds % 60).toString().padStart(2, "0");
  return `${mins}:${secs}`;
}

function findActiveSubtitleCue(cues: SubtitleCue[], currentTime: number): SubtitleCue | null {
  if (!cues.length) return null;
  const matches = cues
    .filter((cue) => {
      const start = Number(cue.start_time || 0);
      const end = Number(cue.end_time || start);
      return cue.text && currentTime >= start && currentTime <= end + 0.35;
    })
    .sort((left, right) => cueKindPriority(right) - cueKindPriority(left));
  if (!matches.length) return null;
  const cue = matches[0];
  return {
    ...cue,
    text: cleanSubtitleText(cue.text, cue.kind === "audio" ? 280 : 220),
    source: cue.source || subtitleSourceLabel((cue as any).provider)
  };
}

function cueKindPriority(cue: SubtitleCue) {
  const provider = String((cue as any).provider || "").toLowerCase();
  if (cue.kind === "audio" || provider.includes("whisper")) return 4;
  if (provider === "deepseek_ocr") return 3;
  if (cue.kind === "ocr") return 2;
  return 1;
}

function findActiveSubtitle(moments: any[], currentTime: number): SubtitleCue | null {
  if (!moments.length) return null;
  const segments = moments
    .flatMap((moment: any) => (moment.asr_segments || []).map((segment: any) => ({ ...segment, moment })))
    .filter((segment: any) => {
      const start = Number(segment.start_time ?? 0);
      const end = Number(segment.end_time ?? start);
      return segment.text && currentTime >= start && currentTime <= end + 0.35;
    })
    .sort((left: any, right: any) => subtitlePriority(right.provider) - subtitlePriority(left.provider));

  if (segments.length) {
    const segment = segments[0];
    return {
      text: cleanSubtitleText(segment.text),
      source: subtitleSourceLabel(segment.provider),
      start_time: Number(segment.start_time || 0),
      end_time: Number(segment.end_time || segment.start_time || 0)
    };
  }

  const moment = moments.find((item: any) => currentTime >= Number(item.start_time || 0) && currentTime <= Number(item.end_time || 0));
  if (!moment) return null;
  const text = moment.transcript || moment.ocr_text || moment.visual_caption || "";
  if (!text.trim()) return null;
  return {
    text: cleanSubtitleText(text),
    source: moment.ocr_text ? "Slide/PDF text" : "Moment subtitle",
    start_time: Number(moment.start_time || 0),
    end_time: Number(moment.end_time || 0)
  };
}

function subtitlePriority(provider?: string) {
  const value = String(provider || "").toLowerCase();
  if (value.includes("whisper") || value === "transcript_file") return 4;
  if (value === "slide_pdf_text") return 3;
  if (value.includes("ocr")) return 2;
  if (value === "fallback_asr") return 1;
  return 0;
}

function subtitleSourceLabel(provider?: string) {
  const value = String(provider || "").toLowerCase();
  if (value.includes("whisper") || value === "transcript_file") return "Audio transcript";
  if (value === "slide_pdf_text") return "Slide/PDF subtitle";
  if (value === "fallback_asr") return "Auto fallback subtitle";
  return "Indexed subtitle";
}

function cleanSubtitleText(text: string, maxChars = 260) {
  const cleaned = text
    .replace(/\s+/g, " ")
    .replace(/©/g, "")
    .trim();
  if (cleaned.length <= maxChars) return cleaned;
  return `${cleaned.slice(0, maxChars).replace(/\s+\S*$/, "")}...`;
}

function loadWorkspaceSizes(): WorkspaceSizes {
  try {
    const raw = window.localStorage.getItem("omnicourse.workspaceSizes");
    if (!raw) return DEFAULT_WORKSPACE_SIZES;
    const parsed = JSON.parse(raw) as Partial<WorkspaceSizes>;
    return {
      leftWidth: clamp(Number(parsed.leftWidth || DEFAULT_WORKSPACE_SIZES.leftWidth), 250, 560),
      rightWidth: clamp(Number(parsed.rightWidth || DEFAULT_WORKSPACE_SIZES.rightWidth), 300, 620),
      videoHeight: clamp(Number(parsed.videoHeight || DEFAULT_WORKSPACE_SIZES.videoHeight), 260, 900),
      libraryListHeight: clamp(Number(parsed.libraryListHeight || DEFAULT_WORKSPACE_SIZES.libraryListHeight), 140, 720),
      sidebarControlsHeight: clamp(Number(parsed.sidebarControlsHeight || DEFAULT_WORKSPACE_SIZES.sidebarControlsHeight), 180, 720),
      outputSideWidth: clamp(Number(parsed.outputSideWidth || DEFAULT_WORKSPACE_SIZES.outputSideWidth), 260, 620)
    };
  } catch {
    return DEFAULT_WORKSPACE_SIZES;
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}
