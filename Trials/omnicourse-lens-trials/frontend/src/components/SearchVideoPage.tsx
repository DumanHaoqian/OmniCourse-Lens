import { Loader2, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Course, imageSearch, SearchResult, textSearch } from "../api";
import UploadPanel from "./UploadPanel";
import VideoEvidenceCard from "./VideoEvidenceCard";
import VideoPlayer from "./VideoPlayer";
import StatusBadge from "./StatusBadge";

export default function SearchVideoPage({ course }: { course: Course | null }) {
  const [query, setQuery] = useState("gradient descent");
  const [image, setImage] = useState<File | null>(null);
  const [lectureIds, setLectureIds] = useState<string[]>([]);
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [selfCheck, setSelfCheck] = useState<any>(null);
  const [error, setError] = useState("");
  const selectedIds = useMemo(() => (lectureIds.length ? lectureIds : undefined), [lectureIds]);

  const run = async () => {
    if (!course) return;
    setLoading(true);
    setError("");
    try {
      const payload = image
        ? await imageSearch({ course_id: course.course_id, query, lecture_ids: selectedIds, top_k: topK, image })
        : await textSearch({ course_id: course.course_id, query, lecture_ids: selectedIds, top_k: topK });
      setResults(payload.results);
      setSelected(payload.results[0] || null);
      setSelfCheck(payload.self_check);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const toggleLecture = (lectureId: string) => {
    setLectureIds((items) => (items.includes(lectureId) ? items.filter((item) => item !== lectureId) : [...items, lectureId]));
  };

  return (
    <section className="page-grid search-grid">
      <div className="tool-panel">
        <div className="section-title">
          <h2>Search Video</h2>
          {selfCheck && <StatusBadge label={`Self-check ${selfCheck.score}/10`} ok={selfCheck.passed} />}
        </div>
        <div className="search-row">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="gradient descent" />
          <UploadPanel file={image} onFile={setImage} />
          <select value={topK} onChange={(event) => setTopK(Number(event.target.value))}>
            {[3, 5, 8, 10].map((value) => (
              <option key={value} value={value}>
                Top {value}
              </option>
            ))}
          </select>
          <button onClick={run} disabled={loading}>
            {loading ? <Loader2 size={18} className="spin" /> : <Search size={18} />}
            Search
          </button>
        </div>
        <div className="lecture-filter">
          {course?.lectures.map((lecture) => (
            <label key={lecture.lecture_id}>
              <input type="checkbox" checked={lectureIds.includes(lecture.lecture_id)} onChange={() => toggleLecture(lecture.lecture_id)} />
              {lecture.title}
            </label>
          ))}
        </div>
        {error && <div className="error-band">{error}</div>}
        <div className="results-list">
          {results.map((result) => (
            <VideoEvidenceCard key={result.moment_id} item={result} onSelect={() => setSelected(result)} />
          ))}
        </div>
      </div>
      <aside className="preview-panel">
        <VideoPlayer result={selected} />
        {selected && (
          <div className="score-grid">
            {Object.entries(selected.score_breakdown).map(([key, value]) => (
              <div key={key}>
                <span>{key.replace(/_/g, " ")}</span>
                <meter min={0} max={1} value={value} />
              </div>
            ))}
          </div>
        )}
      </aside>
    </section>
  );
}
