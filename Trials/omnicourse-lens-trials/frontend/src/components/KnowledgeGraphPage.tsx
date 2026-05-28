import { Loader2, Network } from "lucide-react";
import { useMemo, useState } from "react";
import { apiPost, API_BASE, Course } from "../api";
import StatusBadge from "./StatusBadge";

type GraphNode = { id: string; label: string; type: string; lecture_id?: string; timestamp?: number; metadata?: any };
type GraphEdge = { source: string; target: string; type: string; weight: number };

export default function KnowledgeGraphPage({ course }: { course: Course | null }) {
  const [lectureIds, setLectureIds] = useState<string[]>(["lec_01", "lec_02", "lec_03"]);
  const [focus, setFocus] = useState("");
  const [graph, setGraph] = useState<{ nodes: GraphNode[]; edges: GraphEdge[]; summary: string; self_check?: any } | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const layout = useMemo(() => {
    if (!graph) return [];
    const width = 760;
    const height = 520;
    const centerX = width / 2;
    const centerY = height / 2;
    return graph.nodes.slice(0, 70).map((node, index, nodes) => {
      const ring = node.type === "course" ? 0 : node.type === "lecture" ? 120 : node.type === "concept" ? 205 : 255;
      const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
      return { ...node, x: centerX + Math.cos(angle) * ring, y: centerY + Math.sin(angle) * ring };
    });
  }, [graph]);

  const run = async () => {
    if (!course) return;
    setLoading(true);
    setError("");
    try {
      setGraph(
        await apiPost("/api/knowledge-graph", {
          course_id: course.course_id,
          lecture_ids: lectureIds.length ? lectureIds : course.lectures.map((lecture) => lecture.lecture_id),
          focus_topic: focus || undefined
        })
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const toggle = (id: string) => {
    setLectureIds((items) => (items.includes(id) ? items.filter((item) => item !== id) : [...items, id]));
  };

  const nodeById = Object.fromEntries(layout.map((node) => [node.id, node]));
  const color = (type: string) => ({ course: "#1f7a5f", lecture: "#315f9e", moment: "#7a4f14", concept: "#7f3566", formula: "#4d5a19", visual_evidence: "#555" }[type] || "#334155");

  return (
    <section className="page-grid graph-grid">
      <div className="tool-panel">
        <div className="section-title">
          <h2>Knowledge Graph</h2>
          {graph?.self_check && <StatusBadge label={`Self-check ${graph.self_check.score}/10`} ok={graph.self_check.passed} />}
        </div>
        <div className="search-row">
          <input value={focus} onChange={(event) => setFocus(event.target.value)} placeholder="optional focus" />
          <button onClick={run} disabled={loading}>
            {loading ? <Loader2 size={18} className="spin" /> : <Network size={18} />}
            Generate
          </button>
        </div>
        <div className="lecture-filter">
          {course?.lectures.map((lecture) => (
            <label key={lecture.lecture_id}>
              <input type="checkbox" checked={lectureIds.includes(lecture.lecture_id)} onChange={() => toggle(lecture.lecture_id)} />
              {lecture.title}
            </label>
          ))}
        </div>
        {error && <div className="error-band">{error}</div>}
        <svg className="graph-canvas" viewBox="0 0 760 520">
          {graph?.edges.slice(0, 220).map((edge, index) => {
            const source = nodeById[edge.source];
            const target = nodeById[edge.target];
            if (!source || !target) return null;
            return <line key={`${edge.source}-${edge.target}-${index}`} x1={source.x} y1={source.y} x2={target.x} y2={target.y} stroke="#cbd5df" strokeWidth={edge.type === "prerequisite_of" ? 2 : 1} />;
          })}
          {layout.map((node) => (
            <g key={node.id} onClick={() => setSelected(node)} className="graph-node">
              <circle cx={node.x} cy={node.y} r={node.type === "concept" ? 8 : 10} fill={color(node.type)} />
              <text x={node.x + 12} y={node.y + 4}>
                {node.label.slice(0, 30)}
              </text>
            </g>
          ))}
        </svg>
        <div className="legend">
          {["course", "lecture", "moment", "concept", "formula", "visual_evidence"].map((type) => (
            <span key={type}>
              <i style={{ background: color(type) }} />
              {type.replace("_", " ")}
            </span>
          ))}
        </div>
      </div>
      <aside className="inspector">
        <h3>{selected?.label || "Graph Summary"}</h3>
        <p>{selected ? selected.type.replace("_", " ") : graph?.summary}</p>
        {selected?.timestamp !== undefined && <p>{selected.timestamp.toFixed(0)}s</p>}
        {selected?.metadata?.thumbnail_url && <img src={`${API_BASE}${selected.metadata.thumbnail_url}`} alt={selected.label} />}
      </aside>
    </section>
  );
}
