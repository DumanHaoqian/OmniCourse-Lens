import { API_BASE, EvidenceItem, SearchResult } from "../api";

type Item = SearchResult | EvidenceItem;

export default function VideoEvidenceCard({ item, onSelect }: { item: Item; onSelect?: () => void }) {
  const thumb = item.thumbnail_url ? `${API_BASE}${item.thumbnail_url}` : "";
  return (
    <article className="evidence-card" onClick={onSelect}>
      {thumb && <img src={thumb} alt={item.lecture_title} />}
      <div className="evidence-body">
        <div className="evidence-head">
          <strong>{item.lecture_title}</strong>
          <span>{Math.round(item.score * 100)}%</span>
        </div>
        <div className="timestamp">
          {item.start_time.toFixed(0)}-{item.end_time.toFixed(0)}s
        </div>
        <p>{item.matched_reason}</p>
        <div className="chips">
          {item.matched_modalities.slice(0, 5).map((modality) => (
            <span key={modality}>{modality}</span>
          ))}
        </div>
        {item.transcript_snippet && <blockquote>{item.transcript_snippet}</blockquote>}
        {item.ocr_snippet && <blockquote>{item.ocr_snippet}</blockquote>}
        {item.formula_latex && <code>{item.formula_latex}</code>}
      </div>
    </article>
  );
}
