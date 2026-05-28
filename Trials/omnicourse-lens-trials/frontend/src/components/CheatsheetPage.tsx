import { Download, FileText, Loader2 } from "lucide-react";
import { useState } from "react";
import { apiPost, API_BASE, Course, EvidenceItem } from "../api";
import StatusBadge from "./StatusBadge";
import VideoEvidenceCard from "./VideoEvidenceCard";

export default function CheatsheetPage({ course }: { course: Course | null }) {
  const [lectureIds, setLectureIds] = useState<string[]>(["lec_01", "lec_02"]);
  const [focus, setFocus] = useState("gradient descent, normal equation");
  const [maxPages, setMaxPages] = useState(2);
  const [response, setResponse] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    if (!course) return;
    setLoading(true);
    setError("");
    try {
      setResponse(
        await apiPost("/api/cheatsheet", {
          course_id: course.course_id,
          lecture_ids: lectureIds.length ? lectureIds : course.lectures.map((lecture) => lecture.lecture_id),
          focus_topics: focus,
          style: "exam",
          max_pages: maxPages
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

  return (
    <section className="page-grid two-col">
      <div className="tool-panel">
        <div className="section-title">
          <h2>Cheatsheet</h2>
          {response?.self_check && <StatusBadge label={`Self-check ${response.self_check.score}/10`} ok={response.self_check.passed} />}
        </div>
        <div className="form-stack">
          <div className="lecture-filter">
            {course?.lectures.map((lecture) => (
              <label key={lecture.lecture_id}>
                <input type="checkbox" checked={lectureIds.includes(lecture.lecture_id)} onChange={() => toggle(lecture.lecture_id)} />
                {lecture.title}
              </label>
            ))}
          </div>
          <input value={focus} onChange={(event) => setFocus(event.target.value)} />
          <select value={maxPages} onChange={(event) => setMaxPages(Number(event.target.value))}>
            {[1, 2, 3, 4].map((value) => (
              <option key={value} value={value}>
                {value} pages
              </option>
            ))}
          </select>
          <button onClick={run} disabled={loading}>
            {loading ? <Loader2 size={18} className="spin" /> : <FileText size={18} />}
            Generate
          </button>
        </div>
        {error && <div className="error-band">{error}</div>}
        {response && (
          <div className="download-row">
            <a href={`${API_BASE}${response.tex_file_url}`} target="_blank">
              <Download size={16} /> TEX
            </a>
            {response.pdf_file_url && (
              <a href={`${API_BASE}${response.pdf_file_url}`} target="_blank">
                <Download size={16} /> PDF
              </a>
            )}
          </div>
        )}
        <pre className="latex-preview">{response?.tex_content || ""}</pre>
      </div>
      <aside className="side-list">
        {(response?.source_moments || []).map((item: EvidenceItem) => (
          <VideoEvidenceCard key={item.moment_id} item={item} />
        ))}
      </aside>
    </section>
  );
}
