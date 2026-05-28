import { Bot, FileText, Network, Search } from "lucide-react";
import type { ReactNode } from "react";
import { CourseSummary } from "../api";
import StatusBadge from "./StatusBadge";

export type TabKey = "search" | "cheatsheet" | "graph" | "qa";

type Props = {
  children: ReactNode;
  tab: TabKey;
  onTab: (tab: TabKey) => void;
  courses: CourseSummary[];
  selectedCourse: string;
  onCourse: (courseId: string) => void;
  health: any;
  error: string;
};

const tabs = [
  { key: "search" as const, label: "Search Video", icon: Search },
  { key: "cheatsheet" as const, label: "Cheatsheet", icon: FileText },
  { key: "graph" as const, label: "Knowledge Graph", icon: Network },
  { key: "qa" as const, label: "AI Tutor", icon: Bot }
];

export default function Layout({ children, tab, onTab, courses, selectedCourse, onCourse, health, error }: Props) {
  const providers = health?.providers || {};
  const intern = providers?.search?.internvideo3;
  const deepseek = providers?.deepseek_ocr;
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">OC</div>
          <div>
            <h1>OmniCourse Lens Trials</h1>
            <p>Multimodal lecture workspace</p>
          </div>
        </div>
        <nav className="nav">
          {tabs.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.key} className={tab === item.key ? "active" : ""} onClick={() => onTab(item.key)}>
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-section">
          <label>Course</label>
          <select value={selectedCourse} onChange={(event) => onCourse(event.target.value)}>
            {courses.map((course) => (
              <option key={course.course_id} value={course.course_id}>
                {course.title}
              </option>
            ))}
          </select>
        </div>
        <div className="provider-stack">
          <StatusBadge label="API" ok={health?.status === "ok"} />
          <StatusBadge label="InternVideo3" ok={Boolean(intern?.available)} muted={Boolean(intern?.local_checkpoint_detected)} />
          <StatusBadge label="DeepSeek OCR" ok={Boolean(deepseek?.available)} />
        </div>
      </aside>
      <main className="workspace">
        {error && <div className="error-band">{error}</div>}
        {children}
      </main>
    </div>
  );
}
