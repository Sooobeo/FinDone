import {
  segmentWorkbookMath,
  type WorkbookMathSegment,
} from "@/lib/workbook-math";

interface MathRange {
  start: number;
  end: number;
}

interface MathCoverage {
  coverage: boolean[];
  ranges: MathRange[];
}

const RECOVERED_OPERATOR = /[=+\-−–—×÷*/^]/u;
const TERMINAL_BOUNDARY = /[,，.!?。;:]$/u;
const NUMERIC_TAIL = /\d[\d,]*(?:\.\d+)?$/u;
const NUMERIC_UNIT_CONTINUATION = /^(?:원|만원|억원|백만원|천만원|만\s*주|주|개|건|배|%)(?=[+\-−–—×÷*/^=])/u;
const ASCII_IDENTIFIER_TAIL = /[A-Z]{1,6}$/u;
const ASCII_IDENTIFIER_CONTINUATION = /^[A-Z][A-Za-z0-9_]*(?==)/u;

function segmentLength(segment: WorkbookMathSegment) {
  return segment.kind === "math" ? segment.source.length : segment.value.length;
}

function analyzeMathCoverage(source: string): MathCoverage | null {
  const coverage = Array.from<boolean>({ length: source.length }).fill(false);
  const ranges: MathRange[] = [];
  let offset = 0;

  for (const segment of segmentWorkbookMath(source)) {
    const length = segmentLength(segment);
    if (segment.kind === "math") {
      coverage.fill(true, offset, offset + length);
      ranges.push({ start: offset, end: offset + length });
    }
    offset += length;
  }

  return offset === source.length ? { coverage, ranges } : null;
}

function isNumericUnitSeam(left: string, right: string) {
  return NUMERIC_TAIL.test(left) && NUMERIC_UNIT_CONTINUATION.test(right);
}

function isAsciiIdentifierSeam(left: string, right: string) {
  return ASCII_IDENTIFIER_TAIL.test(left) && ASCII_IDENTIFIER_CONTINUATION.test(right);
}

function isSignedLabelSeam(left: string, right: string) {
  return /(?:은|는)$/u.test(left)
    && /^\+(?=\d)[\s\S]*=\s*\+(?=\d)/u.test(right);
}

function repairableMathSeam(left: string, right: string) {
  if (
    !left
    || !right
    || /\s$/u.test(left)
    || /^\s/u.test(right)
    || TERMINAL_BOUNDARY.test(left)
  ) return false;
  if (isSignedLabelSeam(left, right)) {
    const repaired = analyzeMathCoverage(`${left} ${right}`);
    const formulaStart = left.length + 1;
    return repaired?.ranges.some((range) => (
      range.start === formulaStart && range.end > formulaStart
    )) ?? false;
  }

  const leftCoverage = analyzeMathCoverage(left);
  const rightCoverage = analyzeMathCoverage(right);
  const joinedSource = left + right;
  const joinedCoverage = analyzeMathCoverage(joinedSource);
  if (!leftCoverage || !rightCoverage || !joinedCoverage) return false;

  const seam = left.length;
  const oldCoverage = [...leftCoverage.coverage, ...rightCoverage.coverage];
  for (const range of joinedCoverage.ranges) {
    const crossesSeam = range.start < seam && range.end > seam;
    const repairsSplitCopula = left.endsWith("이")
      && /^다(?:[.!?。]|$)/u.test(right)
      && range.end === seam - 1;
    if (!crossesSeam && !repairsSplitCopula) continue;

    const recoveredIndexes: number[] = [];
    for (let index = range.start; index < range.end; index += 1) {
      if (!oldCoverage[index]) recoveredIndexes.push(index);
    }
    if (!recoveredIndexes.length) continue;
    if (recoveredIndexes.some((index) => RECOVERED_OPERATOR.test(joinedSource[index]))) {
      return true;
    }
    if (isNumericUnitSeam(left, right) || isAsciiIdentifierSeam(left, right)) {
      return true;
    }
  }
  return false;
}

function repairedSeamSeparator(left: string, right: string) {
  if (isAsciiIdentifierSeam(left, right)) return " ";
  if (/\d만$/u.test(left) && /^주(?=[+\-−–—×÷*/^=])/u.test(right)) return " ";
  if (isSignedLabelSeam(left, right)) return " ";
  return "";
}

/**
 * Rejoin source-generator fragments only when doing so recovers a formula that
 * spans the seam. The first item owns the merged run's semantic presentation.
 */
export function mergeWorkbookMathSeams<T extends { text: string }>(
  items: readonly T[],
  canJoin: (left: T, right: T) => boolean,
) {
  const merged: T[] = [];
  for (const item of items) {
    const left = merged.at(-1);
    if (left && canJoin(left, item) && repairableMathSeam(left.text, item.text)) {
      merged[merged.length - 1] = {
        ...left,
        text: left.text + repairedSeamSeparator(left.text, item.text) + item.text,
      };
    } else {
      merged.push(item);
    }
  }
  return merged;
}
