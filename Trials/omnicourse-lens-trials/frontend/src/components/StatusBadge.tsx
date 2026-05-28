import { AlertTriangle, CircleCheck } from "lucide-react";

export default function StatusBadge({ label, ok, muted = false }: { label: string; ok: boolean; muted?: boolean }) {
  return (
    <span className={`status ${ok ? "ok" : muted ? "muted" : "warn"}`}>
      {ok ? <CircleCheck size={14} /> : <AlertTriangle size={14} />}
      {label}
    </span>
  );
}
