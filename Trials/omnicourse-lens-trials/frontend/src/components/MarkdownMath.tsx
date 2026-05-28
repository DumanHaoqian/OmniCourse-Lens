import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

export default function MarkdownMath({ text, className = "" }: { text: string; className?: string }) {
  return (
    <div className={`markdown-math ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {text || ""}
      </ReactMarkdown>
    </div>
  );
}
