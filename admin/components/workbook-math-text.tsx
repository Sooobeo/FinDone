import { memo } from "react";
import { renderWorkbookLatex } from "@/lib/workbook-katex";
import { segmentWorkbookMath } from "@/lib/workbook-math";

interface WorkbookMathTextProps {
  source: string;
  className?: string;
}

export const WorkbookMathText = memo(function WorkbookMathText({
  source,
  className = "",
}: WorkbookMathTextProps) {
  const segments = segmentWorkbookMath(source);
  return (
    <span className={["workbook-math-copy", className].filter(Boolean).join(" ")}>
      {segments.map((segment, index) => {
        if (segment.kind === "text") return segment.value;
        const html = renderWorkbookLatex(segment.value, segment.display);
        if (html == null) return segment.source;
        return (
          <span
            className={`workbook-math ${segment.display ? "workbook-math-display" : "workbook-math-inline"}`}
            // KaTeX is the sole HTML producer. The input is rendered with trust disabled.
            dangerouslySetInnerHTML={{ __html: html }}
            key={`${segment.source}-${index}`}
          />
        );
      })}
    </span>
  );
});
