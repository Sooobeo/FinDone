export interface WorkbookTextSegment {
  kind: "text";
  value: string;
}

export interface WorkbookFormulaSegment {
  kind: "math";
  /** Validated LaTeX passed to KaTeX. */
  value: string;
  /** Exact source text restored when KaTeX rejects the expression. */
  source: string;
  display: boolean;
}

export type WorkbookMathSegment = WorkbookTextSegment | WorkbookFormulaSegment;

const SAFE_SYMBOLIC = /^[A-Za-z0-9_αβγδμρσλΔΣΠ∑∂()\[\]{}+\-−–—×÷*/^%.,=≈≤≥<>²√±& \t]+$/u;
const SAFE_MIXED_SYMBOLIC = /^[A-Za-z0-9_αβγδμρσλΔΣΠ∑∂가-힣()\[\]{}+\-−–—×÷*/^%.,=≈≤≥<>²√±& \t]+$/u;
const SYMBOLIC_RUN = /[A-Za-z0-9_αβγδμρσλΔΣΠ∑∂()\[\]{}+\-−–—×÷*/^%.,=≈≤≥<>²√±& \t]+/gu;
const SINGLE_SYMBOL = /^[A-Za-zαβγδμρσλΔΣΠ][A-Za-z0-9_αβγδμρσλΔΣΠ]*$/u;
const PARENTHESIZED_SINGLE_SYMBOL = /^\([A-Za-zαβγδμρσλΔΣΠ∑∂][A-Za-z0-9_αβγδμρσλΔΣΠ∑∂]*\)$/u;
const COMPARISON_OPERATOR = /≤|≥|≈|<=|>=|=|<|>/u;
const PROSE_LHS_TOKEN_GAP = /[A-Za-z0-9_αβγδμρσλΔΣ]\s+[A-Za-z0-9_αβγδμρσλΔΣ]/u;
const PROSE_HYPHENATED_LABEL = /[A-Za-z]{2,}[-–—][A-Za-z]{2,}/u;
const REPEATED_TEX_SCRIPT = /(?:_(?:\{[^{}]*\}|[A-Za-z0-9])){2}|(?:\^(?:\{[^{}]*\}|[A-Za-z0-9])){2}/u;
const ROOT_BASE_TOKEN = /^(?:\d+(?:\.\d+)?|[A-Za-z][A-Za-z0-9]*|[αβγδμρσλΔΣΠ])/u;
const SCRIPT_TOKEN = /^(?:[A-Z]+[0-9]*(?![a-z])|[A-Z][a-z0-9]*|[a-z][a-z0-9]*|[0-9]+)/u;
const STRONG_MATH_SIGNAL = /[=+×÷*/^%≈≤≥<>²√ΣΠ∑∂±]/u;
const SAFE_MATH_SIGNAL = /[0-9_=+\-−–—×÷*/^%≈≤≥<>²√ΣΠ∑∂±&]/u;
const PROSE_ASCII_WORD_GAP = /[A-Za-z]{2,}\s+[A-Za-z]{2,}/u;
const CONTENT_BREADCRUMB = /^\([A-Z][A-Z0-9-]{1,}(?:\s+[가-힣]+\s+\d+)?\)\s*>\s*[A-Z][A-Z0-9.-]*/u;
const CONTENT_ID_PREFIX = /^[A-Z]{2,}-\d+\s+/u;
const LOWERCASE_RATIO_LABEL = /^[a-z]+\/[a-z-]+$/u;
const OPERATOR_ONLY = /^[=+\-−–—×÷*/^%≈≤≥<>±&]+$/u;
const LEADING_INCOMPLETE_OPERATOR = /^[=+×÷*/^]/u;
const TRAILING_INCOMPLETE_OPERATOR = /[=+\-−–—×÷*/^]$/u;
const MIXED_EQUATION_SUFFIXES = [
  "이므로",
  "이라고 한다",
  "이라고 본다",
  "라면",
  "일 경우",
  "일 때",
  "을 사용",
  "를 사용",
  "을 적용",
  "를 적용",
  "으로 계산",
  "로 계산",
  "을 구한다",
  "를 구한다",
  "을 양쪽에서",
  "를 양쪽에서",
  "으로 연결",
  "로 연결",
  "으로 분해",
  "로 분해",
  "으로 보고",
  "로 보고",
  "으로,",
  "을 목표",
  "를 목표",
  "가 된다",
  "이 항상",
  "및 ",
  " 적용 ",
  " 가정",
  " 조건",
  " 따라서",
  " 동시에",
  " 독립",
  "의 단리식",
  " 또는",
  " 연결",
  " 일치",
  " 평가",
  " 유지",
  " 가능",
  " 성립",
  " 되어",
  " 된다",
  "이며",
  "이고",
  "이면",
  "이다",
] as const;
const MIXED_EQUATION_PARTICLES = [
  "으로",
  "에서",
  "보다",
  "은",
  "는",
  "이",
  "가",
  "을",
  "를",
  "와",
  "과",
  "로",
] as const;
const EQUATION_AFTER_COMMA = /^\s*(?:[A-Za-zαβγδμρσλΔΣΠ][A-Za-z0-9_αβγδμρσλΔΣΠ]*|[가-힣][가-힣 \t]{0,20})\s*=/u;
const KOREAN_OPERATOR_WORD = /^(?:곱하기|나누기|더하기|빼기)$/u;
const LATEX_FUNCTIONS = new Set(["max", "min", "ln", "log"]);
const NO_COMPARISON_FORMULA_TOPIC = /(?:^|\s)(?:할인포기비용|선도환율\/현물환율)(?:은|는)\s+(?:대략\s+)?/gu;

const KNOWN_SYMBOLIC_REWRITES = [
  ["(V_PD_P)/(V_FD_F)", "(V_P×D_P)/(V_F×D_F)"],
  ["uS_0", "u×S_0"],
  ["dS_0", "d×S_0"],
  ["RS_0", "R×S_0"],
  ["qV_u", "q×V_u"],
  ["(1−q)V_d", "(1−q)×V_d"],
  ["wR_A", "w×R_A"],
  ["(1−w)R_B", "(1−w)×R_B"],
  ["(1-w)R_B", "(1-w)×R_B"],
  ["wD_1", "w×D_1"],
  ["(1−w)D_2", "(1−w)×D_2"],
  ["(1-w)D_2", "(1-w)×D_2"],
  ["Ke^(−rT)N(", "K×e^(−r×T)×N("],
  ["Ke^(−rT)", "K×e^(−r×T)"],
  ["Ke^(-rT)", "K×e^(-r×T)"],
  ["S_0N(", "S_0×N("],
  ["(r+σ²/2)T", "(r+σ²/2)×T"],
  ["σ√T", "σ×√T"],
] as const;

function appendText(segments: WorkbookMathSegment[], value: string) {
  if (!value) return;
  const last = segments.at(-1);
  if (last?.kind === "text") last.value += value;
  else segments.push({ kind: "text", value });
}

function appendSegments(target: WorkbookMathSegment[], source: WorkbookMathSegment[]) {
  for (const segment of source) {
    if (segment.kind === "text") appendText(target, segment.value);
    else target.push(segment);
  }
}

function isEscaped(value: string, index: number) {
  let backslashes = 0;
  for (let cursor = index - 1; cursor >= 0 && value[cursor] === "\\"; cursor -= 1) {
    backslashes += 1;
  }
  return backslashes % 2 === 1;
}

function findClosingDelimiter(value: string, delimiter: string, start: number) {
  let cursor = value.indexOf(delimiter, start);
  while (cursor >= 0) {
    if (!isEscaped(value, cursor)) return cursor;
    cursor = value.indexOf(delimiter, cursor + delimiter.length);
  }
  return -1;
}

function explicitDelimiterAt(value: string, index: number) {
  if (value.startsWith("$$", index) && !isEscaped(value, index)) {
    return { open: "$$", close: "$$", display: "auto" } as const;
  }
  if (value.startsWith("\\[", index) && !isEscaped(value, index)) {
    return { open: "\\[", close: "\\]", display: true } as const;
  }
  if (value.startsWith("\\(", index) && !isEscaped(value, index)) {
    return { open: "\\(", close: "\\)", display: false } as const;
  }
  if (value[index] === "$" && !isEscaped(value, index)) {
    return { open: "$", close: "$", display: false } as const;
  }
  return null;
}

function canonicalSymbolicSource(value: string) {
  let result = value;
  for (const [original, canonical] of KNOWN_SYMBOLIC_REWRITES) {
    result = result.replaceAll(original, canonical);
  }
  result = result
    .replace(/\s+곱하기\s+/gu, "×")
    .replace(/\s+나누기\s+/gu, "/")
    .replace(/\s+더하기\s+/gu, "+")
    .replace(/\s+빼기\s+/gu, "-")
    .replace(/([0-9)%\]가-힣])x(?=[0-9(가-힣])/gu, "$1×")
    .replace(/sqrt\s*\(/gu, "√(")
    .replace(/([Σ∑])_\(([^()]+)\)/gu, "$1_{$2}")
    .replace(/(\d)\(,\)(?=\d{3}(?:\D|$))/gu, "$1,")
    .replace(/_​?\(([A-Za-z][A-Za-z0-9]*)\)/gu, "_$1")
    .replace(/([_^])\(\(([^()]+)\)\)/gu, "$1{$2}")
    .replace(/([_^])\(([^()]+)\)/gu, "$1{$2}")
    .replace(/([A-Za-zαβγδμρσλΔΣΠ])\s+([_^])/gu, "$1$2")
    .replace(/(^|[^A-Za-z0-9_])rT(?=$|[^A-Za-z0-9_])/gu, "$1r×T")
    .replace(/(^|[^A-Za-z0-9_])wE(?=$|[^A-Za-z0-9_])/gu, "$1w_E")
    .replace(/(^|[^A-Za-z0-9_])wD(?=$|[^A-Za-z0-9_])/gu, "$1w_D")
    .replace(/(^|[^A-Za-z0-9_])ke(?=$|[^A-Za-z0-9_])/gu, "$1k_e")
    .replace(/(^|[^A-Za-z0-9_])kd(?=$|[^A-Za-z0-9_])/gu, "$1k_d")
    .replace(/β\s+L/gu, "β_L")
    .replace(/β\s+U/gu, "β_U");
  return result;
}

function matchingDelimiterIndex(value: string, start: number) {
  const opening = value[start];
  const closing = opening === "(" ? ")" : opening === "[" ? "]" : opening === "{" ? "}" : "";
  if (!closing) return -1;
  let depth = 0;
  for (let index = start; index < value.length; index += 1) {
    if (value[index] === opening) depth += 1;
    else if (value[index] === closing) {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  return -1;
}

function hasBalancedDelimiters(value: string) {
  const stack: string[] = [];
  const pairs: Record<string, string> = { ")": "(", "]": "[", "}": "{" };
  for (const character of value) {
    if ("([{".includes(character)) stack.push(character);
    else if (pairs[character] && stack.pop() !== pairs[character]) return false;
  }
  return stack.length === 0;
}

function scriptEndExclusive(value: string, start: number): number | null {
  if (start >= value.length) return null;
  if (value[start] === "{" || value[start] === "(") {
    const end = matchingDelimiterIndex(value, start);
    return end <= start + 1 ? null : end + 1;
  }
  if ("+-−–—".includes(value[start])) {
    const match = value.slice(start).match(/^[+-−–—]\d+/u);
    return match ? start + match[0].length : null;
  }
  const match = value.slice(start).match(SCRIPT_TOKEN);
  return match ? start + match[0].length : null;
}

function braceMulticharScripts(value: string): string | null {
  let output = "";
  let index = 0;
  while (index < value.length) {
    const operator = value[index];
    if (operator !== "_" && operator !== "^") {
      output += operator;
      index += 1;
      continue;
    }
    const scriptStart = index + 1;
    const scriptEnd = scriptEndExclusive(value, scriptStart);
    if (scriptEnd == null) return null;
    output += operator;
    if (value[scriptStart] === "{") {
      const inner = braceMulticharScripts(value.slice(scriptStart + 1, scriptEnd - 1));
      if (inner == null) return null;
      output += `{${inner}}`;
    } else if (value[scriptStart] === "(") {
      const inner = braceMulticharScripts(value.slice(scriptStart + 1, scriptEnd - 1));
      if (inner == null) return null;
      output += `{(${inner})}`;
    } else {
      const token = value.slice(scriptStart, scriptEnd);
      output += token.length > 1 ? `{${token}}` : token;
    }
    index = scriptEnd;
  }
  return output;
}

function rootAtomEndExclusive(value: string, start: number): number | null {
  const match = value.slice(start).match(ROOT_BASE_TOKEN);
  if (!match) return null;
  let cursor = start + match[0].length;
  while (cursor < value.length) {
    if (value[cursor] === "²") cursor += 1;
    else if (value[cursor] === "_" || value[cursor] === "^") {
      const end = scriptEndExclusive(value, cursor + 1);
      if (end == null) return null;
      cursor = end;
    } else break;
  }
  return cursor;
}

function replaceSquareRoots(value: string): string | null {
  let output = "";
  let index = 0;
  while (index < value.length) {
    if (value[index] !== "√") {
      output += value[index];
      index += 1;
      continue;
    }
    const atomStart = index + 1;
    if (atomStart >= value.length) return null;
    const parenthesized = value[atomStart] === "(";
    const atomEnd = parenthesized
      ? matchingDelimiterIndex(value, atomStart) + 1
      : rootAtomEndExclusive(value, atomStart);
    if (!atomEnd || atomEnd <= atomStart) return null;
    const radicand = parenthesized
      ? value.slice(atomStart + 1, atomEnd - 1)
      : value.slice(atomStart, atomEnd);
    if (!radicand) return null;
    output += `\\sqrt{${radicand}}`;
    index = atomEnd;
  }
  return output;
}

function uprightAsciiIdentifiers(value: string) {
  let output = "";
  let index = 0;
  while (index < value.length) {
    if (value[index] === "\\") {
      output += value[index];
      index += 1;
      while (index < value.length && /[A-Za-z]/u.test(value[index])) {
        output += value[index];
        index += 1;
      }
      continue;
    }
    if (!/[A-Za-z]/u.test(value[index])) {
      output += value[index];
      index += 1;
      continue;
    }

    const tokenStart = index;
    if (index > 0 && (value[index - 1] === "_" || value[index - 1] === "^")) {
      index += 1;
    } else {
      while (index < value.length && /[A-Za-z0-9]/u.test(value[index])) index += 1;
    }
    const token = value.slice(tokenStart, index);
    const letterCount = [...token].filter((character) => /[A-Za-z]/u.test(character)).length;
    let nextNonSpace = index;
    while (nextNonSpace < value.length && /\s/u.test(value[nextNonSpace])) nextNonSpace += 1;
    if (LATEX_FUNCTIONS.has(token) && value[nextNonSpace] === "(") output += `\\${token}`;
    else if (letterCount > 1) output += `\\mathrm{${token}}`;
    else output += token;
  }
  return output;
}

function isDigitGroupingComma(value: string, index: number) {
  return index > 0
    && /\d/u.test(value[index - 1])
    && index + 3 < value.length
    && /^\d{3}$/u.test(value.slice(index + 1, index + 4))
    && (index + 4 === value.length || !/\d/u.test(value[index + 4]));
}

function isDecimalPoint(value: string, index: number) {
  return value[index] === "."
    && index > 0
    && index + 1 < value.length
    && /\d/u.test(value[index - 1])
    && /\d/u.test(value[index + 1]);
}

function isEllipsisPoint(value: string, index: number) {
  return value[index] === "." && (value[index - 1] === "." || value[index + 1] === ".");
}

function isListMarkerClose(value: string, index: number) {
  if (
    value[index] !== ")"
    || (index + 1 < value.length && !/\s/u.test(value[index + 1]))
  ) return false;
  let cursor = index - 1;
  while (cursor >= 0 && /\d/u.test(value[cursor])) cursor -= 1;
  return cursor < index - 1
    && (cursor < 0 || /[\s.!?。;]/u.test(value[cursor]));
}

function hasUnsafeTopLevelPunctuation(value: string) {
  const stack: string[] = [];
  const pairs: Record<string, string> = { ")": "(", "]": "[", "}": "{" };
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if ("([{".includes(character)) stack.push(character);
    else if (pairs[character]) stack.pop();
    else if (character === "," && stack.length === 0 && !isDigitGroupingComma(value, index)) return true;
    else if (
      ".!?。".includes(character)
      && stack.length === 0
      && !isDecimalPoint(value, index)
      && !isEllipsisPoint(value, index)
      && value.slice(index + 1).trim()
    ) return true;
  }
  return false;
}

function hasProseLikeComparisonLabel(value: string) {
  const comparison = COMPARISON_OPERATOR.exec(value);
  if (!comparison || comparison.index == null) return false;
  const label = value.slice(0, comparison.index);
  return PROSE_LHS_TOKEN_GAP.test(label) || PROSE_HYPHENATED_LABEL.test(label);
}

function isSafeSymbolicExpression(value: string) {
  const canonical = canonicalSymbolicSource(value);
  if (!SAFE_SYMBOLIC.test(canonical) || !hasBalancedDelimiters(canonical)) return false;
  if (/-OtherDebtLi$/u.test(canonical)) return false;
  const comparison = COMPARISON_OPERATOR.exec(value);
  if (comparison?.index === 0) return false;
  if (value.includes("**") || value.includes("__")) return false;
  if (TRAILING_INCOMPLETE_OPERATOR.test(value.trim())) return false;
  if (hasProseLikeComparisonLabel(value) || hasUnsafeTopLevelPunctuation(value)) return false;
  const rooted = replaceSquareRoots(canonical);
  if (rooted == null) return false;
  const scripted = braceMulticharScripts(rooted);
  if (scripted == null || REPEATED_TEX_SCRIPT.test(scripted)) return false;
  return SAFE_MATH_SIGNAL.test(value)
    || SINGLE_SYMBOL.test(value)
    || PARENTHESIZED_SINGLE_SYMBOL.test(value);
}

function looksLikeAutoMath(value: string) {
  const candidate = value.trim();
  if (
    !candidate
    || CONTENT_BREADCRUMB.test(candidate)
    || CONTENT_ID_PREFIX.test(candidate)
    || /\bPDF\b/u.test(candidate)
  ) return false;
  const withoutBullet = candidate.replace(/^[-–—]\s+/u, "");
  if (
    candidate.startsWith("/")
    || LEADING_INCOMPLETE_OPERATOR.test(candidate)
    || LOWERCASE_RATIO_LABEL.test(withoutBullet)
    || OPERATOR_ONLY.test(candidate)
  ) return false;
  if (!COMPARISON_OPERATOR.test(candidate) && PROSE_ASCII_WORD_GAP.test(candidate)) return false;
  return STRONG_MATH_SIGNAL.test(canonicalSymbolicSource(candidate))
    || PARENTHESIZED_SINGLE_SYMBOL.test(candidate);
}

function canonicalExpressionToLatex(value: string) {
  const rooted = replaceSquareRoots(value);
  if (rooted == null) return null;
  const scripted = braceMulticharScripts(rooted);
  if (scripted == null || REPEATED_TEX_SCRIPT.test(scripted)) return null;

  return uprightAsciiIdentifiers(
    scripted
      .replaceAll("×", " \\times ")
      .replaceAll("÷", " \\div ")
      .replace(/[−–—]/gu, "-")
      .replaceAll("≈", " \\approx ")
      .replaceAll("≤", " \\le ")
      .replaceAll("≥", " \\ge ")
      .replaceAll("²", "^{2}")
      .replaceAll("%", "\\%")
      .replaceAll("α", "\\alpha ")
      .replaceAll("β", "\\beta ")
      .replaceAll("γ", "\\gamma ")
      .replaceAll("δ", "\\delta ")
      .replaceAll("μ", "\\mu ")
      .replaceAll("ρ", "\\rho ")
      .replaceAll("σ", "\\sigma ")
      .replaceAll("λ", "\\lambda ")
      .replaceAll("Δ", "\\Delta ")
      .replaceAll("Σ", "\\sum ")
      .replaceAll("∑", "\\sum ")
      .replaceAll("Π", "\\prod ")
      .replaceAll("∂", "\\partial ")
      .replaceAll("±", "\\pm ")
      .replaceAll("&", "\\&")
      .replace(/(\d),(?=\d{3}(?:\D|$))/gu, "$1{,}"),
  ).replace(/[ \t]+/gu, " ").trim();
}

/** Convert a reviewed workbook's legacy pseudo-math to validated KaTeX input. */
export function legacyExpressionToLatex(value: string): string | null {
  const canonical = canonicalSymbolicSource(value.trim());
  if (!isSafeSymbolicExpression(canonical)) return null;
  return canonicalExpressionToLatex(canonical);
}

function mixedKoreanExpressionToLatex(
  value: string,
  requireComparison: boolean,
  allowLeadingPlus = false,
) {
  const canonical = canonicalSymbolicSource(value.trim());
  const hasRequiredSignal = requireComparison
    ? COMPARISON_OPERATOR.test(canonical)
    : /[+\-−–—×÷*/^]/u.test(canonical) && /[가-힣]/u.test(canonical);
  if (
    !hasRequiredSignal
    || !SAFE_MIXED_SYMBOLIC.test(canonical)
    || !hasBalancedDelimiters(canonical)
    || CONTENT_BREADCRUMB.test(canonical)
    || (
      LEADING_INCOMPLETE_OPERATOR.test(canonical)
      && !(
        allowLeadingPlus
        && /^\+(?=\d)[\s\S]*=\s*[+-](?=\d)/u.test(canonical)
      )
    )
    || TRAILING_INCOMPLETE_OPERATOR.test(canonical)
    || canonical.includes("**")
    || canonical.includes("__")
    || /(?:=현|\/평|[-−–—]기|[-−–—]처분시 장부|(?:원|만원|억원|백만원)이|-OtherDebtLi)$/u
      .test(canonical)
  ) return null;
  const withKoreanText = canonical.replace(
    /[가-힣]+(?:[ \t]+[가-힣]+)*/gu,
    (term) => `\\text{${term}}`,
  );
  return canonicalExpressionToLatex(withKoreanText);
}

function mixedEquationClauseStart(value: string, comparisonIndex: number) {
  let delimiterDepth = 0;
  for (let cursor = comparisonIndex - 1; cursor >= 0; cursor -= 1) {
    const character = value[cursor];
    if (isListMarkerClose(value, cursor) && delimiterDepth === 0) return cursor + 1;
    if (")]}".includes(character)) delimiterDepth += 1;
    else if ("([{".includes(character)) delimiterDepth = Math.max(0, delimiterDepth - 1);
    if (delimiterDepth > 0) continue;
    if (/[:;!?。…•·\r\n]/u.test(character)) return cursor + 1;
    if (
      character === "."
      && !isDecimalPoint(value, cursor)
      && !isEllipsisPoint(value, cursor)
    ) return cursor + 1;
    if (character === "," && !isDigitGroupingComma(value, cursor)) return cursor + 1;
  }
  return 0;
}

function mixedEquationStart(
  value: string,
  comparisonIndex: number,
  allowSpacedOperands = true,
): number | null {
  const clauseStart = mixedEquationClauseStart(value, comparisonIndex);
  const lhsClause = value.slice(clauseStart, comparisonIndex)
    .replace(/[A-Za-z]{2,}(?:[-–—][A-Za-z]{2,})+/gu, "");
  const lhsHasArithmetic = allowSpacedOperands
    && /[+\-−–—×÷*/^]|(?:곱하기|나누기|더하기|빼기)/u.test(lhsClause);
  let cursor = comparisonIndex - 1;
  while (cursor >= 0 && /\s/u.test(value[cursor])) cursor -= 1;
  let delimiterDepth = 0;
  let crossedPlainOperandGap = false;
  let foundFormulaBoundary = false;
  while (cursor >= 0) {
    const character = value[cursor];
    if (isListMarkerClose(value, cursor) && delimiterDepth === 0) break;
    if (")]}".includes(character)) delimiterDepth += 1;
    else if ("([{".includes(character)) delimiterDepth = Math.max(0, delimiterDepth - 1);
    if (delimiterDepth === 0) {
      if (/[:;!?。…•·\r\n]/u.test(character)) break;
      if (
        character === "."
        && !isDecimalPoint(value, cursor)
        && !isEllipsisPoint(value, cursor)
      ) break;
      if (character === "," && !isDigitGroupingComma(value, cursor)) break;
      if (/\s/u.test(character)) {
        let previous = cursor - 1;
        while (previous >= 0 && /\s/u.test(value[previous])) previous -= 1;
        let next = cursor + 1;
        while (next < comparisonIndex && /\s/u.test(value[next])) next += 1;
        let previousWordStart = previous;
        while (previousWordStart >= 0 && /[가-힣]/u.test(value[previousWordStart])) {
          previousWordStart -= 1;
        }
        const previousWord = value.slice(previousWordStart + 1, previous + 1);
        const nextWord = value.slice(next).match(/^[가-힣]+/u)?.[0] ?? "";
        const nextStartsMathAtom = /[0-9A-Za-zαβγδμρσλΔΣΠ([]/u.test(value[next] ?? "");
        const koreanOperatorAdjacent = KOREAN_OPERATOR_WORD.test(previousWord)
          || KOREAN_OPERATOR_WORD.test(nextWord);
        const formulaBoundary = lhsHasArithmetic
          && (
            /(?:은|는|인|하면|이면|라면|늘면|줄면|변하면|증가하면|감소하면|이므로|하므로|때|기준|공식|즉|제외해)$/u
              .test(previousWord)
            || (
              nextStartsMathAtom
              && (previousWord === "뺀" || previousWord.endsWith("에서"))
            )
          );
        const proseParticleBeforeSign = /[은는이가을를와과로]/u.test(value[previous] ?? "")
          && /[+\-−–—]/u.test(value[next] ?? "");
        if (formulaBoundary) {
          foundFormulaBoundary = true;
          break;
        }
        const operatorAdjacent = /[+\-−–—×÷*/^]/u.test(value[previous] ?? "")
          || /[+\-−–—×÷*/^]/u.test(value[next] ?? "");
        if (
          previous < 0
          || proseParticleBeforeSign
          || (!koreanOperatorAdjacent && !operatorAdjacent && !lhsHasArithmetic)
        ) break;
        if (!koreanOperatorAdjacent && !operatorAdjacent) crossedPlainOperandGap = true;
      }
    }
    cursor -= 1;
  }
  const start = cursor + 1;
  if (crossedPlainOperandGap && !foundFormulaBoundary && start <= clauseStart) {
    const lhs = value.slice(start, comparisonIndex).trimStart();
    const firstOperator = lhs.search(/[+\-−–—×÷*/^]/u);
    const firstOperand = firstOperator < 0 ? lhs : lhs.slice(0, firstOperator);
    if (!/[0-9A-Za-zαβγδμρσλΔΣΠ]/u.test(firstOperand)) {
      const fallback = mixedEquationStart(value, comparisonIndex, false);
      if (fallback == null) return null;
      const fallbackLhs = value.slice(fallback, comparisonIndex).trim();
      return /^(?:주|대|건|원|만원|억원)$/u.test(fallbackLhs) ? null : fallback;
    }
  }
  return start;
}

function mixedEquationEnd(value: string, comparisonIndex: number) {
  const stack: string[] = [];
  const pairs: Record<string, string> = { ")": "(", "]": "[", "}": "{" };
  for (let index = comparisonIndex + 1; index < value.length; index += 1) {
    const character = value[index];
    if (character === "(" && stack.length === 0) {
      const closeIndex = matchingDelimiterIndex(value, index);
      if (closeIndex > index) {
        const inner = value.slice(index + 1, closeIndex);
        const koreanWords = inner.match(/[가-힣]+/gu) ?? [];
        const hasMathOperator = /[=+\-−–—×÷*/^%≈≤≥<>,]/u.test(inner);
        if (
          koreanWords.length >= 3
          && !hasMathOperator
          && /(기준|부호|반대|설명|주의)/u.test(inner)
        ) return index;
      }
    }
    if ("([{".includes(character)) stack.push(character);
    else if (pairs[character]) {
      if (stack.at(-1) !== pairs[character]) return index;
      stack.pop();
    }
    if (stack.length > 0) continue;
    if (MIXED_EQUATION_SUFFIXES.some((suffix) => value.startsWith(suffix, index))) {
      return index;
    }
    const particle = MIXED_EQUATION_PARTICLES.find((candidate) => {
      if (
        !value.startsWith(candidate, index)
        || !/[A-Za-z0-9_αβγδμρσλΔΣΠ가-힣)%\]]/u.test(value[index - 1] ?? "")
        || !/\s/u.test(value[index + candidate.length] ?? "")
      ) return false;
      const remainder = value.slice(index + candidate.length).trimStart();
      const directContinuation = /^[+\-−–—×÷*/^]/u.test(remainder)
        || /^(?:곱하기|나누기|더하기|빼기)(?:\s|$)/u.test(remainder);
      const koreanRoot = value.slice(0, index).match(/[가-힣]+$/u)?.[0] ?? "";
      const shortRootContinues = koreanRoot.length <= 1
        && /^[A-Za-z0-9_가-힣()% \t]{0,24}[+\-−–—×÷*/^]/u.test(remainder);
      return !directContinuation && !shortRootContinues;
    });
    if (particle) return index;
    if (
      character === "다"
      && (index + 1 === value.length || /[\s,.!?。;]/u.test(value[index + 1]))
    ) return index;
    if (";!?。…\r\n".includes(character)) return index;
    if (
      character === "."
      && !isDecimalPoint(value, index)
      && !isEllipsisPoint(value, index)
    ) return index;
    if (character === "," && !isDigitGroupingComma(value, index)) {
      const remainder = value.slice(index + 1);
      if (!EQUATION_AFTER_COMMA.test(remainder)) return index;
    }
  }
  return value.length;
}

function segmentMixedKoreanEquations(value: string) {
  const segments: WorkbookMathSegment[] = [];
  let cursor = 0;
  let searchFrom = 0;
  while (searchFrom < value.length) {
    const comparisonIndex = value.indexOf("=", searchFrom);
    if (comparisonIndex < 0) break;
    let start = mixedEquationStart(value, comparisonIndex);
    if (start == null) {
      searchFrom = comparisonIndex + 1;
      continue;
    }
    const end = mixedEquationEnd(value, comparisonIndex);
    let raw = value.slice(start, end);
    let leading = raw.match(/^\s*/u)?.[0] ?? "";
    let trailing = raw.match(/\s*$/u)?.[0] ?? "";
    let source = raw.slice(leading.length, raw.length - trailing.length);
    let allowLeadingPlus = source.startsWith("+")
      && /(?:은|는)\s*$/u.test(value.slice(0, start));
    let latex = mixedKoreanExpressionToLatex(source, true, allowLeadingPlus);
    if (latex == null) {
      const fallbackStart = mixedEquationStart(value, comparisonIndex, false);
      if (fallbackStart != null && fallbackStart !== start) {
        start = fallbackStart;
        raw = value.slice(start, end);
        leading = raw.match(/^\s*/u)?.[0] ?? "";
        trailing = raw.match(/\s*$/u)?.[0] ?? "";
        source = raw.slice(leading.length, raw.length - trailing.length);
        allowLeadingPlus = source.startsWith("+")
          && /(?:은|는)\s*$/u.test(value.slice(0, start));
        latex = mixedKoreanExpressionToLatex(source, true, allowLeadingPlus);
      }
    }
    if (latex == null || end <= comparisonIndex + 1 || start < cursor) {
      searchFrom = comparisonIndex + 1;
      continue;
    }
    appendText(segments, value.slice(cursor, start) + leading);
    segments.push({ kind: "math", value: latex, source, display: false });
    appendText(segments, trailing);
    cursor = end;
    searchFrom = end;
  }
  appendText(segments, value.slice(cursor));
  return segments;
}

function segmentMixedKoreanRelations(value: string) {
  const segments: WorkbookMathSegment[] = [];
  let cursor = 0;
  for (const match of value.matchAll(NO_COMPARISON_FORMULA_TOPIC)) {
    const start = (match.index ?? 0) + match[0].length;
    if (start < cursor) continue;
    const end = mixedEquationEnd(value, start - 1);
    const raw = value.slice(start, end);
    const leading = raw.match(/^\s*/u)?.[0] ?? "";
    const trailing = raw.match(/\s*$/u)?.[0] ?? "";
    const source = raw.slice(leading.length, raw.length - trailing.length);
    const latex = mixedKoreanExpressionToLatex(source, false);
    if (latex == null || end <= start) continue;
    appendText(segments, value.slice(cursor, start) + leading);
    segments.push({ kind: "math", value: latex, source, display: false });
    appendText(segments, trailing);
    cursor = end;
  }
  appendText(segments, value.slice(cursor));
  return segments;
}

function splitTopLevelCandidate(value: string) {
  const stack: string[] = [];
  const pairs: Record<string, string> = { ")": "(", "]": "[", "}": "{" };
  let segmentStart = 0;
  const parts: string[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const listMarker = value.slice(index).match(/^\d+\)\s*/u)?.[0];
    if (
      stack.length === 0
      && listMarker
      && (index === 0 || /\s/u.test(value[index - 1]))
    ) {
      if (index > segmentStart) parts.push(value.slice(segmentStart, index));
      parts.push(listMarker);
      segmentStart = index + listMarker.length;
      index = segmentStart - 1;
      continue;
    }
    const character = value[index];
    if (character === "(" && stack.length === 0) {
      const closeIndex = matchingDelimiterIndex(value, index);
      if (closeIndex > index) {
        const inner = value.slice(index + 1, closeIndex);
        const koreanWords = inner.match(/[가-힣]+/gu) ?? [];
        const hasMathOperator = /[=+\-−–—×÷*/^%≈≤≥<>,]/u.test(inner);
        if (koreanWords.length >= 3 && !hasMathOperator) {
          if (index > segmentStart) parts.push(value.slice(segmentStart, index));
          parts.push(value.slice(index, closeIndex + 1));
          segmentStart = closeIndex + 1;
          index = closeIndex;
          continue;
        }
      }
    }
    if ("([{".includes(character)) stack.push(character);
    else if (pairs[character]) {
      if (stack.at(-1) !== pairs[character]) return [value];
      stack.pop();
    } else if (stack.length === 0 && character === "," && !isDigitGroupingComma(value, index)) {
      const before = value.slice(segmentStart, index);
      const after = value.slice(index + 1);
      if (COMPARISON_OPERATOR.test(before) || COMPARISON_OPERATOR.test(after)) {
        parts.push(before, character);
        segmentStart = index + 1;
      }
    } else if (
      stack.length === 0
      && ".!?。".includes(character)
      && !isDecimalPoint(value, index)
      && value.slice(index + 1).trim()
      && (
        COMPARISON_OPERATOR.test(value.slice(segmentStart, index))
        || COMPARISON_OPERATOR.test(value.slice(index + 1))
      )
    ) {
      parts.push(value.slice(segmentStart, index), character);
      segmentStart = index + 1;
    }
  }
  if (stack.length) return [value];
  if (!parts.length) return [value];
  parts.push(value.slice(segmentStart));
  return parts;
}

function segmentCandidate(rawValue: string, allowSplit = true): WorkbookMathSegment[] {
  if (!rawValue.trim()) return [{ kind: "text", value: rawValue }];
  const leading = rawValue.match(/^\s*/u)?.[0] ?? "";
  const trailing = rawValue.match(/\s*$/u)?.[0] ?? "";
  let value = rawValue.slice(leading.length, rawValue.length - trailing.length);
  const result: WorkbookMathSegment[] = [];
  appendText(result, leading);
  if (!value) {
    appendText(result, trailing);
    return result;
  }

  if (allowSplit) {
    const parts = splitTopLevelCandidate(value);
    if (parts.length > 1) {
      for (const part of parts) appendSegments(result, segmentCandidate(part, false));
      appendText(result, trailing);
      return result;
    }
  }

  const terminal = value.match(/[,，.!?。]+$/u)?.[0] ?? "";
  if (terminal) value = value.slice(0, -terminal.length);
  const latex = looksLikeAutoMath(value) ? legacyExpressionToLatex(value) : null;
  if (latex != null) {
    result.push({ kind: "math", value: latex, source: value, display: false });
  } else {
    const comparison = COMPARISON_OPERATOR.exec(value);
    if (comparison?.index != null && comparison.index > 0) {
      const lhs = value.slice(0, comparison.index);
      const rhs = value.slice(comparison.index + comparison[0].length);
      const rhsLatex = legacyExpressionToLatex(rhs);
      if (hasProseLikeComparisonLabel(value) && rhsLatex != null) {
        const rhsLeading = rhs.match(/^\s*/u)?.[0] ?? "";
        const rhsTrailing = rhs.match(/\s*$/u)?.[0] ?? "";
        const rhsSource = rhs.slice(rhsLeading.length, rhs.length - rhsTrailing.length);
        appendText(result, lhs + comparison[0] + rhsLeading);
        result.push({ kind: "math", value: rhsLatex, source: rhsSource, display: false });
        appendText(result, rhsTrailing);
      } else appendText(result, value);
    } else {
      const wordGaps = [...value.matchAll(/\s+/gu)];
      const suffix = wordGaps
        .map((match) => ({
          prefix: value.slice(0, (match.index ?? 0) + match[0].length),
          value: value.slice((match.index ?? 0) + match[0].length),
        }))
        .find((part) => looksLikeAutoMath(part.value) && legacyExpressionToLatex(part.value) != null);
      if (suffix) {
        const suffixLatex = legacyExpressionToLatex(suffix.value);
        appendText(result, suffix.prefix);
        result.push({ kind: "math", value: suffixLatex!, source: suffix.value, display: false });
        appendText(result, terminal + trailing);
        return result;
      }
      appendText(result, value);
    }
  }
  appendText(result, terminal + trailing);
  return result;
}

function segmentLegacyText(value: string) {
  const segments: WorkbookMathSegment[] = [];
  let cursor = 0;
  for (const match of value.matchAll(SYMBOLIC_RUN)) {
    const index = match.index ?? 0;
    appendText(segments, value.slice(cursor, index));
    appendSegments(segments, segmentCandidate(match[0]));
    cursor = index + match[0].length;
  }
  appendText(segments, value.slice(cursor));
  return segments;
}

function segmentPlainWorkbookText(value: string) {
  const segments: WorkbookMathSegment[] = [];
  const hasComparison = value.includes("=");
  const mixed = hasComparison && /[가-힣]/u.test(value)
    ? segmentMixedKoreanEquations(value)
    : [{ kind: "text", value } satisfies WorkbookTextSegment];
  for (const segment of mixed) {
    if (segment.kind === "math") segments.push(segment);
    else {
      const relations = hasComparison
        ? [{ kind: "text", value: segment.value } satisfies WorkbookTextSegment]
        : segmentMixedKoreanRelations(segment.value);
      for (const relation of relations) {
        if (relation.kind === "math") segments.push(relation);
        else appendSegments(segments, segmentLegacyText(relation.value));
      }
    }
  }
  return segments;
}

/**
 * Split mixed workbook copy into native text and safe LaTeX spans.
 *
 * Explicit `$...$`, `$$...$$`, `\\(...\\)`, and `\\[...\\]` spans take priority.
 * Malformed delimiters and legacy expressions are never truncated: callers can render `source`
 * whenever KaTeX rejects a validated segment.
 */
export function segmentWorkbookMath(value: string): WorkbookMathSegment[] {
  if (value.includes("finance_interview_app_final_spec.md:")) {
    return [{ kind: "text", value }];
  }
  const segments: WorkbookMathSegment[] = [];
  let plainStart = 0;
  let index = 0;
  while (index < value.length) {
    const delimiter = explicitDelimiterAt(value, index);
    if (!delimiter) {
      index += 1;
      continue;
    }
    const closeIndex = findClosingDelimiter(value, delimiter.close, index + delimiter.open.length);
    const content = closeIndex < 0
      ? ""
      : value.slice(index + delimiter.open.length, closeIndex);
    const inlineSpacingInvalid = !delimiter.display && content !== content.trim();
    if (closeIndex < 0 || !content.trim() || inlineSpacingInvalid) {
      index += delimiter.open.length;
      continue;
    }

    appendSegments(segments, segmentPlainWorkbookText(value.slice(plainStart, index)));
    const source = value.slice(index, closeIndex + delimiter.close.length);
    segments.push({
      kind: "math",
      value: content.trim(),
      source,
      // FinDone's content contract uses same-line $$...$$ for inline math and only
      // delimiter-only multiline pairs for display math.
      display: delimiter.display === "auto" ? /\r?\n/u.test(content) : delimiter.display,
    });
    index = closeIndex + delimiter.close.length;
    plainStart = index;
  }
  appendSegments(segments, segmentPlainWorkbookText(value.slice(plainStart)));
  return segments;
}
