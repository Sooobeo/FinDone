import katex from "katex";

/** Render only KaTeX-owned markup; untrusted source is returned by the React caller as text. */
export function renderWorkbookLatex(latex: string, displayMode: boolean) {
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
