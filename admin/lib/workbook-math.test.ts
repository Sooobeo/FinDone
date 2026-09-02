import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { WorkbookMathText } from "@/components/workbook-math-text";
import { renderWorkbookLatex } from "@/lib/workbook-katex";
import { mergeWorkbookMathSeams } from "@/lib/workbook-math-seams";
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
    expect(numeric[0].value).toBe("9{,}400-4{,}100=5{,}300\\text{만원}");
  });

  it("covers reviewed workbook pseudo-math variants", () => {
    const sentenceFormula = mathSegments(
      "조정 순부채를 뺀다. 5,200+300-450=5,050만원이다.",
    );
    expect(sentenceFormula.map((segment) => segment.source)).toContain(
      "5,200+300-450=5,050만원",
    );

    const negativeExponent = mathSegments("PV=C[1-(1+r)^((-n))]/r");
    expect(negativeExponent).toHaveLength(1);
    expect(negativeExponent[0].value).toContain("^{-n}");

    const deltaSubtraction = mathSegments("Project FCF = OCF-Capex-Δ NWC");
    expect(deltaSubtraction).toHaveLength(1);
    expect(deltaSubtraction[0].source).toBe("OCF-Capex-Δ NWC");
    expect(deltaSubtraction[0].value).toContain("\\Delta");

    expect(mathSegments("• NWC=유동자산-유동부채."))
      .toMatchObject([{
        source: "NWC=유동자산-유동부채",
        value: "\\mathrm{NWC}=\\text{유동자산}-\\text{유동부채}",
      }]);

    const numbered = mathSegments(
      "1) EBIT=1,200-700-100=400백만원이다. "
        + "2) OCF=400×(1-0.25)+100=300+100=400백만원이다. "
        + "3) FCF=400-150-40=210백만원이다.",
    );
    expect(numbered.map((segment) => segment.source)).toEqual([
      "EBIT=1,200-700-100=400백만원",
      "OCF=400×(1-0.25)+100=300+100=400백만원",
      "FCF=400-150-40=210백만원",
    ]);

    const wacc = mathSegments(
      "판단기준·공식 WACC = E/V×Re + P/V×Rp + D/V×Rd×(1-세율), V=E+P+D.",
    );
    expect(wacc.map((segment) => segment.source)).toEqual([
      "WACC = E/V×Re + P/V×Rp + D/V×Rd×(1-세율), V=E+P+D",
    ]);
    expect(wacc[0].value).toContain("\\text{세율}");
    for (const segment of wacc) {
      expect(renderWorkbookLatex(segment.value, false)).not.toBeNull();
    }

    expect(mathSegments("- peak/trough")).toEqual([]);

    const commaTerminated = segmentWorkbookMath("PV=C1/(r-g), 다음 값을 구한다.");
    expect(mathSegments("PV=C1/(r-g), 다음 값을 구한다.")).toMatchObject([
      { source: "PV=C1/(r-g)" },
    ]);
    expect(commaTerminated).toContainEqual({ kind: "text", value: ", 다음 값을 구한다." });
  });

  it("renders mixed Korean variables and corpus boundary cases", () => {
    const eps = mathSegments(
      "기본 EPS=(당기순이익-우선주배당)/가중평균 유통보통주식수.",
    );
    expect(eps).toMatchObject([{
      source: "EPS=(당기순이익-우선주배당)/가중평균 유통보통주식수",
    }]);
    expect(eps[0].value).toContain("\\text{가중평균 유통보통주식수}");

    expect(mathSegments(
      "ROE=(순이익/매출)×(매출/자산)×(자산/자기자본).",
    )).toHaveLength(1);
    expect(mathSegments(
      "확장옵션 payoff = max(확장 후 추가가치-확장비용, 0).",
    )).toHaveLength(1);
    expect(mathSegments(
      "초기수익률 = (첫날 종가 - 공모가)/공모가이며 이후 안정된다.",
    )).toHaveLength(1);

    const swap = mathSegments(
      "Net=N×(L_prev-K)×d/B(고정금리 수취자 기준 부호는 반대).",
    );
    expect(swap).toMatchObject([{ source: "Net=N×(L_prev-K)×d/B" }]);

    const fx = mathSegments("1,270원/USD-1,320원/USD=-50원/USD이다.");
    expect(fx).toHaveLength(1);
    expect(fx[0].value).toContain("\\text{원}");

    for (const source of ["√36=6%p", "20%/√25=4%", "√0.0125=11.18%"]) {
      const formulas = mathSegments(source);
      expect(formulas).toHaveLength(1);
      expect(formulas[0].value).toContain("\\sqrt{");
    }

    expect(mathSegments(", R=10%이면").map((segment) => segment.source)).toContain("R=10%");
    expect(mathSegments("100, u=1.2, d=0.8").map((segment) => segment.source)).toEqual([
      "u=1.2",
      "d=0.8",
    ]);
    expect(mathSegments("100+10×2.4869=124.87, EAC를 계산한다.")
      .map((segment) => segment.source)).toContain("100+10×2.4869=124.87");
    expect(mathSegments("결과는 정수 %로 정확하다")).toEqual([]);

    expect(mathSegments("13.5억원/1.08 = 12.5억원")).toHaveLength(1);
    expect(mathSegments("840만원/120,000주=주당 70원")).toHaveLength(1);
    expect(mathSegments("σ _p^(2)=w_A^2σ_A^2")).toHaveLength(1);
    expect(mathSegments(
      "옵션가치 = [q 곱하기 상승옵션가치 + (1-q) 곱하기 하락옵션가치] 나누기 (1+r)",
    )).toHaveLength(1);
    expect(mathSegments("(4 곱하기 10,000 + 8,000)/5 = 9,600원이다."))
      .toHaveLength(1);

    expect(mathSegments("손익·자산/부채·현금흐름")).toEqual([]);
    expect(mathSegments("원/달러 환율")).toEqual([]);
    expect(mathSegments("1,300원/달러")).toEqual([]);
    expect(mathSegments("법인세율×D")).toEqual([]);
    expect(mathSegments("÷0.5만원/건=3,000건으로 계산한다.")).toEqual([]);

    expect(mathSegments(
      "할인포기비용은 할인율/(1-할인율) 곱하기 365/(최종지급일-할인기한)으로 근사한다.",
    ).map((segment) => segment.source)).toEqual([
      "할인율/(1-할인율) 곱하기 365/(최종지급일-할인기한)",
    ]);
    expect(mathSegments(
      "선도환율/현물환율은 대략 (1+국내금리)/(1+해외금리)이며 기준을 유지한다.",
    ).map((segment) => segment.source)).toEqual([
      "(1+국내금리)/(1+해외금리)",
    ]);

    const tailedEquations = [
      ["자산=부채+자기자본이 성립한다.", "자산=부채+자기자본"],
      ["NPV는 -10+18.18=8.18로 투자 가능하다.", "-10+18.18=8.18"],
      ["비율=12.60개로 더 높다.", "비율=12.60개"],
      ["수익률=10%보다 낮다.", "수익률=10%"],
      ["가치=100 적용 가정은 별도 명시한다.", "가치=100"],
    ] as const;
    for (const [source, expected] of tailedEquations) {
      expect(mathSegments(source).map((segment) => segment.source)).toEqual([expected]);
      expect(restoredSource(source)).toBe(source);
    }

    const commaEquations = mathSegments("u=1.2, d=0.8, 무위험수익률 5%이다.");
    expect(commaEquations[0].source).toBe("u=1.2, d=0.8");
    expect(commaEquations[0].source).not.toContain("무위험수익률");

    for (const source of [
      "자산=부채+자본",
      "OCF=EBIT(1-T)+감가상각",
      "EPS=(EBIT-이자)/유통주식수",
    ]) {
      const formulas = mathSegments(source);
      expect(formulas).toHaveLength(1);
      expect(formulas[0].source).not.toMatch(/[+\-−–—×÷*/^]$/u);
    }
    expect(mathSegments("=(취득원가-잔존가치)/내용연수")).toEqual([]);
    expect(mathSegments("=5,300-4,500-700+200=300만원")).toEqual([]);

    for (const source of [
      "기말충당금=기초충당금+당기대손상각비-상각채권 회수액이다.",
      "현금이자=액면금액×표면이자율.",
      "자산현금흐름=영업현금흐름-순자본지출-순운전자본증가.",
      "보유기간수익률=(기말가격-기초가격+현금흐름)/기초가격.",
    ]) {
      const formulas = mathSegments(source);
      expect(formulas).toHaveLength(1);
      expect(formulas[0].value).toContain("\\text{");
      expect(renderWorkbookLatex(formulas[0].value, false)).not.toBeNull();
      expect(restoredSource(source)).toBe(source);
    }

    expect(mathSegments(
      "판단기준·공식 할인포기비용은 할인율/(1-할인율) 곱하기 365/(최종지급일-할인기한)으로 근사한다.",
    ).map((segment) => segment.source)).toEqual([
      "할인율/(1-할인율) 곱하기 365/(최종지급일-할인기한)",
    ]);
    expect(mathSegments(
      "판단기준·공식 선도환율/현물환율은 대략 (1+국내금리)/(1+해외금리)이며 기준통화 표시를 일관되게 유지한다.",
    ).map((segment) => segment.source)).toEqual([
      "(1+국내금리)/(1+해외금리)",
    ]);

    for (const source of [
      "적용 가정은 - 현금흐름의 시점과 위험을 일관되게 맞춘다.",
      "적용 가정은 - 기업가치를 같은 기준으로 비교한다.",
      "같은 pre/post-lease 기준으로 비교한다.",
      "지니는 의미 - 회계적 선택과 경제적 실질을 구분한다.",
      "예상 환율은 약 1,326원/달러다.",
    ]) {
      expect(mathSegments(source), source).toEqual([]);
    }
    expect(mathSegments("이 값에 (1+r)을 곱한다.").map((segment) => segment.source))
      .toEqual(["(1+r)"]);
    expect(mathSegments(
      "사용 가능한 보험료는 기초 선급 240+당기 지급 960=기말 선급+비용이다.",
    ).map((segment) => segment.source)).toEqual([
      "기초 선급 240+당기 지급 960=기말 선급+비용",
    ]);

    const completeSpacedEquations = [
      [
        "충당금 흐름은 기초 120+당기 설정 140-대손확정 80=180만원이다.",
        "기초 120+당기 설정 140-대손확정 80=180만원",
      ],
      [
        "처분손익은 매각대금 1,650-처분시 장부가 1,400=250만원이다.",
        "매각대금 1,650-처분시 장부가 1,400=250만원",
      ],
      [
        "기말현금은 기초 500+증가 800=1,300만원이다.",
        "기초 500+증가 800=1,300만원",
      ],
      [
        "요구수익률은 배당수익률 5%+성장률 3%=8%이다.",
        "배당수익률 5%+성장률 3%=8%",
      ],
      [
        "매출은 4억원/천 대 × 75천 대 = 300억원이다.",
        "4억원/천 대 × 75천 대 = 300억원",
      ],
      [
        "ROE는 총순이익 360억원÷평균 자기자본 2,400억원=15.0%이다.",
        "총순이익 360억원÷평균 자기자본 2,400억원=15.0%",
      ],
      [
        "희석주식수는 1,000만 주+80만 주+20만 주=1,100만 주다.",
        "1,000만 주+80만 주+20만 주=1,100만 주",
      ],
      [
        "성장률은 재투자율 40%×증분 ROIC 15%=0.40×0.15=0.06이다.",
        "재투자율 40%×증분 ROIC 15%=0.40×0.15=0.06",
      ],
      [
        "가격변동률 1차 근사는 -수정듀레이션×수익률 변화=-5×0.0035=-0.0175=-1.75%이다.",
        "-수정듀레이션×수익률 변화=-5×0.0035=-0.0175=-1.75%",
      ],
      [
        "LTV는 담보대출 650억원÷부동산 가치 1,000억원=65%이다.",
        "담보대출 650억원÷부동산 가치 1,000억원=65%",
      ],
      [
        "DSCR은 NOI 90억원÷연간 원리금상환액 60억원=1.50배이다.",
        "NOI 90억원÷연간 원리금상환액 60억원=1.50배",
      ],
      [
        "자산가치는 NOI÷cap rate=60억원÷0.06=1,000억원이다.",
        "NOI÷cap rate=60억원÷0.06=1,000억원",
      ],
      [
        "가치 스프레드는 ROIC 12%-WACC 9%=+3%p다.",
        "ROIC 12%-WACC 9%=+3%p",
      ],
      [
        "12%-CAPM 기대수익률 12%=0%p이다.",
        "12%-CAPM 기대수익률 12%=0%p",
      ],
    ] as const;
    for (const [source, expected] of completeSpacedEquations) {
      expect(mathSegments(source).map((segment) => segment.source), source).toEqual([expected]);
      expect(restoredSource(source)).toBe(source);
    }
    expect(mathSegments(
      "순현금흐름은 EBIT의 10%인 10-이자 2.5=7.5다.",
    ).map((segment) => segment.source)).toContain("10-이자 2.5=7.5");
    expect(mathSegments("주+200만 주=500만 주이다.")).toEqual([]);

    const completeKoreanTerms = [
      [
        "특별주문 증분이익 = 주문매출-추가 변동비-추가 고정비-기존 판매 포기 공헌이익.",
        "증분이익 = 주문매출-추가 변동비-추가 고정비-기존 판매 포기 공헌이익",
      ],
      [
        "분할 후 이론주가 = 분할 전 주가 나누기 분할배수이고,",
        "이론주가 = 분할 전 주가 나누기 분할배수",
      ],
      [
        "옵션 매도 순이익 = 받은 프리미엄 - 매수자의 만기 행사이익이다.",
        "순이익 = 받은 프리미엄 - 매수자의 만기 행사이익",
      ],
      [
        "영업권 = 인수대가 + 비지배지분 등 조정 - 취득한 식별가능 순자산의 공정가치다.",
        "영업권 = 인수대가 + 비지배지분 등 조정 - 취득한 식별가능 순자산의 공정가치",
      ],
    ] as const;
    for (const [source, expected] of completeKoreanTerms) {
      expect(mathSegments(source).map((segment) => segment.source), source).toEqual([expected]);
      expect(restoredSource(source)).toBe(source);
    }
    expect(mathSegments(
      "repo 이자 I=Cash×r×days/B, B=360 또는 365; 재매입가격 RP=Cash+I.",
    ).map((segment) => segment.source)).toEqual([
      "I=Cash×r×days/B, B=360",
      "RP=Cash+I",
    ]);
    expect(mathSegments(
      "미결제수표는 뺀다. 5,200+300-450=5,050만원이다.",
    ).map((segment) => segment.source)).toEqual([
      "5,200+300-450=5,050만원",
    ]);
    expect(mathSegments(
      "50주와 이자 30을 가진다. 세금이 없을 때 EBIT/100=(EBIT-30)/50을 풀면 EBIT=60이다.",
    ).map((segment) => segment.source)).toEqual([
      "EBIT/100=(EBIT-30)/50",
      "EBIT=60",
    ]);
    expect(mathSegments(
      "기하평균 = [(1+r1)(1+r2)...(1+rn)]^(1/n)-1.",
    ).map((segment) => segment.source)).toEqual([
      "기하평균 = [(1+r1)(1+r2)...(1+rn)]^(1/n)-1",
    ]);
    const proseBoundaryEquations = [
      ["예제 100을 연 8%로 3년 복리운용하면 100×1.08^3=125.97이다.", "100×1.08^3=125.97"],
      ["연간 기대보상은 단순 금액 기준 700×12%=84다.", "700×12%=84"],
      [
        "단순화한 conversion-factor-adjusted basis Basis=P_cash-F_futures×CF.",
        "Basis=P_cash-F_futures×CF",
      ],
      ["두 자산이면 w × D_1+(1-w) × D_2=D_L.", "w × D_1+(1-w) × D_2=D_L"],
      ["비율 계산은 소수로 하면 0.02÷0.10=0.20이다.", "0.02÷0.10=0.20"],
      ["즉 C-P=S_0-PV(K).", "C-P=S_0-PV(K)"],
      ["연복리 기준 (1+s_2)^2=(1+s_1)(1+f_(1,2)).", "(1+s_2)^2=(1+s_1)(1+f_(1,2))"],
      ["결제일 기준 Net=N×(L_prev-K)×d/B.", "Net=N×(L_prev-K)×d/B"],
    ] as const;
    for (const [source, expected] of proseBoundaryEquations) {
      expect(mathSegments(source).map((segment) => segment.source), source).toContain(expected);
      expect(restoredSource(source)).toBe(source);
    }
    expect(mathSegments(
      "균등상환액은 원금×r/[1-(1+r)^-t]로 구하고 매기 이자=기초잔액×r로 분해한다.",
    ).map((segment) => segment.source)).toContain("이자=기초잔액×r");
    expect(mathSegments(
      "5) 3,900억원÷1,100만 주=35,454.545…원이므로 반올림한다.",
    ).map((segment) => segment.source)).toEqual([
      "3,900억원÷1,100만 주=35,454.545",
    ]);
    expect(mathSegments(
      "/USD)=-100,000,000원이다. 3) 100,000,000원=1억원이므로 환산손실은 -1억원이다.",
    ).map((segment) => segment.source)).toContain("100,000,000원=1억원");
    expect(mathSegments("500백만원×(1-0.20)=400백만원").map((segment) => segment.source))
      .toEqual(["500백만원×(1-0.20)=400백만원"]);
    expect(mathSegments("max(900억원-650억원, 0)=250억원").map((segment) => segment.source))
      .toEqual(["max(900억원-650억원, 0)=250억원"]);
    for (const source of [
      "1,000x6%x90/360=15만원",
      "이자=원금x연이율x기간",
      "ROE=순이익률x총자산회전율x자기자본승수",
    ]) {
      const formulas = mathSegments(source);
      expect(formulas).toHaveLength(1);
      expect(formulas[0].value).not.toMatch(/(?:[)%\]가-힣])x(?=[0-9(가-힣])/u);
      expect(formulas[0].value).toContain("\\times");
    }
    for (const source of [
      "처분손익=매각대금-처분시 장부",
      "매출=현",
      "자기자본승수=평균자산/평",
    ]) {
      expect(mathSegments(source), source).toEqual([]);
    }
    expect(mathSegments(
      "21,400원-20,000원=1,400원/주이다.",
    ).map((segment) => segment.source)).toEqual([
      "21,400원-20,000원=1,400원/주",
    ]);
    expect(mathSegments(
      "확장과 신규를 제외해 (100-5-10)억원÷100억원=85%이다.",
    ).map((segment) => segment.source)).toEqual([
      "(100-5-10)억원÷100억원=85%",
    ]);
    expect(mathSegments(
      "1유로=1.10달러라면 1유로=1,430원이다.",
    ).map((segment) => segment.source)).toEqual([
      "1유로=1.10달러",
      "1유로=1,430원",
    ]);
    expect(mathSegments(
      "FV=PV×(1+r×t)의 단리식과 비교한다.",
    ).map((segment) => segment.source)).toEqual([
      "FV=PV×(1+r×t)",
    ]);
    for (const source of [
      "발생주의 매출=현금회수+기말 매출채권-기",
      "성장영구연금 현재가치는 24억원÷0.06=400억원이",
      "핵심 관계는 CommonEquityValue=OperatingEV-Debt-OtherDebtLi",
    ]) {
      expect(mathSegments(source), source).toEqual([]);
    }
    const causalBoundaries = [
      ["1기간 투자이므로 2,400만원×(1+IRR)=2,760만원이다.", "2,400만원×(1+IRR)=2,760만원"],
      [
        "회사 유입금액은 신주 대금만 포함하므로 40,000원/주×3,000,000주=120,000,000,000원이다.",
        "40,000원/주×3,000,000주=120,000,000,000원",
      ],
      [
        "판단기준·공식 1+명목수익률 = (1+실질수익률)×(1+인플레이션율).",
        "1+명목수익률 = (1+실질수익률)×(1+인플레이션율)",
      ],
      ["D/E가 0.8로 늘면 0.9×1.6=1.44가 되어 위험이 커진다.", "0.9×1.6=1.44"],
      ["현재가치는 5/5%=100으로, 세율×부채와 같다.", "5/5%=100"],
    ] as const;
    for (const [source, expected] of causalBoundaries) {
      expect(mathSegments(source).map((segment) => segment.source), source).toContain(expected);
      expect(restoredSource(source)).toBe(source);
    }

    const discourseBoundaries = [
      [
        "변경일 장부가에서 새 잔존가치를 뺀 900-100=800만원을 앞으로 남은 2년에 배분한다.",
        "900-100=800만원",
      ],
      [
        "무배당 유럽형 옵션에서 C+PV(K)=P+S_0, 즉 C-P=S_0-PV(K).",
        "C+PV(K)=P+S_0",
      ],
    ] as const;
    for (const [source, expected] of discourseBoundaries) {
      expect(mathSegments(source).map((segment) => segment.source), source).toContain(expected);
      expect(restoredSource(source)).toBe(source);
    }
    expect(mathSegments(
      "순조정액은 +3,000원-2,000원=+1,000원/주이다.",
    ).map((segment) => segment.source)).toEqual([
      "+3,000원-2,000원=+1,000원/주",
    ]);
    expect(mathSegments("+400억원=100억원")).toEqual([]);
    expect(mathSegments("깨진식=x_")).toEqual([]);
  });

  it("keeps Korean native while typesetting adjacent symbolic atoms", () => {
    const source = "자산(A)=부채(L)+자본(E).";
    const formulas = mathSegments(source);
    expect(formulas.map((segment) => segment.source)).toEqual([
      "자산(A)=부채(L)+자본(E)",
    ]);
    expect(formulas[0].value).toContain("\\text{자산}");
    expect(restoredSource(source)).toBe(source);
  });

  it("does not mistake source breadcrumbs or currency for formulas", () => {
    const breadcrumb = "자료 (ACC) > ACC-01. 원문 finance_interview_app_final_spec.md:L1063";
    expect(mathSegments(breadcrumb)).toEqual([]);
    expect(mathSegments("확장 요소 (EQV-20 약 64) > F.3.5 실무 메모")).toEqual([]);
    expect(mathSegments("자료 (IBT) > G 실무 메모")).toEqual([]);
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
    expect(renderWorkbookLatex("\\href{javascript:alert(1)}{x}", false)).toBeNull();
    expect(renderWorkbookLatex("\\url{https://example.com}", false)).toBeNull();
    expect(renderWorkbookLatex("\\includegraphics{x.png}", false)).toBeNull();
  });

  it("renders delimiter-only multiline input as one display formula", () => {
    const html = renderToStaticMarkup(createElement(WorkbookMathText, {
      source: "$$\nx+1\n$$",
    }));
    expect(html).toContain("workbook-math-display");
    expect(html).toContain("katex-display");
    expect(html).not.toContain("$$");
  });
});

describe("generated workbook corpus", () => {
  it("repairs only formula-bearing source seams before display", () => {
    const unitRoot = join(process.cwd(), "content", "workbook", "units");
    let repairedSeams = 0;
    const repairedSources: string[] = [];

    for (const fileName of readdirSync(unitRoot).filter((name) => name.endsWith(".json"))) {
      const unit = JSON.parse(readFileSync(join(unitRoot, fileName), "utf8")) as {
        theory: Array<{ kind: string; text: string }>;
        questions: Array<{
          solution: Array<{ labelled: boolean; text: string }>;
        }>;
      };
      const theory = mergeWorkbookMathSeams(
        unit.theory,
        (left, right) => left.kind === "body" && right.kind === "body",
      );
      repairedSeams += unit.theory.length - theory.length;
      repairedSources.push(...theory.map((block) => block.text));

      for (const question of unit.questions) {
        const solution = mergeWorkbookMathSeams(
          question.solution,
          (_left, right) => !right.labelled,
        );
        repairedSeams += question.solution.length - solution.length;
        repairedSources.push(...solution.map((segment) => segment.text));
      }
    }

    expect(repairedSeams).toBe(34);
    expect(repairedSources.some((source) => source.includes(
      "FD Shares=Basic+Incremental+RSU+Convertibles",
    ))).toBe(true);
    expect(repairedSources.some((source) => source.includes(
      "총 공모주식수는 300만 주+200만 주=500만 주",
    ))).toBe(true);
    expect(repairedSources.some((source) => source.includes(
      "순조정액은 +3,000원-2,000원=+1,000원/주",
    ))).toBe(true);

    for (const source of repairedSources) {
      expect(restoredSource(source), source).toBe(source);
      for (const formula of mathSegments(source)) {
        expect(renderWorkbookLatex(formula.value, formula.display), formula.source).not.toBeNull();
      }
    }

    for (const fragments of [
      ["합계는", "110만원+100만원=210만원이다."],
      ["핵심 관계는", "WACC=wE×ke+wD×kd×(1-T)."],
      ["CF_t=N(L_(t-1)-K)α_t,", "α_t=days/B."],
      ["ARR=Begin+New+Expansion-Contraction-Churn", "NRR=(Begin-Contraction-Churn)/Begin"],
    ]) {
      expect(mergeWorkbookMathSeams(
        fragments.map((text) => ({ text })),
        () => true,
      )).toHaveLength(2);
    }
  }, 30_000);

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
      for (const segment of mathSegments(source)) {
        expect(segment.source.trim()).not.toMatch(/[=+\-−–—×÷*/^]$/u);
        expect(segment.source.trim()).not.toMatch(/^[=+×÷*/^]/u);
        formulas.set(segment.value, segment.display);
      }
    }

    expect(formulas.size).toBeGreaterThan(500);
    for (const [latex, display] of formulas) {
      expect(renderWorkbookLatex(latex, display), latex).not.toBeNull();
      expect(latex).not.toContain("\\mathrm{sqrt}");
    }
  }, 30_000);
});
