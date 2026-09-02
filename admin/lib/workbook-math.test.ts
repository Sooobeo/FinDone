import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { renderWorkbookLatex } from "@/lib/workbook-katex";
import {
  legacyExpressionToLatex,
  segmentWorkbookMath,
  type WorkbookMathSegment,
} from "@/lib/workbook-math";

function mathSegments(source: string) {
  return segmentWorkbookMath(source).filter(
    (segment): segment is Extract<WorkbookMathSegment, { kind: "math" }> => segment.kind === "math",
  );
}

function restoredSource(source: string) {
  return segmentWorkbookMath(source)
    .map((segment) => segment.kind === "text" ? segment.value : segment.source)
    .join("");
}

describe("legacyExpressionToLatex", () => {
  it("normalizes finance identifiers, scripts, and unicode operators", () => {
    expect(legacyExpressionToLatex("WACC=wE×ke+wD×kd×(1-T)")).toBe(
      "\\mathrm{WACC}=w_E \\times k_e+w_D \\times k_d \\times (1-T)",
    );
    expect(legacyExpressionToLatex("Revenue_(accrual)=CashCollected+AR_(end)-AR_(begin)")).toBe(
      "\\mathrm{Revenue}_{\\mathrm{accrual}}=\\mathrm{CashCollected}+" +
        "\\mathrm{AR}_{\\mathrm{end}}-\\mathrm{AR}_{\\mathrm{begin}}",
    );
  });

  it("normalizes workbook sqrt, summation, numeric x, and grouped digits", () => {
    expect(legacyExpressionToLatex("σ=sqrt(σ^2)")).toBe("\\sigma =\\sqrt{\\sigma ^2}");
    expect(legacyExpressionToLatex("Σ_(t=1)^n C/(1+y)^t")).toBe(
      "\\sum _{t=1}^n C/(1+y)^t",
    );
    expect(legacyExpressionToLatex("4,000x4%=160")).toBe(
      "4{,}000 \\times 4\\%=160",
    );
  });

  it("rejects malformed expressions instead of partially converting them", () => {
    expect(legacyExpressionToLatex("x_=1")).toBeNull();
    expect(legacyExpressionToLatex("x_^2")).toBeNull();
    expect(legacyExpressionToLatex("NBV_at_sale")).toBeNull();
    expect(legacyExpressionToLatex("PV=C/(r-g")).toBeNull();
  });
});

describe("segmentWorkbookMath", () => {
  it("promotes symbolic and numeric formulas embedded in Korean prose", () => {
    const symbolic = segmentWorkbookMath("관계: FV_n=PV_0(1+r)^n.");
    expect(symbolic).toEqual([
      { kind: "text", value: "관계: " },
      {
        kind: "math",
        value: "\\mathrm{FV}_n=\\mathrm{PV}_0(1+r)^n",
        source: "FV_n=PV_0(1+r)^n",
        display: false,
      },
      { kind: "text", value: "." },
    ]);

    const numeric = mathSegments("기초 자본은 9,400-4,100=5,300만원이다.");
    expect(numeric).toHaveLength(1);
    expect(numeric[0].value).toBe("9{,}400-4{,}100=5{,}300");
  });

  it("keeps Korean native while typesetting adjacent symbolic atoms", () => {
    const source = "자산(A)=부채(L)+자본(E).";
    const formulas = mathSegments(source);
    expect(formulas.map((segment) => segment.source)).toEqual(["(A)=", "(L)+", "(E)"]);
    expect(restoredSource(source)).toBe(source);
  });

  it("does not mistake source breadcrumbs or currency for formulas", () => {
    const breadcrumb = "자료 > ACC-01. 원문 finance_interview_app_final_spec.md:L1063";
    expect(mathSegments(breadcrumb)).toEqual([]);
    expect(segmentWorkbookMath("price $100 and $200")).toEqual([
      { kind: "text", value: "price $100 and $200" },
    ]);
  });

  it("supports explicit delimiters with the FinDone inline and block contract", () => {
    expect(mathSegments("값 $$x+1$$ 끝")[0]).toMatchObject({
      value: "x+1",
      source: "$$x+1$$",
      display: false,
    });
    expect(mathSegments("$$\nx+1\n$$")[0]).toMatchObject({ value: "x+1", display: true });
    expect(mathSegments("\\[x+1\\]")[0]).toMatchObject({ value: "x+1", display: true });
  });

  it("preserves malformed delimiters and expressions without truncation", () => {
    for (const source of ["broken $x_", "$ $", "PV=C/(r-g", "x_=1"]) {
      expect(restoredSource(source)).toBe(source);
    }
  });
});

describe("renderWorkbookLatex", () => {
  it("returns accessible KaTeX markup for valid input", () => {
    const html = renderWorkbookLatex("\\frac{1}{2}", false);
    expect(html).toContain('class="katex"');
    expect(html).toContain("<math");
  });

  it("returns null for malformed or untrusted commands", () => {
    expect(renderWorkbookLatex("\\frac{1", false)).toBeNull();
    expect(renderWorkbookLatex("\\htmlClass{unsafe}{x}", false)).toBeNull();
  });
});

describe("generated workbook corpus", () => {
  it("preserves every source string and renders every promoted formula", () => {
    const unitRoot = join(process.cwd(), "content", "workbook", "units");
    const sources: string[] = [];
    const visit = (value: unknown) => {
      if (typeof value === "string") sources.push(value);
      else if (Array.isArray(value)) value.forEach(visit);
      else if (value && typeof value === "object") Object.values(value).forEach(visit);
    };
    for (const filename of readdirSync(unitRoot).filter((value) => value.endsWith(".json"))) {
      visit(JSON.parse(readFileSync(join(unitRoot, filename), "utf8")));
    }

    const formulas = new Map<string, boolean>();
    for (const source of sources) {
      expect(restoredSource(source)).toBe(source);
      for (const segment of mathSegments(source)) formulas.set(segment.value, segment.display);
    }

    expect(formulas.size).toBeGreaterThan(500);
    for (const [latex, display] of formulas) {
      expect(renderWorkbookLatex(latex, display), latex).not.toBeNull();
      expect(latex).not.toContain("\\mathrm{sqrt}");
    }
  });
});
