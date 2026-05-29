import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

export default function MarkdownMath({ text, className = "" }: { text: string; className?: string }) {
  const normalizedText = normalizeMathDelimiters(text || "");
  return (
    <div className={`markdown-math ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {normalizedText}
      </ReactMarkdown>
    </div>
  );
}

function normalizeMathDelimiters(text: string) {
  return text
    .replace(/\\\[([\s\S]*?)\\\]/g, (_match, body) => `\n$$\n${String(body).trim()}\n$$\n`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_match, body) => `$${String(body).trim()}$`);
}
