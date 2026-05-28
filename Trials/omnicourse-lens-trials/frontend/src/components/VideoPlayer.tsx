import { API_BASE, SearchResult } from "../api";

export default function VideoPlayer({ result }: { result: SearchResult | null }) {
  if (!result) return <div className="preview-empty">Select a moment</div>;
  const image = result.thumbnail_url ? `${API_BASE}${result.thumbnail_url}` : "";
  const video = result.video_url ? `${API_BASE}${result.video_url}#t=${Math.max(0, Math.floor(result.start_time))}` : "";
  return (
    <div className="preview-surface">
      {video ? <video src={video} poster={image} controls /> : image ? <img src={image} alt={result.lecture_title} /> : null}
      <div className="preview-meta">
        <strong>{result.lecture_title}</strong>
        <span>
          {result.start_time.toFixed(0)}-{result.end_time.toFixed(0)}s
        </span>
      </div>
    </div>
  );
}
