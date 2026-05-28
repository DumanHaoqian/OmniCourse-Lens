import { useEffect, useState } from "react";
import { apiGet, Course, CourseSummary } from "./api";
import Layout, { TabKey } from "./components/Layout";
import SearchVideoPage from "./components/SearchVideoPage";
import CheatsheetPage from "./components/CheatsheetPage";
import KnowledgeGraphPage from "./components/KnowledgeGraphPage";
import AgentQAPage from "./components/AgentQAPage";

export default function App() {
  const [tab, setTab] = useState<TabKey>("search");
  const [courses, setCourses] = useState<CourseSummary[]>([]);
  const [course, setCourse] = useState<Course | null>(null);
  const [health, setHealth] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([apiGet<CourseSummary[]>("/api/courses"), apiGet<any>("/api/health")])
      .then(async ([items, status]) => {
        setCourses(items);
        setHealth(status);
        if (items[0]) setCourse(await apiGet<Course>(`/api/courses/${items[0].course_id}`));
      })
      .catch((err) => setError(String(err)));
  }, []);

  const selectCourse = async (courseId: string) => {
    setCourse(await apiGet<Course>(`/api/courses/${courseId}`));
  };

  return (
    <Layout
      tab={tab}
      onTab={setTab}
      courses={courses}
      selectedCourse={course?.course_id || ""}
      onCourse={selectCourse}
      health={health}
      error={error}
    >
      {tab === "search" && <SearchVideoPage course={course} />}
      {tab === "cheatsheet" && <CheatsheetPage course={course} />}
      {tab === "graph" && <KnowledgeGraphPage course={course} />}
      {tab === "qa" && <AgentQAPage course={course} />}
    </Layout>
  );
}
