import MarkdownMath from "./MarkdownMath";

export default function MathText({
  text,
  block = false,
  className = ""
}: {
  text?: string | null;
  block?: boolean;
  className?: string;
}) {
  const content = block ? formulaMarkdown(text || "") : inlineMathMarkdown(text || "");
  return <MarkdownMath text={content} className={`math-text ${block ? "math-block-text" : "math-inline-text"} ${className}`} />;
}

export function inlineMathMarkdown(text: string) {
  if (!text) return "";
  if (hasMathDelimiters(text)) return text;
  let rendered = normalizeWhitespace(text);
  const replacements = formulaCandidates(rendered).sort((a, b) => b.length - a.length);
  for (const candidate of replacements) {
    const latex = latexify(candidate);
    if (!latex) continue;
    rendered = rendered.replace(candidate, `\\(${latex}\\)`);
  }
  return rendered;
}

export function renderModelMarkdown(text: string) {
  if (!text) return "";
  if (hasMathDelimiters(text)) return text;
  return text
    .split("\n")
    .map((line) => inlineMathMarkdown(line))
    .join("\n");
}

export function formulaMarkdown(text: string) {
  if (!text) return "";
  if (hasMathDelimiters(text)) return text;
  const candidates = formulaCandidates(text);
  const formula = candidates[0] || text;
  const latex = latexify(formula);
  if (!latex) return inlineMathMarkdown(text);
  return `\\[\n${latex}\n\\]`;
}

function hasMathDelimiters(text: string) {
  return /\\\(|\\\[|\$\$|(?<!\\)\$/.test(text);
}

function normalizeWhitespace(text: string) {
  return text.replace(/\s+/g, " ").trim();
}

function formulaCandidates(text: string) {
  const normalized = normalizeWhitespace(text);
  const patterns = [
    /θ\[t\+1\]\s*=\s*θ\[t\]\s*[−-]\s*α[^.;,\n]{0,100}/gi,
    /θ\s*:=\s*θ\s*[−-]\s*α[^.;,\n]{0,90}/gi,
    /dR(?:emp)?\s*\/?\s*dθ\s*\([^)]*\)?/gi,
    /R\s*emp\s*\(θ\)|Remp\s*\(θ\)/gi,
    /ˆ?θ\s*=\s*arg\s*min[^.;,\n]{0,100}/gi,
    /∀θ\s*∈\s*Θ[^.;,\n]{0,100}/gi,
    /\\frac\{[^}]+\}\{[^}]+\}[^.;,\n]{0,90}/gi,
    /\\mathrm\{[^}]+\}[^.;,\n]{0,70}/gi,
    /(?:mean squared error|MSE)\s*=\s*[^.;,\n]{0,90}/gi
  ];
  const found: string[] = [];
  for (const pattern of patterns) {
    for (const match of normalized.matchAll(pattern)) {
      const item = normalizeWhitespace(match[0]).replace(/[;,.]$/, "");
      if (item.length >= 4 && !found.includes(item)) found.push(item);
    }
  }
  if (!found.length && looksFormulaLike(normalized)) found.push(normalized);
  return found.slice(0, 4);
}

function looksFormulaLike(text: string) {
  if (text.length > 180) return false;
  return /[=∇θθα≤≥]|\\frac|arg\s*min|dθ|Remp|R\s*emp/i.test(text);
}

function latexify(text: string) {
  let latex = normalizeWhitespace(text);
  if (!latex) return "";
  latex = latex
    .replace(/−/g, "-")
    .replace(/θ\[t\+1\]/g, "\\theta_{t+1}")
    .replace(/θ\[t\]/g, "\\theta_t")
    .replace(/θ\s*\[\s*0\s*\]/g, "\\theta_0")
    .replace(/θ\s*\[\s*1\s*\]/g, "\\theta_1")
    .replace(/θ\s*\[\s*2\s*\]/g, "\\theta_2")
    .replace(/ˆθ/g, "\\hat{\\theta}")
    .replace(/theta/gi, "\\theta")
    .replace(/θ/g, "\\theta")
    .replace(/α/g, "\\alpha")
    .replace(/∇/g, "\\nabla")
    .replace(/≤/g, "\\le")
    .replace(/≥/g, "\\ge")
    .replace(/∀/g, "\\forall")
    .replace(/∈/g, "\\in")
    .replace(/Θ/g, "\\Theta")
    .replace(/\bRemp\b/g, "R_{\\mathrm{emp}}")
    .replace(/\bR\s+emp\b/g, "R_{\\mathrm{emp}}")
    .replace(/dR_{\\mathrm\{emp\}}\s*d\\theta/g, "\\frac{dR_{\\mathrm{emp}}}{d\\theta}")
    .replace(/dRemp\s*d\\theta/g, "\\frac{dR_{\\mathrm{emp}}}{d\\theta}")
    .replace(/dRemp\s*\/\s*d\\theta/g, "\\frac{dR_{\\mathrm{emp}}}{d\\theta}")
    .replace(/dθ/g, "d\\theta")
    .replace(/arg min/gi, "\\arg\\min")
    .replace(/\s+/g, " ")
    .trim();
  if (/[A-Za-z]{12,}/.test(latex) && !/\\mathrm|\\text|\\arg/.test(latex)) {
    return `\\text{${escapeLatexText(text.slice(0, 90))}}`;
  }
  return latex;
}

function escapeLatexText(text: string) {
  return normalizeWhitespace(text)
    .replace(/\\/g, "\\textbackslash{}")
    .replace(/[{}]/g, "")
    .replace(/_/g, "\\_")
    .replace(/&/g, "\\&")
    .replace(/%/g, "\\%");
}
