import { Brain, ClipboardCheck, Compass, GraduationCap, ImagePlus, Route, Sigma } from "lucide-react";
import { useState } from "react";
import {
  DatasetVideo,
  EvidenceItem,
  formulaDerivation,
  masteryUpdate,
  misconceptionCheck,
  prerequisiteRewind,
  regionExplain,
  SearchResult,
  socraticDrill,
  studyPlan
} from "../../api";
import MarkdownMath from "../MarkdownMath";
import MathText from "../MathText";
import UploadPanel from "../UploadPanel";
import VideoEvidenceCard from "../VideoEvidenceCard";

type LearningTool = "rewind" | "misconception" | "drill" | "formula" | "region" | "plan";

const tools: { key: LearningTool; label: string; icon: typeof Route }[] = [
  { key: "rewind", label: "Prerequisite Rewind", icon: Route },
  { key: "misconception", label: "Misconception Check", icon: ClipboardCheck },
  { key: "drill", label: "Socratic Drill", icon: Brain },
  { key: "formula", label: "Formula Tutor", icon: Sigma },
  { key: "region", label: "Region Explain", icon: ImagePlus },
  { key: "plan", label: "Study Plan", icon: GraduationCap }
];

export default function LearningToolsPanel({
  courseId,
  selectedVideo,
  selectedMomentId,
  question,
  query,
  playbackTime,
  onJump
}: {
  courseId: string;
  selectedVideo: DatasetVideo | null;
  selectedMomentId?: string;
  question: string;
  query: string;
  playbackTime: number;
  onJump: (item: SearchResult | EvidenceItem | any) => void;
}) {
  const [active, setActive] = useState<LearningTool>("rewind");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [studentText, setStudentText] = useState("Gradient descent follows the gradient to minimize loss.");
  const [formula, setFormula] = useState("\\theta := \\theta - \\alpha \\nabla_\\theta J(\\theta)");
  const [regionImage, setRegionImage] = useState<File | null>(null);
  const [status, setStatus] = useState("");

  const common = {
    course_id: courseId,
    video_id: selectedVideo?.video_id,
    lecture_id: selectedVideo?.lecture_id,
    top_k: 5
  };

  const run = async () => {
    setBusy(true);
    setStatus("Running evidence-grounded learning skill...");
    try {
      let payload: any;
      if (active === "rewind") {
        payload = await prerequisiteRewind({ ...common, current_moment_id: selectedMomentId, question, target_concept: query || question });
      }
      if (active === "misconception") {
        payload = await misconceptionCheck({ ...common, student_text: studentText, related_concept: query });
      }
      if (active === "drill") {
        payload = await socraticDrill({ ...common, focus_topic: query || "gradient descent", difficulty: "medium", number_of_questions: 4 });
      }
      if (active === "formula") {
        payload = await formulaDerivation({ ...common, formula_latex: formula, question });
      }
      if (active === "region") {
        payload = await regionExplain({
          ...common,
          current_moment_id: selectedMomentId,
          question,
          timestamp: playbackTime,
          bbox: [0.12, 0.12, 0.88, 0.78],
          image: regionImage
        });
      }
      if (active === "plan") {
        await masteryUpdate({
          student_id: "demo_student",
          course_id: courseId,
          interactions: [{ question, query, timestamp: playbackTime, video_id: selectedVideo?.video_id }],
          watched_clips: selectedMomentId ? [{ moment_id: selectedMomentId, query }] : [],
          concepts: query ? query.split(",").map((item) => item.trim()).filter(Boolean) : []
        });
        payload = await studyPlan({ student_id: "demo_student", course_id: courseId, focus_topics: query ? [query] : undefined, days: 3 });
      }
      setResult(payload);
      setStatus(`${payload?.skill || "Learning skill"} self-check: ${payload?.self_check?.score ?? "n/a"}/10`);
    } catch (err) {
      setStatus(String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="learning-tools-panel">
      <div className="learning-head">
        <Compass size={17} />
        <div>
          <strong>Learning Tools</strong>
          <span>skill-augmented, evidence-grounded</span>
        </div>
      </div>

      <div className="learning-tool-tabs">
        {tools.map((tool) => {
          const Icon = tool.icon;
          return (
            <button key={tool.key} type="button" className={active === tool.key ? "active" : ""} onClick={() => setActive(tool.key)}>
              <Icon size={15} />
              <span>{tool.label}</span>
            </button>
          );
        })}
      </div>

      {active === "misconception" && (
        <textarea className="compact-textarea" value={studentText} onChange={(event) => setStudentText(event.target.value)} />
      )}

      {active === "formula" && (
        <textarea className="compact-textarea mono-input" value={formula} onChange={(event) => setFormula(event.target.value)} />
      )}

      {active === "region" && (
        <div className="region-help">
          <UploadPanel file={regionImage} onFile={setRegionImage} label="Optional region image" />
          <small>No upload means: explain the current video frame area using the selected timestamp/keyframe.</small>
        </div>
      )}

      <button type="button" className="run-learning-button" onClick={run} disabled={busy}>
        {busy ? "Running..." : "Run Learning Skill"}
      </button>
      {status && <div className="learning-status">{status}</div>}

      {result && <LearningResult result={result} onJump={onJump} />}
    </section>
  );
}

function LearningResult({ result, onJump }: { result: any; onJump: (item: any) => void }) {
  const moments = [
    ...(result.supporting_moments || []),
    ...(result.evidence_clips || []),
    ...(result.related_moments || []),
    ...((result.study_plan || []).flatMap((day: any) => day.review_clips || []))
  ];

  return (
    <div className="learning-result">
      <div className="learning-result-head">
        <strong>{result.skill}</strong>
        {result.self_check && <span>{result.self_check.score}/10</span>}
      </div>

      {result.target_concept && <p><strong>Target:</strong> {result.target_concept}</p>}
      {result.prerequisite_concepts?.length > 0 && <p><strong>Before this:</strong> {result.prerequisite_concepts.join(" -> ")}</p>}
      {result.misconception && <p><strong>Detected:</strong> {result.misconception}</p>}
      {result.formula_latex && <MathText text={result.formula_latex} block className="learning-formula" />}
      {result.region_ocr?.text && <p><strong>Region OCR:</strong> {result.region_ocr.text}</p>}
      {result.crop_url && <img className="region-crop" src={result.crop_url.startsWith("http") ? result.crop_url : `${import.meta.env.VITE_API_BASE || "http://localhost:8000"}${result.crop_url}`} alt="Selected region crop" />}

      {(result.explanation_markdown || result.correction_markdown || result.derivation_markdown) && (
        <MarkdownMath text={result.explanation_markdown || result.correction_markdown || result.derivation_markdown} />
      )}

      {result.questions?.length > 0 && (
        <div className="drill-list">
          {result.questions.map((item: any, index: number) => (
            <details key={`${item.question}-${index}`}>
              <summary>{item.question}</summary>
              <p><strong>Hint:</strong> {item.hint}</p>
              <p><strong>Answer:</strong> {item.answer_key}</p>
              {item.evidence && <button type="button" onClick={() => onJump(item.evidence)}>Jump to evidence</button>}
            </details>
          ))}
        </div>
      )}

      {result.study_plan?.length > 0 && (
        <div className="study-plan-list">
          {result.study_plan.map((day: any) => (
            <article key={day.day}>
              <strong>Day {day.day}: {day.focus}</strong>
              <p>{day.activity}</p>
            </article>
          ))}
        </div>
      )}

      {moments.length > 0 && (
        <div className="learning-evidence-grid">
          {moments.slice(0, 4).map((item: any) => (
            <VideoEvidenceCard key={`${item.moment_id}-${item.start_time}`} item={item} onSelect={() => onJump(item)} />
          ))}
        </div>
      )}
    </div>
  );
}
