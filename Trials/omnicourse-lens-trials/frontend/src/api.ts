export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export type CourseSummary = {
  course_id: string;
  title: string;
  description: string;
  lecture_count: number;
  moment_count: number;
};

export type Lecture = {
  lecture_id: string;
  title: string;
  duration: number;
  moments?: any[];
};

export type Course = CourseSummary & {
  lectures: Lecture[];
};

export type DatasetVideo = {
  video_id: string;
  filename: string;
  absolute_path: string;
  relative_path: string;
  size: number;
  duration?: number;
  ingestion_status: string;
  indexed_status: string;
  thumbnail?: string;
  title: string;
  course_id: string;
  lecture_id: string;
  slides_path?: string;
};

export type SearchResult = {
  moment_id: string;
  video_id?: string;
  course_id: string;
  lecture_id: string;
  lecture_title: string;
  start_time: number;
  end_time: number;
  score: number;
  score_breakdown: Record<string, number>;
  matched_reason: string;
  matched_modalities: string[];
  transcript_snippet: string;
  ocr_snippet: string;
  formula_latex: string;
  concept_tags: string[];
  thumbnail_url?: string;
  video_url?: string;
};

export type EvidenceItem = {
  moment_id: string;
  lecture_id: string;
  lecture_title: string;
  start_time: number;
  end_time: number;
  thumbnail_url?: string;
  matched_reason: string;
  matched_modalities: string[];
  transcript_snippet: string;
  ocr_snippet: string;
  formula_latex: string;
  score: number;
};

export type SubtitleCue = {
  start_time: number;
  end_time: number;
  text: string;
  provider: string;
  source: string;
  moment_id?: string;
  kind: "audio" | "ocr" | "supplemental";
};

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function textSearch(payload: {
  course_id: string;
  query: string;
  lecture_ids?: string[];
  video_ids?: string[];
  top_k: number;
}) {
  return apiPost<{ results: SearchResult[]; self_check?: any; provider_status?: any; scope_notice?: string; scope_fallback?: any }>("/api/search/text", payload);
}

export async function imageSearch(payload: {
  course_id: string;
  query: string;
  lecture_ids?: string[];
  video_ids?: string[];
  top_k: number;
  image: File;
}) {
  const form = new FormData();
  form.append("course_id", payload.course_id);
  form.append("query", payload.query);
  form.append("top_k", String(payload.top_k));
  if (payload.lecture_ids?.length) form.append("lecture_ids", payload.lecture_ids.join(","));
  if (payload.video_ids?.length) form.append("video_ids", payload.video_ids.join(","));
  form.append("image", payload.image);
  const res = await fetch(`${API_BASE}/api/search/image`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ results: SearchResult[]; image_ocr?: any; self_check?: any; provider_status?: any; scope_notice?: string; scope_fallback?: any }>;
}

export async function askTutor(payload: {
  course_id: string;
  question: string;
  lecture_id?: string;
  video_id?: string;
  current_timestamp?: number;
  top_k: number;
  image?: File | null;
}) {
  if (payload.image) {
    const form = new FormData();
    form.append("course_id", payload.course_id);
    form.append("question", payload.question);
    form.append("top_k", String(payload.top_k));
    if (payload.lecture_id) form.append("lecture_id", payload.lecture_id);
    if (payload.video_id) form.append("video_id", payload.video_id);
    if (payload.current_timestamp !== undefined) form.append("current_timestamp", String(payload.current_timestamp));
    form.append("image", payload.image);
    const res = await fetch(`${API_BASE}/api/qa`, { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }
  return apiPost("/api/qa", payload);
}

export async function datasetVideos() {
  return apiGet<DatasetVideo[]>("/api/dataset/videos");
}

export async function videoSubtitles(video_id: string) {
  return apiGet<{ video_id: string; cue_count: number; audio_cue_count: number; ocr_cue_count: number; cues: SubtitleCue[]; summary?: any }>(
    `/api/dataset/videos/${video_id}/subtitles`
  );
}

export async function ingestDatasetVideo(video_id: string, force_reingest = false) {
  return apiPost<{ result: any; rebuild_index: any }>("/api/dataset/ingest", { video_id, force_reingest });
}

export async function ingestAllDataset(limit?: number) {
  return apiPost<any>("/api/jobs/start-ingest-all", { limit });
}

export async function rebuildIndex() {
  return apiPost<any>("/api/index/rebuild", {});
}

export async function compileCheatsheet(payload: { tex_content?: string; filename?: string }) {
  return apiPost<any>("/api/cheatsheet/compile", payload);
}
