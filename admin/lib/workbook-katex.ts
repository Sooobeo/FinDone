import katex from "katex";

const TRUST_REQUIRED_COMMAND = /\\(?:href|url|includegraphics|htmlClass|htmlId|htmlStyle|htmlData)\b/u;

/** Render only KaTeX-owned markup; untrusted source is returned by the React caller as text. */
export function renderWorkbookLatex(latex: string, displayMode: boolean) {
  if (TRUST_REQUIRED_COMMAND.test(latex)) return null;
  try {
    return katex.renderToString(latex, {
      displayMode,
      output: "htmlAndMathml",
      throwOnError: true,
      trust: false,
      strict: "error",
      maxExpand: 100,
      maxSize: 24,
    });
  } catch {
    return null;
  }
}
