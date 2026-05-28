import { Bot, Loader2, Send } from "lucide-react";
import { useState } from "react";
import { askTutor, Course, EvidenceItem } from "../api";
import MarkdownMath from "./MarkdownMath";
import { renderModelMarkdown } from "./MathText";
import StatusBadge from "./StatusBadge";
import UploadPanel from "./UploadPanel";
import VideoEvidenceCard from "./VideoEvidenceCard";

export default function AgentQAPage({ course }: { course: Course | null }) {
  const [question, setQuestion] = useState("Why does gradient descent move opposite to the gradient?");
  const [lectureId, setLectureId] = useState("");
  const [timestamp, setTimestamp] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [response, setResponse] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    if (!course) return;
    setLoading(true);
    setError("");
    try {
      setResponse(
        await askTutor({
          course_id: course.course_id,
          question,
          lecture_id: lectureId || undefined,
          current_timestamp: timestamp ? Number(timestamp) : undefined,
          top_k: 5,
          image
        })
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="page-grid two-col">
      <div className="tool-panel">
        <div className="section-title">
          <h2>AI Tutor</h2>
          {response?.self_check && <StatusBadge label={`Self-check ${response.self_check.score}/10`} ok={response.self_check.passed} />}
        </div>
        <div className="chat-input">
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
          <div className="search-row">
            <select value={lectureId} onChange={(event) => setLectureId(event.target.value)}>
              <option value="">All lectures</option>
              {course?.lectures.map((lecture) => (
                <option key={lecture.lecture_id} value={lecture.lecture_id}>
                  {lecture.title}
                </option>
              ))}
            </select>
            <input value={timestamp} onChange={(event) => setTimestamp(event.target.value)} placeholder="timestamp" />
            <UploadPanel file={image} onFile={setImage} />
            <button onClick={run} disabled={loading}>
              {loading ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
              Ask
            </button>
          </div>
        </div>
        {error && <div className="error-band">{error}</div>}
        {response ? (
          <div className="answer-panel">
            <div className="answer-head">
              <Bot size={18} />
              <strong>{response.generation_mode}</strong>
              <span>{Math.round(response.confidence * 100)}%</span>
            </div>
            <MarkdownMath text={renderModelMarkdown(response.answer)} />
            <div className="followups">
              {(response.follow_up_questions || []).map((item: string) => (
                <button key={item} onClick={() => setQuestion(item)}>
                  {item}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
      <aside className="side-list">
        {(response?.evidence || []).map((item: EvidenceItem) => (
          <VideoEvidenceCard key={item.moment_id} item={item} />
        ))}
      </aside>
    </section>
  );
}
