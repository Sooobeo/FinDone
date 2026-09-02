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
const SYMBOLIC_RUN = /[A-Za-z0-9_αβγδμρσλΔΣΠ∑∂()\[\]{}+\-−–—×÷*/^%.,=≈≤≥<>²√±& \t]+/gu;
const SINGLE_SYMBOL = /^[A-Za-zαβγδμρσλΔΣΠ][A-Za-z0-9_αβγδμρσλΔΣΠ]*$/u;
const PARENTHESIZED_SINGLE_SYMBOL = /^\([A-Za-zαβγδμρσλΔΣΠ∑∂][A-Za-z0-9_αβγδμρσλΔΣΠ∑∂]*\)$/u;
const COMPARISON_OPERATOR = /≤|≥|≈|<=|>=|=|<|>/u;
const PROSE_LHS_TOKEN_GAP = /[A-Za-z0-9_αβγδμρσλΔΣ]\s+[A-Za-z0-9_αβγδμρσλΔΣ]/u;
const PROSE_HYPHENATED_LABEL = /[A-Za-z]{2,}[-–—][A-Za-z]{2,}/u;
const REPEATED_TEX_SCRIPT = /(?:_(?:\{[^{}]*\}|[A-Za-z0-9])){2}|(?:\^(?:\{[^{}]*\}|[A-Za-z0-9])){2}/u;
const ROOT_BASE_TOKEN = /^(?:[A-Za-z][A-Za-z0-9]*|[αβγδμρσλΔΣΠ])/u;
const SCRIPT_TOKEN = /^(?:[A-Z]+[0-9]*(?![a-z])|[A-Z][a-z0-9]*|[a-z][a-z0-9]*|[0-9]+)/u;
const STRONG_MATH_SIGNAL = /[=+×÷*/^%≈≤≥<>²√ΣΠ∑∂±&]/u;
const EDGE_OPERATOR = /([=+-−–—×÷*/^≈≤≥<>]+)$/u;
const LATEX_FUNCTIONS = new Set(["max", "min", "ln", "log"]);

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
    .replace(/(\d)x(?=\d|\()/gu, "$1×")
    .replace(/sqrt\s*\(/gu, "√(")
    .replace(/([Σ∑])_\(([^()]+)\)/gu, "$1_{$2}")
    .replace(/_​?\(([A-Za-z][A-Za-z0-9]*)\)/gu, "_$1")
    .replace(/\^\(\(([+-−]?[A-Za-z0-9]+)\)\)/gu, "^$1")
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
  const comparison = COMPARISON_OPERATOR.exec(value);
  if (comparison?.index === 0 && comparison[0] !== "=") return false;
  if (value.includes("**") || value.includes("__")) return false;
  if (hasProseLikeComparisonLabel(value) || hasUnsafeTopLevelPunctuation(value)) return false;
  const rooted = replaceSquareRoots(canonical);
  if (rooted == null) return false;
  const scripted = braceMulticharScripts(rooted);
  if (scripted == null || REPEATED_TEX_SCRIPT.test(scripted)) return false;
  return STRONG_MATH_SIGNAL.test(value)
    || /\d/u.test(value)
    || SINGLE_SYMBOL.test(value)
    || PARENTHESIZED_SINGLE_SYMBOL.test(value);
}

/** Convert a reviewed workbook's legacy pseudo-math to validated KaTeX input. */
export function legacyExpressionToLatex(value: string): string | null {
  const canonical = canonicalSymbolicSource(value.trim());
  if (!isSafeSymbolicExpression(canonical)) return null;
  const rooted = replaceSquareRoots(canonical);
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

function splitTopLevelCandidate(value: string) {
  const stack: string[] = [];
  const pairs: Record<string, string> = { ")": "(", "]": "[", "}": "{" };
  let segmentStart = 0;
  const parts: string[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if ("([{".includes(character)) stack.push(character);
    else if (pairs[character]) {
      if (stack.at(-1) !== pairs[character]) return [value];
      stack.pop();
    } else if (stack.length === 0 && character === "," && !isDigitGroupingComma(value, index)) {
      const before = value.slice(segmentStart, index);
      const after = value.slice(index + 1);
      if (COMPARISON_OPERATOR.test(before) && COMPARISON_OPERATOR.test(after)) {
        parts.push(before, character);
        segmentStart = index + 1;
      }
    } else if (
      stack.length === 0
      && ".!?。".includes(character)
      && !isDecimalPoint(value, index)
      && value.slice(index + 1).trim()
      && COMPARISON_OPERATOR.test(value.slice(segmentStart, index))
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

  const terminal = value.match(/[.!?。]+$/u)?.[0] ?? "";
  if (terminal) value = value.slice(0, -terminal.length);
  const hasSignal = STRONG_MATH_SIGNAL.test(canonicalSymbolicSource(value))
    || PARENTHESIZED_SINGLE_SYMBOL.test(value);

  const latex = hasSignal ? legacyExpressionToLatex(value) : null;
  if (latex != null) {
    result.push({ kind: "math", value: latex, source: value, display: false });
  } else {
    const comparison = COMPARISON_OPERATOR.exec(value);
    if (comparison?.index != null && comparison.index > 0) {
      const lhs = value.slice(0, comparison.index);
      const rhs = value.slice(comparison.index + comparison[0].length);
      const rhsLatex = legacyExpressionToLatex(rhs);
      if (hasProseLikeComparisonLabel(value) && rhsLatex != null) {
        appendText(result, lhs + comparison[0]);
        result.push({ kind: "math", value: rhsLatex, source: rhs, display: false });
      } else appendText(result, value);
    } else {
      const edge = value.match(EDGE_OPERATOR);
      const atom = edge ? value.slice(0, -edge[0].length) : "";
      const atomLatex = atom && (SINGLE_SYMBOL.test(atom) || PARENTHESIZED_SINGLE_SYMBOL.test(atom))
        ? legacyExpressionToLatex(atom)
        : null;
      if (edge && atomLatex != null) {
        result.push({ kind: "math", value: atomLatex, source: atom, display: false });
        appendText(result, edge[0]);
      } else appendText(result, value);
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

/**
 * Split mixed workbook copy into native text and safe LaTeX spans.
 *
 * Explicit `$...$`, `$$...$$`, `\\(...\\)`, and `\\[...\\]` spans take priority.
 * Malformed delimiters and legacy expressions are never truncated: callers can render `source`
 * whenever KaTeX rejects a validated segment.
 */
export function segmentWorkbookMath(value: string): WorkbookMathSegment[] {
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

    appendSegments(segments, segmentLegacyText(value.slice(plainStart, index)));
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
  appendSegments(segments, segmentLegacyText(value.slice(plainStart)));
  return segments;
}
