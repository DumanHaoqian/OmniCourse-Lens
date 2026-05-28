import { Image, Upload } from "lucide-react";

export default function UploadPanel({
  file,
  onFile,
  label = "Image"
}: {
  file: File | null;
  onFile: (file: File | null) => void;
  label?: string;
}) {
  return (
    <label className="upload-box">
      {file ? <Image size={18} /> : <Upload size={18} />}
      <span>{file ? file.name : label}</span>
      <input type="file" accept="image/*" onChange={(event) => onFile(event.target.files?.[0] || null)} />
    </label>
  );
}
