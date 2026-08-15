#!/usr/bin/env python3
"""Generate a complete v3.1 question preview and an exception-only review queue.

The generator consumes the selected offline v3 ranker but publishes nothing.
All artifacts are restricted to ``docs/modeling`` and ``build``.  Admin,
Supabase, the checked-in question bank, and Android assets are never written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np

from tools import experiment_concept_question_model_v3 as experiment
from tools import train_concept_question_model as base


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "modeling" / "previews"
DEFAULT_SELECTED_EXPERIMENT = (
    ROOT
    / "docs"
    / "modeling"
    / "experiments"
    / "cmq-v3-20260813-075147-6a618c72.json"
)
DEFAULT_RAW_ELEMENTS = ROOT / "admin" / "data" / "content-elements.generated.json"
CHOICE_KEYS = ("A", "B", "C", "D", "E")
REFERENCE_DESIGN_PATH = ROOT / "docs" / "modeling" / "CONCEPT_MCQ_MODELING_DESIGN.md"

# The design reference requires one explicit overlap anchor and one explicit
# distinguishing axis on each side (sections 5.1-5.3 and 11.2).  Corpus
# specificity is descriptive evidence used for ordering, not an extra pass/fail
# threshold: the 75th-percentile document frequency is recorded in every run so
# reviewers can see which shared anchors are unusually common.
REFERENCE_GATE_POLICY_ID = "cmq-v3.1-reference-hard-gates-v1"
ANCHOR_DOCUMENT_FREQUENCY_PERCENTILE = 0.75
REFERENCE_GATE_THRESHOLDS: dict[str, int] = {
    "questionCount": 540,
    "questionsPerElement": 4,
    "choiceCount": 5,
    "answerCount": 1,
    "generalTargetFactCount": 1,
    "generalCrossConceptFactCount": 2,
    "generalTargetMutationCount": 2,
    "inverseTargetFactCount": 4,
    "inverseTargetMutationCount": 1,
    "minimumSharedAnchorCount": 1,
    "minimumTargetDistinctAxisCount": 1,
    "minimumCandidateDistinctAxisCount": 1,
    "mutationChangedSpanCount": 1,
    "minimumRelationParticipantCount": 2,
    "minimumRelationEdgeCount": 1,
    "maximumRelationMutationChangedBindingOrEdgeCount": 1,
    "maximumConceptNameExposureCount": 0,
    "maximumFormulaExposureCount": 0,
    "maximumDuplicateChoiceTextCount": 0,
}

SOFT_REVIEW_CRITERIA: dict[str, str] = {
    "definition-insufficient-source-evidence": (
        "정의형 타개념의 대상 또는 후보에서 검토된 정의 종결 술어를 추출하지 못함"
    ),
    "common-anchor-only": (
        "선택된 타개념과 공유한 앵커의 최소 문서빈도가 코퍼스 75백분위보다 큼"
    ),
    "no-displayed-fact-anchor-overlap": (
        "요소 전체 출처에는 공유 앵커가 있으나 실제 화면의 두 설명 문장에서는 명시 앵커가 겹치지 않음"
    ),
}

# These are source-backed audit signals, not release gates.  Section 12.1 of
# the design makes sentence-core overlap a ranking feature; the corpus-derived
# 75th percentile identifies unusually common overlap without inventing a
# target review rate.
SOFT_REVIEW_FORMULAS: dict[str, str] = {
    "definition-insufficient-source-evidence": (
        "definitionRoleCompatibility.reasonId == 'insufficient-source-evidence'"
    ),
    "common-anchor-only": (
        "minimumSharedAnchorDocumentFrequency > anchorCorpus.documentFrequencyP75"
    ),
    "no-displayed-fact-anchor-overlap": "displayedSharedAnchorCount == 0",
}

# Additional explicit ending predicates are used only for post-ranking audit.
# They do not change the candidate pool or the selected v3 experiment model.
AUDIT_DEFINITION_ROLE_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "method_or_process",
        "audit-definition-ends-with-explanatory-predicate",
        re.compile(r"(?:설명한다|세분한다|나눈다|정한다|명시한다|근사한다)\.?$"),
    ),
    (
        "quantitative_measure",
        "audit-definition-ends-with-quantitative-object-predicate",
        re.compile(r"(?:비중이다|측정해 .+ 본다|정도다|추가 수익률이다)\.?$"),
    ),
    (
        "financial_entity",
        "audit-definition-ends-with-financial-content-predicate",
        re.compile(r"(?:포함하지 않는다|담는다)\.?$"),
    ),
    (
        "method_or_process",
        "audit-definition-ends-with-analysis-observation-predicate",
        re.compile(r"(?:분석은|분석이).*(?:함께 )?본다\.?$"),
    ),
    (
        "quantitative_measure",
        "audit-definition-ends-with-measure-observation-predicate",
        re.compile(r"(?:수익률|비율|지표|규모|수익성).*(?:본다|나타낸다)\.?$"),
    ),
    (
        "quantitative_measure",
        "audit-definition-ends-with-banking-profitability-predicate",
        re.compile(r"(?:nim|ppnr|영업수익성)을 본다\.?$", re.IGNORECASE),
    ),
)


@dataclass(frozen=True)
class AnchorRule:
    anchor_id: str
    label: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class MutationRule:
    rule_id: str
    category: str
    before: str
    after: str
    rationale: str
    auto_safe: bool = True


# This is a reviewed vocabulary of financial subjects, roles, and situations.
# An anchor is emitted only when one of its expressions occurs in source text;
# domain and model similarity alone never create an anchor.
ANCHOR_RULES: tuple[AnchorRule, ...] = (
    AnchorRule("accounting_record", "회계 기록·인식", (r"회계", r"인식", r"분개", r"결산")),
    AnchorRule("financial_statements", "재무제표 연결", (r"재무제표", r"손익계산서", r"재무상태표", r"현금흐름표")),
    AnchorRule("assets", "자산", (r"자산", r"asset")),
    AnchorRule("liabilities_debt", "부채·채무", (r"부채", r"채무", r"차입", r"debt")),
    AnchorRule("equity_shareholders", "자본·주주", (r"자기자본", r"자본", r"주주", r"equity")),
    AnchorRule("cash", "현금", (r"현금", r"cash")),
    AnchorRule("revenue_sales", "매출·수익", (r"매출", r"수익(?!률)", r"revenue", r"sales")),
    AnchorRule("cost_expense", "원가·비용", (r"원가", r"비용", r"expense", r"cogs")),
    AnchorRule("profit_earnings", "이익·성과", (r"이익", r"손익", r"성과", r"earnings?", r"ebit")),
    AnchorRule("receivables_credit", "외상채권·신용", (r"매출채권", r"외상", r"미수", r"신용")),
    AnchorRule("inventory", "재고", (r"재고", r"inventory")),
    AnchorRule("fixed_assets_capex", "설비·투자자산", (r"설비", r"유형자산", r"감가상각", r"capex")),
    AnchorRule("working_capital", "운전자본", (r"운전자본", r"nwc", r"매입채무")),
    AnchorRule("cash_flow", "현금흐름", (r"현금흐름", r"cash\s*flow", r"fcf", r"fcff", r"fcfe")),
    AnchorRule("tax", "세금", (r"세금", r"세율", r"법인세", r"tax", r"nol")),
    AnchorRule("interest", "이자", (r"이자", r"interest")),
    AnchorRule("time_value", "화폐의 시간·기준시점", (r"현재가치", r"미래가치", r"기준시점", r"시간가치", r"pv", r"fv")),
    AnchorRule("discount_rate", "할인율·요구수익률", (r"할인율", r"요구수익률", r"자본비용", r"wacc")),
    AnchorRule("growth", "성장", (r"성장", r"증가율", r"growth")),
    AnchorRule("investment_decision", "투자안·의사결정", (r"투자안", r"프로젝트", r"초기투자", r"npv", r"irr")),
    AnchorRule("dividend_distribution", "배당·주주환원", (r"배당", r"자사주", r"주주환원", r"dividend")),
    AnchorRule("risk", "위험", (r"위험", r"리스크", r"risk")),
    AnchorRule("market_systematic_risk", "시장위험·베타", (r"시장위험", r"베타", r"beta", r"체계적")),
    AnchorRule("capital_structure", "자본구조·조달", (r"자본구조", r"조달", r"레버리지", r"debt", r"equity")),
    AnchorRule("enterprise_equity_value", "기업가치·지분가치", (r"기업가치", r"지분가치", r"주당가치", r"enterprise\s*value", r"marketcap")),
    AnchorRule("valuation", "가치평가", (r"가치평가", r"가치", r"valuation", r"dcf", r"목표가")),
    AnchorRule("terminal_value", "계속가치·안정기", (r"계속가치", r"terminal", r"안정기", r"명시적 예측")),
    AnchorRule("returns", "수익률", (r"수익률", r"return", r"tsr")),
    AnchorRule("volatility_dispersion", "변동성·분산", (r"변동성", r"분산", r"표준편차", r"volatility")),
    AnchorRule("correlation_diversification", "상관·분산투자", (r"상관", r"공분산", r"분산투자", r"correlation")),
    AnchorRule("portfolio", "포트폴리오", (r"포트폴리오", r"portfolio")),
    AnchorRule("factor_model", "요인모형", (r"위험요인", r"공통요인", r"apt", r"capm", r"알파")),
    AnchorRule("performance_benchmark", "성과평가·벤치마크", (r"성과평가", r"벤치마크", r"sharpe", r"treynor", r"jensen", r"information\s*ratio")),
    AnchorRule("bond_fixed_income", "채권·고정수익", (r"채권", r"사채", r"국채", r"회사채", r"bond")),
    AnchorRule("yield_rates", "금리·수익률곡선", (r"금리", r"이자율", r"수익률곡선", r"ytm", r"yield")),
    AnchorRule("term_structure_forward", "기간구조·선도금리", (r"현물이자율", r"선도금리", r"기간구조", r"forward\s*rate")),
    AnchorRule("duration", "듀레이션", (r"duration", r"듀레이션", r"가중평균 시점")),
    AnchorRule("convexity_dv01", "금리민감도·곡률", (r"convexity", r"dv01", r"가격민감도", r"곡률")),
    AnchorRule("hedging", "헤지", (r"헤지", r"hedg", r"immunization", r"면역")),
    AnchorRule("collateral_repo", "담보·레포", (r"담보", r"repo", r"레포", r"haircut")),
    AnchorRule("futures_forward", "선물·선도", (r"선물", r"선도", r"futures?", r"forward")),
    AnchorRule("basis_delivery", "베이시스·인도", (r"basis", r"베이시스", r"ctd", r"인도")),
    AnchorRule("swap", "스왑", (r"스왑", r"swap", r"고정 이자", r"변동 이자")),
    AnchorRule("credit_loss_spread", "신용손실·스프레드", (r"신용위험", r"신용스프레드", r"expected\s*loss", r"기대손실", r"부도")),
    AnchorRule("derivatives_options", "파생상품·옵션", (r"파생", r"옵션", r"콜", r"풋", r"option")),
    AnchorRule("arbitrage_pricing", "무차익·이론가격", (r"무차익", r"차익거래", r"이론가격", r"parity")),
    AnchorRule("option_payoff", "옵션 권리·손익", (r"행사가격", r"payoff", r"프리미엄", r"손익분기")),
    AnchorRule("option_models", "옵션 평가모형", (r"binomial", r"black", r"scholes", r"이항", r"위험중립")),
    AnchorRule("greeks_sensitivity", "그릭스·민감도", (r"greeks?", r"delta", r"gamma", r"vega", r"theta", r"민감도")),
    AnchorRule("price_volume", "가격·물량", (r"가격", r"물량", r"판매수량", r"p.?q")),
    AnchorRule("margin", "마진", (r"마진", r"margin")),
    AnchorRule("eps_dilution", "주당이익·희석", (r"eps", r"주당", r"희석", r"주식수")),
    AnchorRule("multiples", "가치평가 배수", (r"배수", r"multiple", r"per", r"pbr", r"ev/ebitda")),
    AnchorRule("scenario_sensitivity", "시나리오·민감도", (r"시나리오", r"민감도", r"sensitivity", r"bull", r"bear")),
    AnchorRule("saas_retention", "반복매출·고객유지", (r"arr", r"nrr", r"grr", r"반복매출", r"고객 유지")),
    AnchorRule("unit_economics", "단위경제성", (r"cac", r"ltv", r"단위경제", r"회수기간", r"공헌이익")),
    AnchorRule("operations_capacity", "영업량·가동률", (r"가동률", r"손익분기", r"점포", r"gmv", r"take\s*rate")),
    AnchorRule("orders_backlog", "수주·주문잔고", (r"수주", r"주문잔고", r"backlog", r"book.?to.?bill")),
    AnchorRule("accrual_conversion", "발생액·현금전환", (r"발생액", r"현금전환", r"회전일수", r"billings", r"계약자산", r"계약부채")),
    AnchorRule("research_investment", "연구개발·자본화", (r"r&d", r"연구개발", r"자본화")),
    AnchorRule("lease_pension", "리스·연금 의무", (r"리스", r"연금", r"퇴직급여")),
    AnchorRule("goodwill_acquisition", "영업권·인수", (r"영업권", r"인수", r"m&a", r"시너지")),
    AnchorRule("roic_capital_efficiency", "투하자본수익성", (r"roic", r"투하자본", r"nopat", r"자본수익")),
    AnchorRule("roe_dupont", "자기자본수익성·듀퐁", (r"roe", r"dupont", r"자기자본수익")),
    AnchorRule("economic_profit", "경제적 이익·가치스프레드", (r"eva", r"가치 스프레드", r"경제적 이익")),
    AnchorRule("rollforward_bridge", "롤포워드·브리지", (r"롤포워드", r"bridge", r"브리지", r"연결 과정")),
    AnchorRule("banking", "은행 수익·자본", (r"은행", r"nim", r"ppnr", r"cet1", r"예금")),
    AnchorRule("insurance", "보험 손익·자본", (r"보험", r"손해율", r"합산비율", r"csm", r"지급여력")),
    AnchorRule("commodities_resources", "원자재·자원", (r"원자재", r"매장량", r"자원기업", r"nav")),
    AnchorRule("catalyst_surprise", "촉매·실적 괴리", (r"촉매", r"서프라이즈", r"추정치", r"실적 괴리")),
    AnchorRule("liquidity_downside", "유동성·하방위험", (r"유동성", r"런웨이", r"하방", r"covenant")),
    AnchorRule("inflation_real_nominal", "물가·명목실질", (r"물가", r"인플레이션", r"명목", r"실질")),
    AnchorRule("foreign_exchange", "환율·외화", (r"환율", r"외화", r"fx", r"달러", r"원화")),
    AnchorRule("ipo_equity_issuance", "기업공개·신주", (r"ipo", r"공모", r"신주", r"구주", r"주식교환")),
    AnchorRule("real_estate", "부동산 영업가치", (r"부동산", r"noi", r"cap\s*rate", r"임대")),
    AnchorRule("debt_capacity", "부채상환능력", (r"ltv", r"dscr", r"담보대출", r"부채상환")),
)


def _mutation_pairs(
    rule_id: str,
    category: str,
    left: str,
    right: str,
    rationale: str,
    auto_safe: bool = True,
) -> tuple[MutationRule, MutationRule]:
    return (
        MutationRule(
            f"{rule_id}-forward", category, left, right, rationale, auto_safe
        ),
        MutationRule(
            f"{rule_id}-reverse", category, right, left, rationale, auto_safe
        ),
    )


MUTATION_RULES: tuple[MutationRule, ...] = tuple(
    rule
    for pair in (
        _mutation_pairs("increase-decrease", "direction_reverse", "증가", "감소", "증가와 감소 방향을 뒤바꿨다."),
        _mutation_pairs("rise-fall", "direction_reverse", "상승", "하락", "상승과 하락 방향을 뒤바꿨다."),
        _mutation_pairs("grow-shrink", "direction_reverse", "늘어난", "줄어든", "증감 방향을 뒤바꿨다."),
        _mutation_pairs("grow-shrink-da", "direction_reverse", "늘어난다", "줄어든다", "증감 방향을 뒤바꿨다."),
        _mutation_pairs("grow-shrink-go", "direction_reverse", "늘고", "줄고", "증감 방향을 뒤바꿨다."),
        _mutation_pairs("grow-shrink-myeon", "direction_reverse", "늘면", "줄면", "조건의 증감 방향을 뒤바꿨다."),
        _mutation_pairs("grow-shrink-surok", "direction_reverse", "늘수록", "줄수록", "조건과 결과의 방향을 뒤바꿨다."),
        _mutation_pairs("large-small", "direction_reverse", "커진다", "작아진다", "크기 변화 방향을 뒤바꿨다."),
        _mutation_pairs("large-small-myeon", "direction_reverse", "크면", "작으면", "비교 조건의 방향을 뒤바꿨다."),
        _mutation_pairs("high-low", "direction_reverse", "높아진다", "낮아진다", "높고 낮아지는 방향을 뒤바꿨다."),
        _mutation_pairs("high-low-myeon", "direction_reverse", "높으면", "낮으면", "높고 낮은 조건을 뒤바꿨다."),
        _mutation_pairs("high-low-adj", "direction_reverse", "높은", "낮은", "높고 낮은 속성을 뒤바꿨다."),
        _mutation_pairs("fast-slow", "direction_reverse", "빠르게", "느리게", "속도 방향을 뒤바꿨다."),
        _mutation_pairs("long-short", "scope_swap", "길어진다", "짧아진다", "기간의 길고 짧음을 뒤바꿨다."),
        _mutation_pairs("same-opposite", "relation_reverse", "같은 방향", "반대 방향", "두 대상의 동행 방향을 뒤바꿨다."),
        _mutation_pairs("positive-negative", "sign_reverse", "양수", "음수", "부호를 뒤바꿨다."),
        _mutation_pairs("add-subtract", "bridge_adjustment_swap", "더한다", "뺀다", "브리지 조정의 가감 방향을 뒤바꿨다."),
        _mutation_pairs("add-subtract-hae", "bridge_adjustment_swap", "더해", "빼", "브리지 조정의 가감 방향을 뒤바꿨다.", False),
        _mutation_pairs("include-exclude", "inclusion_boundary_swap", "포함한다", "제외한다", "포함 경계를 뒤바꿨다."),
        _mutation_pairs("include-exclude-doe", "inclusion_boundary_swap", "포함되고", "제외되고", "포함 경계를 뒤바꿨다."),
        _mutation_pairs("market-book", "basis_swap", "시장가치", "장부가치", "측정 기준을 시장가치와 장부가치 사이에서 바꿨다."),
        _mutation_pairs("fair-book", "basis_swap", "공정가치", "장부가치", "측정 기준을 공정가치와 장부가치 사이에서 바꿨다."),
        _mutation_pairs("pretax-aftertax", "basis_swap", "세전", "세후", "세금 전후 기준을 바꿨다."),
        _mutation_pairs("nominal-real", "basis_swap", "명목", "실질", "명목과 실질 기준을 바꿨다."),
        _mutation_pairs("fixed-floating", "role_swap", "고정", "변동", "고정과 변동 역할을 바꿨다.", False),
        _mutation_pairs("begin-end", "timing_swap", "기초", "기말", "기준 시점을 바꿨다.", False),
        _mutation_pairs("past-future", "timing_swap", "과거", "미래", "기준 기간을 바꿨다."),
        _mutation_pairs("before-after", "timing_swap", "이전", "이후", "절차의 전후 시점을 바꿨다."),
        _mutation_pairs("shareholder-creditor", "role_swap", "주주", "채권자", "경제적 귀속 주체를 바꿨다.", False),
        _mutation_pairs("equity-debt", "role_swap", "자기자본", "부채", "자금 제공자의 역할을 바꿨다.", False),
        _mutation_pairs("asset-liability", "classification_swap", "자산", "부채", "재무상태표 분류를 바꿨다.", False),
        _mutation_pairs("revenue-expense", "classification_swap", "수익", "비용", "손익의 성격을 바꿨다.", False),
        _mutation_pairs("profit-cash", "recognition_cash_swap", "이익", "현금", "회계 성과와 현금을 바꿨다.", False),
        _mutation_pairs("inflow-outflow", "direction_reverse", "유입", "유출", "현금흐름 방향을 바꿨다."),
        _mutation_pairs("borrow-repay", "role_swap", "차입", "상환", "자금조달과 상환을 바꿨다.", False),
        _mutation_pairs("issue-repay", "role_swap", "발행", "상환", "발행과 상환을 바꿨다.", False),
        _mutation_pairs("buy-sell", "position_swap", "매수", "매도", "거래 포지션을 바꿨다."),
        _mutation_pairs("call-put", "option_role_swap", "콜", "풋", "옵션 권리의 종류를 바꿨다."),
        _mutation_pairs("spot-futures", "instrument_swap", "현물", "선물", "현물과 선물의 역할을 바꿨다."),
        _mutation_pairs("principal-interest", "cashflow_role_swap", "원금", "이자", "현금흐름의 원금과 이자 역할을 바꿨다.", False),
        _mutation_pairs("price-volume", "driver_swap", "가격", "수량", "매출 변화의 가격과 수량 역할을 바꿨다.", False),
        _mutation_pairs("numerator-denominator", "ratio_role_swap", "분자", "분모", "비율의 분자와 분모 역할을 바꿨다."),
        _mutation_pairs("operating-financing", "cashflow_classification_swap", "영업", "재무", "현금흐름 활동 분류를 바꿨다."),
        _mutation_pairs("company-shareholders", "scope_swap", "기업 전체", "보통주주", "가치나 현금흐름의 귀속 범위를 바꿨다."),
        _mutation_pairs("all-common-equity", "scope_swap", "모든 자본 제공자", "보통주주", "현금흐름의 귀속 범위를 바꿨다."),
        _mutation_pairs("actual-expected", "basis_swap", "실제", "예상", "실제값과 예상값의 기준을 바꿨다.", False),
        _mutation_pairs("gross-net", "scope_swap", "총액", "순액", "총액과 순액의 범위를 바꿨다."),
        _mutation_pairs("before-after-interest", "scope_swap", "이자 지급 전", "이자 지급 후", "이자 지급 전후의 귀속 범위를 바꿨다."),
    )
    for rule in pair
)


# Complete-phrase mutations supplement the morphological rules above.  These
# replacements preserve particles and conjugation, so they can pass without a
# language-model grammar guess.  Each still changes only one source assertion.
PHRASE_MUTATION_RULES: tuple[MutationRule, ...] = tuple(
    rule
    for pair in (
        _mutation_pairs("receivable-estimate-realized", "timing_swap", "회수하지 못할 것으로 예상되는 금액", "이미 회수한 금액", "예상 손실과 이미 회수한 금액을 바꿨다."),
        _mutation_pairs("sold-remaining", "inclusion_boundary_swap", "판매된 부분", "남은 부분", "판매분과 잔존분의 역할을 바꿨다."),
        _mutation_pairs("ending-beginning-inventory", "timing_swap", "기말재고", "기초재고", "재고의 기준 시점을 기말에서 기초로 바꿨다."),
        _mutation_pairs("use-acquisition-period", "timing_swap", "사용기간에", "취득한 날에", "비용 배분 기간을 취득일로 바꿨다."),
        _mutation_pairs("late-early-payment", "timing_swap", "늦게 지급", "일찍 지급", "지급 시점을 뒤바꿨다."),
        _mutation_pairs("different-same-time", "timing_swap", "서로 다른 시점", "서로 같은 시점", "비교하는 시점의 범위를 바꿨다."),
        _mutation_pairs("low-high-condition", "condition_reverse", "할인율보다 낮아야", "할인율보다 높아야", "유한가치의 성장률 조건을 뒤바꿨다."),
        _mutation_pairs("present-future-value", "timing_swap", "현재가치", "미래가치", "가치를 옮기는 기준시점을 바꿨다."),
        _mutation_pairs("fixed-floating-legs", "role_swap", "고정 다리와 변동 다리", "고정 다리와 고정 다리", "스왑의 두 이자 다리 중 변동 역할을 고정 역할로 바꿨다."),
        _mutation_pairs("floating-rate-fixing-payment-order", "sequence_swap", "기간 시작에 확정되어 기간 말에 지급", "기간 말에 확정되어 기간 시작에 지급", "변동금리의 확정 시점과 지급 시점 순서를 바꿨다."),
        _mutation_pairs("swap-net-gross-settlement", "settlement_scope_swap", "각각 교환하지 않고 차액만 결제", "차액을 상계하지 않고 양쪽 총액을 각각 결제", "스왑 현금흐름의 순액 결제를 총액 결제로 바꿨다."),
        _mutation_pairs("market-idiosyncratic", "risk_scope_swap", "시장 전체", "개별 기업", "분산할 수 없는 위험의 범위를 바꿨다."),
        _mutation_pairs("selected-already-spent", "decision_scope_swap", "투자안을 선택했기 때문에 새로", "투자안을 선택하기 전에 이미", "증분성과 매몰비용의 범위를 바꿨다."),
        _mutation_pairs("forecast-end-start", "timing_swap", "예측 종료시점", "예측 시작시점", "계속가치의 기준시점을 바꿨다."),
        _mutation_pairs("simple-compound-average", "aggregation_swap", "단순 평균", "복리 평균", "기간 수익률의 집계 방식을 바꿨다."),
        _mutation_pairs("wide-narrow-dispersion", "direction_reverse", "넓게 흩어질수록", "좁게 모일수록", "분산과 위험의 관계 방향을 바꿨다."),
        _mutation_pairs("market-idiosyncratic-risk", "risk_scope_swap", "시장위험", "고유위험", "성과평가의 위험 범위를 바꿨다."),
        _mutation_pairs("equal-different-path", "equivalence_reverse", "같아야 한다", "달라야 한다", "무차익 경로의 등가 조건을 뒤바꿨다."),
        _mutation_pairs("premium-strike", "cashflow_role_swap", "프리미엄", "행사가격", "옵션 원가와 행사가격의 역할을 바꿨다.", False),
        _mutation_pairs("option-payoff-premium-exclusion", "inclusion_boundary_swap", "최초 프리미엄은 포함하지 않는다", "최초 프리미엄까지 포함한다", "옵션 payoff의 최초 프리미엄 포함 여부를 바꿨다."),
        _mutation_pairs("call-put-payoff-directions", "option_role_swap", "살 권리는 시장가격이 약정가격보다 높을 때, 팔 권리는 시장가격이 약정가격보다 낮을 때", "살 권리는 시장가격이 약정가격보다 낮을 때, 팔 권리는 시장가격이 약정가격보다 높을 때", "콜과 풋의 만기 가치 발생 조건을 서로 바꿨다."),
        _mutation_pairs("call-payoff-condition-only", "direction_reverse", "살 권리는 시장가격이 약정가격보다 높을 때", "살 권리는 시장가격이 약정가격보다 낮을 때", "살 권리의 만기 가치 발생 조건만 뒤집었다."),
        _mutation_pairs("option-maturity-spot-price", "timing_swap", "만기 기초자산가격", "계약시점 기초자산가격", "옵션 payoff의 기초자산 가격 시점을 바꿨다."),
        _mutation_pairs("option-profit-premium-exclusion", "inclusion_boundary_swap", "프리미엄까지 반영한 최종 손익", "프리미엄을 제외한 만기 손익", "옵션 최종 손익에서 최초 프리미엄 포함 여부를 바꿨다."),
        _mutation_pairs("sales-price-volume", "driver_swap", "판매단가", "판매량", "매출의 가격과 물량 동인을 바꿨다."),
        _mutation_pairs("share-price-enterprise-value", "scope_swap", "현재 주가", "현재 기업가치", "지분 단위 가치와 기업 전체 가치를 바꿨다."),
        _mutation_pairs("per-sales", "denominator_swap", "주당이익", "주당매출", "가치평가 배수의 기준 이익을 매출로 바꿨다."),
        _mutation_pairs("accretion-share-count-ignore", "inclusion_boundary_swap", "새 주식수를 반영한", "새 주식수를 제외한", "인수 후 주당이익에서 신주 분모 효과를 제외했다."),
        _mutation_pairs("peer-target", "comparison_role_swap", "비교기업", "목표기업", "배수를 제공하는 기업과 적용받는 기업을 바꿨다.", False),
        _mutation_pairs("peer-multiple-target-metric", "comparison_role_swap", "비교기업의 시장 배수를 목표기업 지표에 적용", "목표기업의 시장 배수를 비교기업 지표에 적용", "상대가치 평가에서 배수 제공자와 적용 대상을 바꿨다."),
        _mutation_pairs("relative-valuation-market-book-basis", "basis_swap", "시장기준의 내재가치", "과거 장부기준의 내재가치", "상대가치 평가의 비교 기준을 시장에서 과거 장부로 바꿨다."),
        _mutation_pairs("same-different-basis", "basis_swap", "같은 기준", "서로 다른 기준", "비교 기준의 일관성을 뒤바꿨다."),
        _mutation_pairs("organic-fx-growth", "driver_swap", "유기적 성장", "환율 효과", "본업 성장과 외부 환산효과를 바꿨다."),
        _mutation_pairs("existing-acquired-business", "scope_swap", "기존 사업", "인수한 사업", "동일 기준 성장의 사업 범위를 바꿨다."),
        _mutation_pairs("new-existing", "scope_swap", "신규", "기존", "신규와 기존 범위를 바꿨다."),
        _mutation_pairs("expansion-contraction", "direction_reverse", "확장", "축소", "고객 매출의 확장과 축소 방향을 바꿨다."),
        _mutation_pairs("churn-acquisition", "flow_swap", "이탈", "신규 유입", "고객 이탈과 신규 유입을 바꿨다."),
        _mutation_pairs("service-billing-first", "sequence_swap", "서비스를 먼저 제공", "고객에게 먼저 청구", "서비스 제공과 청구 순서를 바꿨다."),
        _mutation_pairs("new-existing-investment", "scope_swap", "신규투자", "기존투자", "증분 수익성의 투자 범위를 바꿨다."),
        _mutation_pairs("reinvestment-payout", "capital_allocation_swap", "재투자율", "배당성향", "성장 재원과 환원 비율을 바꿨다."),
        _mutation_pairs("year-round-year-end", "timing_swap", "연중 발생", "연말에만 발생", "현금 발생 시점을 바꿨다."),
        _mutation_pairs("valuation-date-same-year-start", "timing_swap", "가치평가일이 회계연도 시작과 다르다는", "가치평가일이 항상 회계연도 시작과 같다는", "가치평가일과 회계연도 시작의 시점 관계를 바꿨다."),
        _mutation_pairs("continuing-value-compress-cash", "valuation_role_swap", "장기 현금을 한 값으로 압축", "과거 장부가를 한 값으로 압축", "계속가치가 압축하는 대상을 장기 현금에서 과거 장부가로 바꿨다."),
        _mutation_pairs("one-all-input", "scope_swap", "한 입력만", "모든 입력을", "민감도 분석의 변경 범위를 바꿨다."),
        _mutation_pairs("one-consistent-path", "scope_swap", "여러 일관된 미래 경로", "서로 무관한 입력 조합", "시나리오의 일관성 조건을 바꿨다."),
        _mutation_pairs("oneoff-persistent", "persistence_swap", "일회성", "지속적", "실적 괴리의 지속성을 바꿨다."),
        _mutation_pairs("foreign-domestic-currency", "currency_scope_swap", "외화로 받을 금액", "원화로 받을 금액", "환산손익의 통화 범위를 바꿨다."),
        _mutation_pairs("target-acquirer", "transaction_role_swap", "목표회사", "인수회사", "주식교환의 거래 당사자 역할을 바꿨다."),
        _mutation_pairs("pre-post-money", "timing_scope_swap", "pre-money", "post-money", "공모 전후 가치 기준을 바꿨다."),
        _mutation_pairs("basic-diluted-shares", "scope_swap", "기본주식수", "희석주식수", "주식수의 희석 범위를 바꿨다."),
        _mutation_pairs("probability-impact", "risk_role_swap", "발생확률", "발생 시 충격", "위험의 확률과 충격 역할을 바꿨다."),
        _mutation_pairs("expected-realized-result", "basis_swap", "예상보다 달라진", "이미 확정된", "예상과 실제 결과의 기준을 바꿨다."),
        _mutation_pairs("lower-higher-surok", "direction_reverse", "낮을수록", "높을수록", "조건의 높고 낮은 방향을 뒤바꿨다."),
        _mutation_pairs("larger-smaller-surok", "direction_reverse", "커질수록", "작아질수록", "조건의 크기 방향을 뒤바꿨다."),
        _mutation_pairs("larger-smaller-even", "direction_reverse", "커져도", "작아져도", "조건의 크기 방향을 뒤바꿨다."),
        _mutation_pairs("more-less", "direction_reverse", "더 많은", "더 적은", "수량의 대소 방향을 뒤바꿨다."),
        _mutation_pairs("roic-cost-capital-value", "comparison_role_swap", "자본비용과 비교하면 투입한 1원이 가치를 만들었는지", "매출액과 비교하면 투입한 1원이 현금을 만들었는지", "자본수익성의 비교 기준을 자본비용에서 매출액으로 바꿨다."),
        _mutation_pairs("earlier-later", "timing_swap", "먼저", "나중에", "절차의 순서를 뒤바꿨다."),
        _mutation_pairs("before-after-period", "timing_swap", "이후", "이전", "기간의 전후를 뒤바꿨다."),
        _mutation_pairs("same-different-adjective", "relation_reverse", "같은", "다른", "동일성과 차이를 뒤바꿨다.", False),
        _mutation_pairs("different-same-adjective", "relation_reverse", "다른", "같은", "동일성과 차이를 뒤바꿨다.", False),
        _mutation_pairs("same-different-da", "relation_reverse", "같다", "다르다", "동일성과 차이를 뒤바꿨다.", False),
        _mutation_pairs("different-same-if", "relation_reverse", "다르면", "같으면", "비교 조건의 동일성을 뒤바꿨다.", False),
        _mutation_pairs("many-few", "direction_reverse", "많은", "적은", "수량의 많고 적음을 뒤바꿨다.", False),
        _mutation_pairs("many-few-adverb", "direction_reverse", "많이", "적게", "수량의 많고 적음을 뒤바꿨다.", False),
        _mutation_pairs("many-few-hae", "direction_reverse", "많아", "적어", "수량의 많고 적음을 뒤바꿨다.", False),
        _mutation_pairs("large-small-adverb", "direction_reverse", "크게", "작게", "변화 크기를 뒤바꿨다.", False),
        _mutation_pairs("large-small-adjective", "direction_reverse", "큰", "작은", "크기 속성을 뒤바꿨다.", False),
        _mutation_pairs("good-bad-adjective", "quality_reverse", "좋은", "나쁜", "질적 방향을 뒤바꿨다.", False),
        _mutation_pairs("good-bad-adverb", "quality_reverse", "좋게", "나쁘게", "질적 방향을 뒤바꿨다.", False),
        _mutation_pairs("long-short-if", "timing_swap", "길면", "짧으면", "기간 길이의 조건을 뒤바꿨다."),
        _mutation_pairs("long-short-adverb", "timing_swap", "오래", "짧게", "기간 길이를 뒤바꿨다."),
        _mutation_pairs("far-near-future", "timing_swap", "먼 미래", "가까운 미래", "미래 시점의 거리를 바꿨다."),
        _mutation_pairs("together-separate", "relation_reverse", "함께", "별도로", "대상의 결합 여부를 뒤바꿨다.", False),
        _mutation_pairs("direct-indirect", "relation_reverse", "직접", "간접적으로", "직접성과 간접성을 뒤바꿨다.", False),
        _mutation_pairs("consistent-conflicting", "consistency_reverse", "일관된", "서로 충돌하는", "입력 간 일관성을 뒤바꿨다."),
        _mutation_pairs("accurate-inaccurate", "quality_reverse", "정확히", "부정확하게", "측정의 정확성을 뒤바꿨다."),
        _mutation_pairs("annual-cash-flow-one-date", "timing_scope_swap", "각 연도의 매출·마진·재투자를 따로 예측", "모든 연도의 현금흐름을 한 시점에 발생한 것으로 가정", "연도별 현금흐름의 발생 시점을 하나로 합쳤다."),
        _mutation_pairs("first-later-order", "sequence_swap", "첫 번째", "두 번째", "순서상 역할을 바꿨다."),
        _mutation_pairs("company-owner-claim", "role_swap", "채권자 몫인 부채", "주주 몫인 부채", "부채의 경제적 귀속 주체를 바꿨다."),
        _mutation_pairs("equity-creditor-claim", "role_swap", "주주 몫인 자본", "채권자 몫인 자본", "자본의 경제적 귀속 주체를 바꿨다."),
        _mutation_pairs("cash-profit-subject", "recognition_cash_swap", "현금이", "이익이", "현금과 회계이익의 역할을 바꿨다.", False),
        _mutation_pairs("cash-profit-object", "recognition_cash_swap", "현금을", "이익을", "현금과 회계이익의 역할을 바꿨다.", False),
        _mutation_pairs("cash-profit-topic", "recognition_cash_swap", "현금은", "이익은", "현금과 회계이익의 역할을 바꿨다."),
        _mutation_pairs("cash-profit-flow", "recognition_cash_swap", "현금흐름", "회계이익", "현금흐름과 회계이익의 역할을 바꿨다."),
        _mutation_pairs("accrual-sale-cash-timing", "timing_swap", "대금을 1월에 받았다면, 매출은 현금을 받은 1월이 아니라 일을 끝낸 12월", "대금을 1월에 받았다면, 매출은 일을 끝낸 12월이 아니라 현금을 받은 1월", "발생주의 매출 인식 시점을 현금수취 시점으로 바꿨다."),
        _mutation_pairs("irr-boundary-below-required-return", "direction_reverse", "내재 수익 경계가 요구수익률보다 높으면", "내재 수익 경계가 요구수익률보다 낮으면", "투자 수익 경계와 요구수익률의 비교 방향을 바꿨다."),
        _mutation_pairs("asset-liability-genitive", "classification_swap", "자산의", "부채의", "자산과 부채의 분류를 바꿨다."),
        _mutation_pairs("asset-liability-object", "classification_swap", "자산을", "부채를", "자산과 부채의 분류를 바꿨다."),
        _mutation_pairs("asset-liability-subject", "classification_swap", "자산이", "부채가", "자산과 부채의 분류를 바꿨다."),
        _mutation_pairs("asset-liability-topic", "classification_swap", "자산은", "부채는", "자산과 부채의 분류를 바꿨다."),
        _mutation_pairs("revenue-expense-object", "classification_swap", "수익을", "비용을", "수익과 비용의 역할을 바꿨다."),
        _mutation_pairs("revenue-expense-topic", "classification_swap", "수익은", "비용은", "수익과 비용의 역할을 바꿨다."),
        _mutation_pairs("profit-cash-object", "recognition_cash_swap", "이익을", "현금을", "이익과 현금의 역할을 바꿨다."),
        _mutation_pairs("profit-cash-topic", "recognition_cash_swap", "이익은", "현금은", "이익과 현금의 역할을 바꿨다."),
        _mutation_pairs("issue-repay-past", "transaction_role_swap", "발행한", "상환한", "발행과 상환의 거래 역할을 바꿨다.", False),
        _mutation_pairs("issue-repay-after", "transaction_role_swap", "발행 뒤", "상환 뒤", "발행과 상환의 시점을 바꿨다."),
        _mutation_pairs("shareholder-creditor-subject", "role_swap", "주주가", "채권자가", "경제적 귀속 주체를 바꿨다."),
        _mutation_pairs("shareholder-creditor-dative", "role_swap", "주주에게", "채권자에게", "경제적 귀속 주체를 바꿨다."),
        _mutation_pairs("shareholder-creditor-genitive", "role_swap", "주주의", "채권자의", "경제적 귀속 주체를 바꿨다."),
        _mutation_pairs("higher-lower-than", "direction_reverse", "보다 높", "보다 낮", "비교 방향을 뒤바꿨다.", False),
        _mutation_pairs("larger-smaller-than", "direction_reverse", "보다 크", "보다 작", "비교 방향을 뒤바꿨다.", False),
        _mutation_pairs("more-less-than", "direction_reverse", "보다 많", "보다 적", "비교 방향을 뒤바꿨다.", False),
        _mutation_pairs("estimated-realized-loss", "timing_swap", "미리 반영", "회수한 뒤 반영", "예상 손실의 반영 시점을 바꿨다."),
        _mutation_pairs("effective-coupon-yield", "basis_swap", "실제 조달수익률", "표면이율", "사채 이자비용의 적용 수익률을 바꿨다."),
        _mutation_pairs("book-face-amount", "basis_swap", "장부금액에 적용", "액면금액에만 적용", "유효이자율의 적용 금액 기준을 바꿨다."),
        _mutation_pairs("profit-margin-debt-maturity", "driver_swap", "이익률", "부채 만기", "수익성 동인을 부채 만기로 바꿨다.", False),
        _mutation_pairs("asset-efficiency-debt-cost", "driver_swap", "자산 효율", "부채 비용", "자산 활용 동인을 부채 비용으로 바꿨다."),
        _mutation_pairs("one-separate-reference-time", "timing_swap", "하나의 기준시점", "각기 다른 시점", "가치 비교의 공통 기준시점을 없앴다."),
        _mutation_pairs("recurring-once-cashflow", "scope_swap", "반복 현금흐름", "한 번의 현금흐름", "반복 지급과 일시금을 바꿨다."),
        _mutation_pairs("npv-zero-maximum", "criterion_swap", "NPV를 0으로", "NPV를 가장 크게", "내부수익률의 정의 기준을 바꿨다."),
        _mutation_pairs("intrinsic-market-return", "criterion_swap", "투자 자체가 내재적으로 제공하는", "시장이 외부에서 요구하는", "투자 내재수익과 요구수익의 역할을 바꿨다."),
        _mutation_pairs("price-change-distribution", "return_component_swap", "가격변화", "현금분배", "수익률의 가격변화와 현금분배 역할을 바꿨다."),
        _mutation_pairs("one-multiple-period", "scope_swap", "한 기간", "여러 기간", "수익률 측정 기간의 범위를 바꿨다."),
        _mutation_pairs("center-maximum", "aggregation_swap", "결과의 중심", "결과의 최댓값", "분포의 중심과 극단값을 바꿨다."),
        _mutation_pairs("individual-market-asset", "risk_scope_swap", "개별 자산", "시장 전체", "민감도를 측정하는 자산 범위를 바꿨다."),
        _mutation_pairs("market-idiosyncratic-return", "risk_scope_swap", "시장 수익률", "고유위험", "베타의 비교 대상을 바꿨다."),
        _mutation_pairs("common-specific-factor", "risk_scope_swap", "공통 위험요인", "개별 기업 고유요인", "요인모형의 위험 범위를 바꿨다."),
        _mutation_pairs("recovery-average-price-sensitivity", "measure_role_swap", "가중평균 시점", "가격 민감도", "듀레이션의 시간과 민감도 역할을 바꿨다."),
        _mutation_pairs("default-probability-loss-rate", "risk_role_swap", "부도확률", "부도 후 손실률", "신용손실의 확률과 손실률 역할을 바꿨다."),
        _mutation_pairs("expected-loss-spread", "risk_role_swap", "평균 신용손실", "추가 수익률", "기대손실과 가격 보상의 역할을 바꿨다."),
        _mutation_pairs("maturity-contract-start", "timing_swap", "만기 payoff", "계약 체결 시점의 payoff", "옵션 손익의 측정 시점을 바꿨다."),
        _mutation_pairs("sales-assets-margin", "denominator_swap", "매출에서 원가", "자산에서 원가", "마진의 기준 분모를 매출에서 자산으로 바꿨다."),
        _mutation_pairs("cost-sga-role", "cost_role_swap", "원가와 판관비", "매출과 세금", "영업마진의 비용 구성요소를 바꿨다."),
        _mutation_pairs("sales-linked-fixed", "driver_swap", "성장에 따라", "매출과 관계없이", "운전자본의 매출 연동 조건을 바꿨다."),
        _mutation_pairs("net-income-ending-cash", "bridge_role_swap", "순이익에서", "기말현금에서", "재무제표 연결의 시작점과 종착점을 바꿨다."),
        _mutation_pairs("cash-bridge-ending-beginning", "timing_swap", "실제 기말현금이 나온다", "실제 기초현금이 나온다", "현금 브리지의 종착 시점을 기말에서 기초로 바꿨다."),
        _mutation_pairs("cash-bridge-investment-financing-exclusion", "inclusion_boundary_swap", "비현금항목·운전자본·투자·조달을 거쳐", "투자·조달을 제외하고", "기말현금 브리지에서 투자와 조달 활동을 제외했다."),
        _mutation_pairs("book-equity-sales-per-share", "denominator_swap", "주당 장부자본", "주당 매출", "PBR의 비교 기준을 장부자본에서 매출로 바꿨다."),
        _mutation_pairs("annual-fcff-accounting-profit", "cashflow_scope_swap", "연도별 FCFF", "연도별 회계이익", "DCF의 할인 대상을 현금흐름에서 회계이익으로 바꿨다."),
        _mutation_pairs("occurrence-terminal-discount", "timing_swap", "각 발생시점에서 현재로", "모두 예측 종료시점으로", "현금흐름 할인 기준시점을 바꿨다."),
        _mutation_pairs("stable-unstable-growth", "condition_reverse", "안정적으로 성장할", "일시적으로 변동할", "계속가치의 안정기 조건을 바꿨다."),
        _mutation_pairs("current-target-price", "role_swap", "현재 주가", "분석가의 목표가", "상승여력의 출발가격과 도착가격을 바꿨다."),
        _mutation_pairs("ev-equity-sensitivity", "scope_swap", "EV와 주당가치", "매출과 회계이익", "배수 민감도의 가치 대상을 바꿨다."),
        _mutation_pairs("segment-mix-common-cost", "driver_swap", "매출비중과 마진", "부채비중과 금리", "사업부 믹스의 영업 동인을 바꿨다."),
        _mutation_pairs("customer-cost-profit", "unit_economics_role_swap", "고객 한 명을 얻는 비용", "그 고객이 남길 이익", "획득비용과 고객가치 역할을 바꿨다."),
        _mutation_pairs("payback-sales-growth", "measure_role_swap", "투자금 회수 속도", "회사 전체 매출 성장률", "단위경제성의 회수 지표를 전사 성장률로 바꿨다."),
        _mutation_pairs("store-count-sales", "driver_swap", "점포 수와 점포당 매출", "점포당 매출과 점포 수", "점포 수와 점포당 매출의 역할을 바꿨다."),
        _mutation_pairs("traffic-ticket", "driver_swap", "트래픽·전환율·객단가", "객단가·전환율·트래픽", "점포 매출 동인의 역할 순서를 바꿨다."),
        _mutation_pairs("cash-invest-recover", "sequence_swap", "현금을 투입한 뒤 고객에게 회수", "고객에게 회수한 뒤 현금을 투입", "현금전환주기의 순서를 바꿨다."),
        _mutation_pairs("cash-cycle-days-money", "unit_scope_swap", "순기간을 일수로", "순기간을 금액으로", "현금전환주기의 측정 단위를 기간에서 금액으로 바꿨다."),
        _mutation_pairs("billing-revenue-recognition", "sequence_swap", "청구, 수익인식, 현금수취", "수익인식, 청구, 현금수취", "계약사업의 청구와 수익인식 순서를 바꿨다."),
        _mutation_pairs("contract-asset-liability", "classification_swap", "선이행 권리·선수 의무", "선수 의무·선이행 권리", "계약자산과 계약부채의 역할을 바꿨다."),
        _mutation_pairs("inventory-receivables", "asset_role_swap", "재고가 판매로 전환되는 속도", "매출채권이 현금으로 전환되는 속도", "재고와 매출채권의 회전 대상을 바꿨다."),
        _mutation_pairs("turnover-loss-buffer", "measure_role_swap", "판매로 전환되는 속도", "손실에 대비한 완충 수준", "회전속도와 손실완충 지표의 역할을 바꿨다."),
        _mutation_pairs("lease-debt-operating-payable", "classification_swap", "차입과 유사한 청구권", "일반 영업비용", "리스부채의 금융성 분류를 바꿨다."),
        _mutation_pairs("additional-existing-nopat", "scope_swap", "추가 NOPAT", "기존 전체 NOPAT", "증분 수익성의 이익 범위를 바꿨다."),
        _mutation_pairs("growth-discount-rate", "valuation_role_swap", "장기 성장률", "할인율", "계속가치의 성장과 할인 역할을 바꿨다."),
        _mutation_pairs("market-business-assumption", "reverse_dcf_role_swap", "시장가치를 출발점", "사업계획을 출발점", "역산 가치평가의 출발점을 바꿨다."),
        _mutation_pairs("credit-loss-profitability", "bank_role_swap", "신용손실 흡수", "유형자본 수익성", "은행 건전성과 수익성 역할을 바꿨다."),
        _mutation_pairs("claims-expense-premium", "insurance_role_swap", "보험료 중 사고손해와 사업비", "사고손해 중 보험료와 투자이익", "합산비율의 분자와 분모 역할을 바꿨다.", False),
        _mutation_pairs("insurance-premium-claims-expense-scope", "inclusion_boundary_swap", "사고손해와 사업비가 차지하는 비중", "투자이익 하나가 차지하는 비중", "보험영업 비율의 손해·사업비 범위를 투자이익으로 바꿨다."),
        _mutation_pairs("midcycle-spot-margin", "normalization_basis_swap", "중간주기 가격·마진", "현재 정점의 가격·마진", "정상화의 가격·마진 기준을 바꿨다."),
        _mutation_pairs("normalization-increase-distortion", "direction_reverse", "경기정점·저점의 왜곡을 줄인", "경기정점·저점의 왜곡을 키운", "정상화 이익의 경기순환 왜곡 방향을 뒤집었다."),
        _mutation_pairs("target-dividend-tsr", "return_component_swap", "목표가 변화와 예상 배당", "과거 주가와 이미 지급한 배당", "기대 총수익의 미래 구성요소를 과거값으로 바꿨다."),
        _mutation_pairs("unused-committed-liquidity", "liquidity_scope_swap", "현금·미사용한도", "매출·회계이익", "유동성 런웨이의 가용재원을 바꿨다."),
        _mutation_pairs("fx-constant-rate", "condition_reverse", "환율 변화 때문에", "환율이 고정돼도", "환산손익의 발생 조건을 바꿨다."),
        _mutation_pairs("government-corporate-bond", "credit_scope_swap", "국채금리가 같아도", "회사채 신용위험이 같아도", "신용스프레드 변화에서 고정하는 기준을 바꿨다."),
        _mutation_pairs("deal-value-stock-price", "transaction_scope_swap", "사업 전체 가치", "인수회사 주가", "거래가치 브리지의 출발 대상을 바꿨다."),
        _mutation_pairs("potential-effective-rent", "real_estate_scope_swap", "잠재 임대수입", "실제 현금잔액", "부동산 영업소득의 출발 수익을 바꿨다."),
        _mutation_pairs("noi-gross-rent", "real_estate_scope_swap", "연간 NOI", "연간 총임대료", "Cap rate 평가의 소득 기준을 바꿨다."),
        _mutation_pairs("property-debt-value-ltv", "ratio_role_swap", "담보 부동산가치 중 대출", "대출 중 담보 부동산가치", "LTV의 분자와 분모 역할을 바꿨다.", False),
        _mutation_pairs("ltv-equity-buffer-debt", "classification_swap", "자기자본 완충", "추가 부채 부담", "담보가격 하락을 흡수하는 자기자본 역할을 추가 부채로 바꿨다."),
        _mutation_pairs("noi-debt-service", "ratio_role_swap", "NOI가 한 해의 원금과 이자 상환액", "원금과 이자 상환액이 한 해의 NOI", "DSCR의 분자와 분모 역할을 바꿨다."),
        _mutation_pairs("equity-distribution-irr", "cashflow_scope_swap", "초기 자기자본 투자와 보유 중·매각 시 분배금", "초기 부동산 총가치와 회계상 감가상각", "보유기간 수익률의 현금흐름 범위를 바꿨다."),
        _mutation_pairs("rise-drop-da", "direction_reverse", "올라간다", "내려간다", "증감 방향을 뒤바꿨다."),
        _mutation_pairs("rise-drop-do", "direction_reverse", "올라도", "내려도", "증감 조건의 방향을 뒤바꿨다."),
        _mutation_pairs("subtract-add-ya", "bridge_adjustment_swap", "빼야", "더해야", "브리지 조정의 가감 방향을 뒤바꿨다."),
        _mutation_pairs("subtract-add-ji", "inclusion_boundary_swap", "빼지 않는다", "반드시 뺀다", "비용의 포함 여부를 뒤바꿨다."),
        _mutation_pairs("exclude-include-hae", "inclusion_boundary_swap", "제외해", "포함해", "포함 경계를 뒤바꿨다."),
        _mutation_pairs("reflect-ignore", "inclusion_boundary_swap", "반영해야", "무시해야", "필수 반영 항목을 제외했다."),
        _mutation_pairs("separate-combine", "aggregation_swap", "따로", "한꺼번에", "분리해야 할 항목을 합쳤다.", False),
        _mutation_pairs("combine-subtract", "aggregation_swap", "합치면", "서로 빼면", "합산 관계를 차감 관계로 바꿨다."),
        _mutation_pairs("divide-combine", "aggregation_swap", "나누면", "하나로 합치면", "분해 관계를 합산 관계로 바꿨다.", False),
        _mutation_pairs("divide-multiply", "ratio_role_swap", "나눠", "곱해", "비율의 연산 역할을 바꿨다."),
        _mutation_pairs("multiply-add", "risk_role_swap", "곱해", "더해", "확률가중 관계를 단순 합산으로 바꿨다."),
        _mutation_pairs("match-mismatch", "consistency_reverse", "맞는다", "어긋난다", "정합성 조건을 뒤바꿨다."),
        _mutation_pairs("changes-fixed", "condition_reverse", "변할 때", "고정될 때", "변화가 필요한 조건을 고정 조건으로 바꿨다."),
        _mutation_pairs("different-equal-result", "direction_reverse", "달라진다", "같아진다", "결과의 차이 여부를 뒤바꿨다."),
        _mutation_pairs("important-irrelevant", "relevance_reverse", "중요하다", "무관하다", "판단 관련성을 뒤바꿨다."),
        _mutation_pairs("near-far-event", "timing_swap", "가까우며", "멀며", "촉매의 예상 시점을 바꿨다."),
        _mutation_pairs("better-worse-surok", "quality_reverse", "좋을수록", "나쁠수록", "결과 품질의 방향을 뒤바꿨다."),
        _mutation_pairs("many-few-go", "direction_reverse", "많고", "적고", "가용 자원의 많고 적음을 뒤바꿨다."),
        _mutation_pairs("receivable-estimated-realized", "timing_swap", "받을 돈 100원", "이미 받은 현금 100원", "미수금과 회수 완료 현금을 바꿨다."),
        _mutation_pairs("expected-loss-certain-profit", "claim_swap", "예상 손실 3원", "확정 수익 3원", "예상 손실을 확정 수익으로 바꿨다."),
        _mutation_pairs("discount-premium-issuance", "basis_swap", "할인 발행한", "할증 발행한", "채권 발행가격의 할인과 할증을 바꿨다."),
        _mutation_pairs("repo-higher-lower-repurchase", "direction_reverse", "더 높은 가격으로 되사는", "더 낮은 가격으로 되사는", "레포의 재매입 가격 방향을 바꿨다."),
        _mutation_pairs("repo-collateral-buffer-full-loan", "inclusion_boundary_swap", "담보가치 중 대출하지 않는 완충분", "담보가치 전액을 대출한 금액", "레포 haircut의 미대출 완충 범위를 전액 대출로 바꿨다."),
        _mutation_pairs("arbitrage-lock-profit-loss", "sign_reverse", "확정이익을 만드는", "확정손실을 만드는", "무차익거래의 잠금 결과를 이익에서 손실로 바꿨다."),
        _mutation_pairs("operations-financing-total", "cashflow_classification_swap", "본업, 장기자산 투자, 차입·증자·배당", "차입·증자·배당, 장기자산 투자, 본업", "현금흐름 활동의 분류 역할을 바꿨다."),
        _mutation_pairs("revenue-asset-scale", "denominator_swap", "매출 100억 원", "자산 1,000억 원", "성과비율의 규모 기준을 바꿨다."),
        _mutation_pairs("tax-shareholder-risk", "capital_structure_role_swap", "세금효과", "주주위험", "레버리지의 세금효과와 주주위험 역할을 바꿨다."),
        _mutation_pairs("incremental-sunk-cash", "decision_scope_swap", "새로 생기거나 사라지는 현금", "이미 지출해 되돌릴 수 없는 비용", "증분현금과 매몰비용의 범위를 바꿨다."),
        _mutation_pairs("sunk-future-cost", "decision_scope_swap", "이미 쓴 시장조사비", "앞으로 지출할 공장 건설비", "매몰비용과 미래 증분비용을 바꿨다."),
        _mutation_pairs("wacc-cost-equity", "discount_pair_swap", "WACC와 자기자본비용", "자기자본비용과 WACC", "현금흐름과 할인율의 짝을 뒤바꿨다."),
        _mutation_pairs("dividend-foreign-rate", "carry_role_swap", "배당이나 해외금리", "자금조달비용", "보유수익과 조달비용의 역할을 바꿨다."),
        _mutation_pairs("separate-profit-causes", "aggregation_swap", "매출 성장과 비용률을 따로", "매출 성장과 비용률을 한 값으로 합쳐", "이익 동인의 분리를 합산으로 바꿨다."),
        _mutation_pairs("profit-driver-cash-source", "claim_swap", "이익의 원인이 보인다", "현금잔액의 출처가 보인다", "손익 동인 분석의 대상을 현금잔액으로 바꿨다."),
        _mutation_pairs("scenario-probability-equal", "probability_swap", "각 시나리오가 얼마나 가능", "모든 시나리오가 똑같이 가능", "시나리오별 발생확률을 동일하게 바꿨다."),
        _mutation_pairs("head-office-cost-add", "inclusion_boundary_swap", "본사비용과 내부거래 제거", "본사비용과 내부거래 가산", "연결 조정의 제거를 가산으로 바꿨다."),
        _mutation_pairs("traffic-conversion-ticket", "driver_swap", "방문객, 구매전환, 객단가", "부채, 이자비용, 세율", "점포 운영 동인을 금융 동인으로 바꿨다.", False),
        _mutation_pairs("capacity-contribution-margin", "driver_swap", "생산능력 사용 정도와 단위당 공헌이익", "시장금리와 총차입금", "손익분기 분석의 운영 동인을 금융 동인으로 바꿨다."),
        _mutation_pairs("break-even-fixed-variable-cost", "cost_role_swap", "고정비를 회수하는 물량", "변동비만 회수하는 물량", "손익분기점의 회수 대상 비용을 고정비에서 변동비로 바꿨다."),
        _mutation_pairs("store-driver-growth-source", "claim_swap", "어떤 운영 레버가 실제 성장을 만들었는지", "어떤 금융 조달이 과거 장부가를 만들었는지", "점포 성장 분석의 설명 대상을 금융 조달과 장부가로 바꿨다."),
        _mutation_pairs("store-drivers-combined", "aggregation_swap", "방문객, 구매전환, 객단가를 나누면", "방문객·구매전환·객단가를 구분하지 않으면", "점포 매출 동인의 구분을 제거했다."),
        _mutation_pairs("fee-rate-transaction-volume", "platform_role_swap", "수수료율", "전체 거래규모", "플랫폼 수익률과 거래규모의 역할을 바꿨다."),
        _mutation_pairs("platform-variable-cost-add", "bridge_adjustment_swap", "변동비를 차감한 뒤", "변동비를 가산한 뒤", "플랫폼 단위경제성에서 변동비의 가감 방향을 바꿨다."),
        _mutation_pairs("platform-company-share-zero", "inclusion_boundary_swap", "회사가 매출로 가져가는 몫", "회사가 매출로 가져가지 못하는 몫", "플랫폼 거래액 중 회사 귀속 매출의 포함 여부를 바꿨다."),
        _mutation_pairs("sales-collection-quality", "asset_role_swap", "판매와 회수", "생산과 차입", "운전자산의 판매·회수 역할을 바꿨다."),
        _mutation_pairs("cash-double-count", "inclusion_boundary_swap", "양쪽에서 더하면", "한쪽에서만 더하면", "이중계상 조건을 단일 반영으로 바꿨다."),
        _mutation_pairs("cash-double-count-repeat", "inclusion_boundary_swap", "이중계상이므로 포함 기준을 한 번만 적용", "누락이므로 포함 기준을 두 번 적용", "현금 브리지의 중복 반영 방지 원칙을 뒤집었다."),
        _mutation_pairs("growth-free-reinvestment", "condition_reverse", "재투자를 그대로 두면", "재투자를 함께 늘리면", "성장과 재투자의 정합 조건을 뒤바꿨다."),
        _mutation_pairs("midyear-endyear", "timing_swap", "중간시점", "연말시점", "현금 발생의 대표 시점을 바꿨다."),
        _mutation_pairs("market-expectation-business-plan", "reverse_dcf_role_swap", "시장이 이미 어떤 미래를 기대하는지", "회사가 과거에 무엇을 기록했는지", "역산 분석의 미래 기대를 과거 실적으로 바꿨다."),
        _mutation_pairs("segment-single-multiple", "scope_swap", "사업부별 가치를 따로", "모든 사업부 가치를 하나의 배수로", "SOTP의 사업부 분리를 단일 평가로 바꿨다."),
        _mutation_pairs("segment-head-office-cash-duplicate", "inclusion_boundary_swap", "본사비용과 현금을 중복 반영하지 않아야", "본사비용과 현금을 각 사업부에 중복 반영해야", "사업부 합산 시 본사비용과 현금의 중복 제거 원칙을 뒤집었다."),
        _mutation_pairs("bank-interest-income-cost", "bank_role_swap", "이자수익", "이자비용", "은행의 이자수익과 이자비용 역할을 바꿨다."),
        _mutation_pairs("insurance-new-contract-release", "insurance_role_swap", "신계약, 가정변경, 환율, 해제 속도", "보험료 수취액 하나", "보험계약마진 롤포워드의 동인을 단일 현금항목으로 바꿨다."),
        _mutation_pairs("insurance-future-profit-cash-release", "recognition_cash_swap", "이익으로 풀릴 금액", "즉시 현금으로 지급할 금액", "미래 서비스 이익의 인식 역할을 즉시 현금지급으로 바꿨다."),
        _mutation_pairs("normal-current-production", "normalization_basis_swap", "현재 생산량과 정상 가격·원가", "과거 생산량과 현재 정점 가격·원가", "정상화의 생산량과 가격 기준을 바꿨다."),
        _mutation_pairs("reserve-ignore-risk", "inclusion_boundary_swap", "자산별 위험을 반영", "자산별 위험을 무시", "자원가치의 위험 반영 여부를 바꿨다."),
        _mutation_pairs("expectation-consensus-roles", "expectation_role_swap", "내 예상과 시장 컨센서스, 실제 결과", "실제 결과와 내 예상, 시장 컨센서스", "예상·컨센서스·실제의 비교 역할을 바꿨다."),
        _mutation_pairs("risk-event-target-price", "catalyst_role_swap", "구체적 사건", "장기 평균 실적", "촉매의 사건성을 장기 평균으로 바꿨다."),
        _mutation_pairs("capital-allocation-single-return", "scope_swap", "배당·상환·M&A·재투자", "배당 하나", "자본배분 선택지를 단일 환원수단으로 축소했다."),
        _mutation_pairs("repricing-immediate", "timing_swap", "재가격 주기", "즉시 재가격", "금리 전이의 재가격 시점을 바꿨다."),
        _mutation_pairs("net-debt-exclude", "inclusion_boundary_swap", "순부채까지 포함", "순부채를 제외", "거래부담의 부채 포함 여부를 바꿨다."),
        _mutation_pairs("noi-interest-included", "inclusion_boundary_swap", "이자비용을 빼지 않는다", "이자비용을 반드시 뺀다", "부동산 영업소득의 금융비용 포함 여부를 바꿨다."),
        _mutation_pairs("noi-market-return", "denominator_swap", "시장이 요구하는 부동산 수익률", "회사의 회계상 세율", "Cap rate 평가의 할인 기준을 바꿨다."),
        _mutation_pairs("noi-debt-service-subject", "ratio_role_swap", "운영소득이 원리금 상환액", "원리금 상환액이 운영소득", "채무상환비율의 분자와 분모 역할을 바꿨다."),
        _mutation_pairs("expected-downside-realized-loss", "risk_scope_swap", "평균적인 가격영향", "최악의 확정 손실", "기대하방과 최악손실의 범위를 바꿨다."),
        _mutation_pairs("ctd-cheapest-expensive", "selection_reverse", "가장 싸게 인도", "가장 비싸게 인도", "최저 인도비용 선택 기준을 뒤바꿨다."),
        _mutation_pairs("default-half-full-recovery", "recovery_swap", "절반만 회수", "전액 회수", "부도 후 회수율 가정을 바꿨다."),
        _mutation_pairs("carry-lower-higher-forward", "direction_reverse", "선도가격을 낮추는", "선도가격을 높이는", "보유수익의 선도가격 방향을 뒤바꿨다."),
        _mutation_pairs("volume-price-growth", "driver_swap", "가격 인상으로 매출이 늘", "수량 감소만으로 매출이 늘", "가격과 수량의 매출 기여 역할을 바꿨다."),
        _mutation_pairs("roe-cost-capital-gap", "comparison_role_swap", "주주수익성과 자본비용의 차이", "매출성장률과 세율의 차이", "PBR의 가치 동인을 다른 차이로 바꿨다."),
        _mutation_pairs("scenario-uncertainty-certainty", "aggregation_swap", "불확실성을 하나의 기대값", "확실한 결과를 최악값", "확률가중 기대값을 확정 최악값으로 바꿨다."),
        _mutation_pairs("supplier-delay-early", "timing_swap", "공급업체 결제를 늦추면", "공급업체 결제를 앞당기면", "매입채무 지급 시점을 바꿨다."),
        _mutation_pairs("slower-faster-sales", "direction_reverse", "상품 판매 속도가 느려지고", "상품 판매 속도가 빨라지고", "재고 판매속도의 방향을 뒤바꿨다."),
        _mutation_pairs("reverse-assumption-history", "reverse_dcf_role_swap", "역산한 가정", "과거에 보고된 수치", "역산 가정과 과거 실적의 역할을 바꿨다."),
        _mutation_pairs("capital-insufficient-excess", "capital_condition_swap", "손실흡수 자본이 부족하면", "손실흡수 자본이 충분하면", "규제자본 충족 조건을 뒤바꿨다."),
        _mutation_pairs("bank-profit-regulatory-capital-ignore", "inclusion_boundary_swap", "규제상 손실흡수 자본이 부족하면 지속 가능한 수익성으로 보기 어렵다", "규제상 손실흡수 자본이 부족해도 지속 가능한 수익성으로 본다", "은행 수익성 판단에서 규제자본 부족 조건을 제외했다."),
        _mutation_pairs("resource-include-ignore-risk", "inclusion_boundary_swap", "자산별 위험을 반영해야", "자산별 위험을 무시해야", "자원가치의 위험 반영 여부를 바꿨다."),
        _mutation_pairs("expectation-driver-target-role", "expectation_role_swap", "핵심 드라이버와 목표가 변화", "과거 배당과 장부가", "추정치 괴리의 결과 연결 대상을 바꿨다."),
        _mutation_pairs("net-debt-lower-deal-burden", "direction_reverse", "거래부담은 주식매매대금보다 클", "거래부담은 주식매매대금보다 작을", "순부채 포함 시 거래부담의 방향을 뒤바꿨다."),
        _mutation_pairs("dscr-noi-principal-only", "cashflow_scope_swap", "원금과 이자 상환액", "원금 상환액만", "채무상환액의 범위에서 이자를 제외했다."),
        _mutation_pairs("irr-equity-gross-property", "cashflow_scope_swap", "초기 자기자본 투자", "초기 부동산 총가치", "IRR의 초기 투자 범위를 자기자본에서 총가치로 바꿨다."),
        _mutation_pairs("tail-average-worst", "risk_scope_swap", "평균값이 tail risk", "최악값이 평균 위험", "평균위험과 꼬리위험의 역할을 바꿨다."),
        _mutation_pairs("resource-confirmed-unconfirmed-reserve", "evidence_scope_swap", "확인된 매장량", "확인되지 않은 자원량", "자원가치의 매장량 근거 수준을 바꿨다."),
        # Source-sentence-specific rules below cover the remaining claims for
        # which a broad one-word antonym would be grammatically ambiguous.  The
        # complete source phrase is the match boundary, so each replacement is
        # one auditable claim change rather than free text generation.
        _mutation_pairs("risk-time-exclude", "inclusion_boundary_swap", "시점과 위험을 함께 반영", "시점과 위험을 모두 제외", "가치평가에서 시점과 위험의 반영 여부를 바꿨다."),
        _mutation_pairs("debt-tax-shield", "capital_structure_role_swap", "부채이자는 세금을 줄여 주지만", "부채이자는 세금과 무관하지만", "부채이자의 세금효과를 제거했다."),
        _mutation_pairs("dispersion-center", "risk_role_swap", "중심에서 벗어날 가능성의 크기", "중심 자체의 크기", "분산위험과 기대값의 측정 역할을 바꿨다."),
        _mutation_pairs("benchmark-total-return", "benchmark_scope_swap", "벤치마크 대비 수익", "절대 총수익", "상대성과의 기준을 절대성과로 바꿨다."),
        _mutation_pairs("same-different-maturity", "term_structure_scope_swap", "서로 다른 만기", "하나의 같은 만기", "기간구조의 만기 비교 범위를 바꿨다."),
        _mutation_pairs("first-second-order-sensitivity", "sensitivity_role_swap", "일차 민감도", "이차 곡률", "일차 민감도와 이차 곡률의 역할을 바꿨다."),
        _mutation_pairs("one-bp-hundred-bp", "rate_shock_scope_swap", "1bp 움직일 때", "100bp 움직일 때", "DV01의 금리 충격 단위를 바꿨다."),
        _mutation_pairs("curvature-ignore-correct", "inclusion_boundary_swap", "직선 근사의 오차를 보정", "직선 근사의 오차를 무시", "곡률의 오차 보정 역할을 제거했다."),
        _mutation_pairs("volatility-certain-price", "option_input_swap", "변동성", "확정된 미래가격", "옵션가치의 불확실성 입력을 확정가격으로 바꿨다."),
        _mutation_pairs("option-model-dividend-assumption", "inclusion_boundary_swap", "무배당 유럽형 옵션", "배당을 계속 지급하는 미국형 옵션", "옵션 평가모형의 배당·행사 가정을 바꿨다."),
        _mutation_pairs("option-value-stock-price-input", "option_input_swap", "옵션가치가 주가", "옵션가치가 과거 장부가", "옵션 민감도의 가격 입력을 현재 시장가격에서 과거 장부가로 바꿨다."),
        _mutation_pairs("option-sensitivity-equal-movement", "sensitivity_role_swap", "각각에 대한 민감도만큼 옵션가치가 함께 움직인다", "각 입력과 무관하게 옵션가치가 같은 폭으로 움직인다", "옵션가치의 입력별 민감도를 동일 반응으로 바꿨다."),
        _mutation_pairs("sales-cost-sustainability", "driver_scope_swap", "비용·지속가능성", "매출액 하나", "가격·물량 변화의 평가 범위를 단일 매출액으로 축소했다."),
        _mutation_pairs("maintenance-expansion-capex", "investment_scope_swap", "노후 설비를 유지하기 위한 교체투자", "생산능력을 늘리는 확장투자", "유지투자와 확장투자의 역할을 바꿨다."),
        _mutation_pairs("dilution-denominator-ignore", "inclusion_boundary_swap", "분모 효과를 봐야", "분모 효과를 무시해야", "주식수 변화의 분모 반영 여부를 바꿨다."),
        _mutation_pairs("per-profit-book-equity", "denominator_swap", "주당이익의 몇 배", "주당 장부자본의 몇 배", "가치평가 배수의 분모를 이익에서 장부자본으로 바꿨다."),
        _mutation_pairs("pbr-net-assets-sales", "denominator_swap", "순자산 1원", "매출 1원", "PBR의 경제적 기준을 순자산에서 매출로 바꿨다."),
        _mutation_pairs("small-large-assumption", "sensitivity_reverse", "작은 가정 변화가 큰 가치 차이", "큰 가정 변화만 작은 가치 차이", "가정과 가치의 민감도 방향을 뒤바꿨다."),
        _mutation_pairs("multiple-policy-ignore", "comparison_condition_swap", "회계정책, 경기시점이 다르면", "회계정책, 경기시점이 달라도", "비교가능성에 필요한 조건을 제거했다."),
        _mutation_pairs("ltm-ntm-adjustment-inconsistency", "consistency_reverse", "LTM과 NTM, 리스·R&D·SBC 조정도 비교기업 사이에서 같아야", "LTM과 NTM, 리스·R&D·SBC 조정을 비교기업마다 다르게 둬야", "비교기업 배수의 기간·조정 기준 일관성을 뒤바꿨다."),
        _mutation_pairs("upside-risk-ignore", "inclusion_boundary_swap", "위험과 도달기간도 함께 고려", "위험과 도달기간은 모두 무시", "상승여력 판단의 위험·기간 반영 여부를 바꿨다."),
        _mutation_pairs("cohort-average-only", "aggregation_swap", "가입시기별 유지율과 마진을 함께 봐야", "전체 평균 고객값만 봐야", "코호트별 분석을 전체 평균으로 바꿨다."),
        _mutation_pairs("backlog-current-past-sales", "timing_swap", "현재 매출을 얼마나 대체", "과거 매출을 얼마나 대체", "주문잔고의 선행 기준을 현재에서 과거로 바꿨다."),
        _mutation_pairs("r-and-d-asset-expense-only", "inclusion_boundary_swap", "R&D 자산과 상각도 함께 만들어야", "당기 R&D 비용만 되돌려야", "연구개발 자산과 상각의 동시 반영을 제거했다."),
        _mutation_pairs("sbc-double-count-ignore", "inclusion_boundary_swap", "주식수 희석까지 무시하면", "주식수 희석을 정확히 반영하면", "주식보상 이중계상의 발생 조건을 뒤바꿨다."),
        _mutation_pairs("lease-consistent-accounting", "consistency_reverse", "같은 회계 기준으로 맞춰야", "서로 다른 회계 기준을 써야", "리스 비교의 회계기준 일관성을 뒤바꿨다."),
        _mutation_pairs("lease-multiple-consistency", "consistency_reverse", "EBITDA와 배수도 같은 pre/post-lease 기준으로 맞춰야", "EBITDA는 pre-lease, 배수는 post-lease 기준으로 섞어야", "리스 조정의 이익과 배수 기준 일관성을 뒤바꿨다."),
        _mutation_pairs("same-enterprise-different-value", "equivalence_reverse", "같은 기업가치를 다른 경로", "서로 다른 기업가치를 같은 경로", "가치평가 경로의 등가성과 결과를 뒤바꿨다."),
        _mutation_pairs("valuation-three-claims-one-claim", "scope_swap", "각각 전체 자본, 보통주 현금, 장부자본 초과이익", "모두 보통주 현금 하나", "가치평가 경로별 귀속 범위를 단일 현금흐름으로 축소했다."),
        _mutation_pairs("sotp-separate-business", "aggregation_swap", "성격이 다른 사업부를 각자", "모든 사업부를 하나로 합쳐", "사업부별 평가를 단일 평가로 바꿨다."),
        _mutation_pairs("sotp-head-office-debt-adjustment", "inclusion_boundary_swap", "본사비용과 순부채 등을 조정해 합산", "본사비용과 순부채를 조정하지 않고 합산", "사업부 가치 합산에서 본사비용과 순부채 조정을 제외했다."),
        _mutation_pairs("late-early-claims-report", "timing_swap", "사고는 늦게 보고될 수 있어", "사고는 항상 즉시 확정되어", "보험사고 보고 시점의 불확실성을 제거했다."),
        _mutation_pairs("future-service-past-service", "timing_swap", "미래 서비스에서 인식할", "이미 끝난 과거 서비스에서 인식할", "보험계약마진의 서비스 귀속 시점을 바꿨다."),
        _mutation_pairs("better-worse-than-market", "expectation_reverse", "시장이 이미 기대하는 뉴스보다 더 좋은 결과", "시장이 이미 기대하는 뉴스보다 더 나쁜 결과", "촉매의 시장기대 대비 방향을 뒤바꿨다."),
        _mutation_pairs("probability-impact-one-factor", "aggregation_swap", "사건확률과 충격을 결합한", "사건확률 하나만 반영한", "하방위험에서 충격 크기를 제외했다."),
        _mutation_pairs("liquidity-ignore-runway", "inclusion_boundary_swap", "현금소진, 만기부채, covenant, 차환 가능성을 함께 봐야", "현금잔액 하나만 봐야", "생존여력의 의무·차환 조건을 제외했다."),
        _mutation_pairs("nominal-inflation-add", "bridge_adjustment_swap", "물가상승 효과를 제거", "물가상승 효과를 더해", "명목금리에서 물가효과를 조정하는 방향을 뒤바꿨다."),
        _mutation_pairs("basis-point-unit", "unit_scope_swap", "100bp가 1%포인트", "1bp가 1%포인트", "베이시스포인트 환산 단위를 바꿨다."),
        _mutation_pairs("fx-payable-receivable", "position_swap", "달러 지급의무", "달러 수취권리", "환율변화에 노출되는 지급자와 수취자의 역할을 바꿨다."),
        _mutation_pairs("surprise-eps-revenue", "impact_scope_swap", "EPS와 목표주가", "과거 매출액 하나", "실적 괴리의 영향 대상을 이익·가치에서 과거 매출로 바꿨다."),
        _mutation_pairs("kpi-multi-year-one-quarter", "persistence_swap", "여러 해 이익전망", "한 분기 과거 실적", "KPI 변화의 지속기간과 전망 대상을 바꿨다."),
        _mutation_pairs("expected-center-maximum", "aggregation_swap", "기대값은 중심", "기대값은 최댓값", "기대값의 집계 역할을 중심에서 극단값으로 바꿨다."),
        _mutation_pairs("tracking-error-rise-fall", "direction_reverse", "추적오차가 커지고", "추적오차가 작아지고", "액티브 수익 변동의 방향을 뒤바꿨다."),
        _mutation_pairs("multiple-mechanical-allowed", "condition_reverse", "기계적으로 적용할 수 없다", "기계적으로 그대로 적용해야 한다", "배수 비교의 적용 조건을 뒤바꿨다."),
        _mutation_pairs("target-above-below-current", "direction_reverse", "목표가가 현재가보다 높다는", "목표가가 현재가보다 낮다는", "목표가격과 현재가격의 비교 방향을 바꿨다."),
        _mutation_pairs("bad-good-cohort-hidden", "quality_reverse", "나쁜 cohort가 숨을 수", "좋은 cohort만 드러날 수", "평균값이 숨기는 고객군의 성격을 바꿨다."),
        _mutation_pairs("catalyst-time-unspecified", "inclusion_boundary_swap", "어떤 지표에서 언제 확인될지를 촉매로 적어야", "지표와 확인 시점을 적지 않아야", "촉매의 지표·시점 명시 요건을 제거했다."),
        _mutation_pairs("market-better-worse-result", "expectation_reverse", "뉴스보다 더 좋은 결과", "뉴스보다 더 나쁜 결과", "시장 기대 대비 결과 방향을 뒤바꿨다."),
        _mutation_pairs("upside-compensation-ignore", "inclusion_boundary_swap", "이 개념이 위험과 시간, 배당, 목표가 도달 가능성을 보상할 만큼 큰지 함께 봐야 한다", "위험과 시간, 배당, 목표가 도달 가능성을 무시해도 충분하다", "상승여력 판단에서 위험·기간·배당·실현가능성을 제외했다."),
        _mutation_pairs("target-price-below-current", "direction_reverse", "목표가가 현재가보다 높다는", "목표가가 현재가보다 낮다는", "목표가격과 현재가격의 비교 방향을 바꿨다."),
        _mutation_pairs("upside-alone-sufficient", "inclusion_boundary_swap", "사실만으로 충분하지 않다", "사실만으로 충분하다", "목표가격 격차만으로 판단해도 되는지 여부를 바꿨다."),
        _mutation_pairs("catalyst-verifiability-reverse", "verification_reverse", "투자논리가 검증 가능해진다", "투자논리를 검증할 수 없게 된다", "촉매의 지표와 시점을 명시했을 때 생기는 검증 가능성을 뒤바꿨다."),
    )
    for rule in pair
)

MUTATION_RULES = PHRASE_MUTATION_RULES + MUTATION_RULES


def _normalize_source_text(value: str) -> str:
    return base.normalize_text(re.sub(r"\$+|\\[A-Za-z]+|[{}_^]", " ", value))


def _source_snippet(text: str, match: re.Match[str]) -> str:
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+|\n+", text)
        if item.strip()
    ]
    matched = match.group(0)
    return next((item for item in sentences if matched.casefold() in item.casefold()), matched)


def extract_anchor_evidence(
    element: base.ElementRecord,
    raw: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    fields = {
        "title": element.title,
        "definition": element.definition,
        "intuition": element.intuition,
        "coreRelation": element.core_relation,
        "formulaNotes": str(raw.get("formulaNotes", "")),
        "checklist": str(raw.get("checklist", "")),
    }
    result: dict[str, dict[str, Any]] = {}
    for rule in ANCHOR_RULES:
        evidence_rows = []
        for field, source in fields.items():
            normalized = _normalize_source_text(source)
            for pattern in rule.patterns:
                match = re.search(pattern, normalized, flags=re.IGNORECASE)
                if match is None:
                    continue
                evidence_rows.append(
                    {
                        "sourceField": field,
                        "evidenceText": match.group(0),
                        "evidenceSnippet": _source_snippet(normalized, match),
                        "sourceLocator": element.source_locator,
                        "sourceSha256": base._sha256_bytes(normalized.encode("utf-8")),
                    }
                )
                break
        if evidence_rows:
            result[rule.anchor_id] = {
                "anchorId": rule.anchor_id,
                "label": rule.label,
                "evidence": evidence_rows,
            }
    return result


@lru_cache(maxsize=None)
def extract_text_anchor_evidence(
    *,
    element: base.ElementRecord,
    text: str,
    source_field: str,
) -> dict[str, dict[str, Any]]:
    normalized = _normalize_source_text(text)
    result: dict[str, dict[str, Any]] = {}
    for rule in ANCHOR_RULES:
        evidence_rows = []
        for pattern in rule.patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match is None:
                continue
            evidence_rows.append(
                {
                    "sourceField": source_field,
                    "evidenceText": match.group(0),
                    "evidenceSnippet": _source_snippet(normalized, match),
                    "sourceLocator": element.source_locator,
                    "sourceSha256": base._sha256_bytes(normalized.encode("utf-8")),
                }
            )
            break
        if evidence_rows:
            result[rule.anchor_id] = {
                "anchorId": rule.anchor_id,
                "label": rule.label,
                "evidence": evidence_rows,
            }
    return result


def anchor_document_frequency(
    anchors: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> Counter[str]:
    """Count source elements containing each explicit anchor."""

    return Counter(
        anchor_id
        for element_anchors in anchors.values()
        for anchor_id in element_anchors
    )


def _nearest_rank_percentile(values: Sequence[int], percentile: float) -> int:
    if not values:
        raise base.ConceptModelError("Cannot calculate an anchor percentile without data")
    ordered = sorted(int(value) for value in values)
    # Nearest-rank is ceil(p * N), expressed as a zero-based index.
    rank = max(1, int(math.ceil(percentile * len(ordered))))
    return ordered[rank - 1]


def reference_gate_policy(
    anchors: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    """Return the exact, reproducible exception criteria for this corpus."""

    frequencies = anchor_document_frequency(anchors)
    ordered_frequencies = sorted(int(value) for value in frequencies.values())
    percentile_rank = max(
        1,
        int(
            math.ceil(
                ANCHOR_DOCUMENT_FREQUENCY_PERCENTILE * len(ordered_frequencies)
            )
        ),
    )
    p75 = _nearest_rank_percentile(
        ordered_frequencies,
        ANCHOR_DOCUMENT_FREQUENCY_PERCENTILE,
    )
    return {
        "policyId": REFERENCE_GATE_POLICY_ID,
        "referencePath": base._report_path(REFERENCE_DESIGN_PATH),
        "referenceSections": [
            "5.1-5.3 타개념 혼동 오답 규칙",
            "6 개념변형 오답 규칙",
            "11.2-11.3 생성 절차",
            "15 자동 품질 게이트",
            "16 사람 검수와 릴리스 게이트",
        ],
        "hardGateThresholds": dict(REFERENCE_GATE_THRESHOLDS),
        "anchorCorpus": {
            "elementCount": len(anchors),
            "anchorVocabularyCount": len(frequencies),
            "documentFrequencyStatistic": "nearest-rank 75th percentile",
            "documentFrequencyPercentile": ANCHOR_DOCUMENT_FREQUENCY_PERCENTILE,
            "nearestRankFormula": "rank = ceil(percentile * anchorVocabularyCount)",
            "nearestRank": percentile_rank,
            "documentFrequencyP75": p75,
            "specificAnchorDefinition": f"documentFrequency <= {p75}",
            "specificAnchorUse": (
                "품질 정렬·감사 수치이며 하드 게이트가 아니다. 설계서의 명시 앵커 "
                "1개 이상 조건은 빈도가 높은 앵커에도 동일하게 적용한다."
            ),
            "documentFrequencyByAnchorId": dict(sorted(frequencies.items())),
        },
        "exceptionRule": (
            "하드 게이트 하나라도 위반하면 생성 자체를 중단하고 산출물을 쓰지 않는다. "
            "하드 게이트를 모두 통과한 문항 중 소프트 기준 하나 이상에 해당하는 "
            "문항만 review_required로 분류한다. 모델 점수나 목표 검수율로 예외 수를 "
            "맞추지 않는다."
        ),
        "softReviewCriteria": dict(SOFT_REVIEW_CRITERIA),
        "softReviewFormulas": dict(SOFT_REVIEW_FORMULAS),
    }


def mutation_rule_prefix(rule_id: str) -> str:
    return re.sub(r"-(?:forward|reverse)$", "", rule_id)


def relation_metadata(
    *,
    element: base.ElementRecord,
    text: str,
    anchor_ids: Sequence[str],
) -> dict[str, Any]:
    """Build a source-derived relation record without inventing entity kinds."""

    normalized = base.normalize_text(text)
    if re.search(r"(?:먼저|나중|이전|이후|기초|기말|시점|기간|만기)", normalized):
        relation_type = "sequence_timing"
    elif re.search(r"(?:포함|제외|더하|빼|나누|합치|구성|비중)", normalized):
        relation_type = "composition_inclusion"
    elif re.search(r"(?:연결|조정|이어|전환|환산)", normalized):
        relation_type = "bridge_conversion"
    elif re.search(r"(?:맞춰|대응|짝|귀속|요구수익률|할인율)", normalized):
        relation_type = "application_pairing"
    elif re.search(r"(?:같|다르|비교|대비|범위)", normalized):
        relation_type = "comparison_boundary"
    elif re.search(r"(?:분류|자산|부채|자본|상위|하위)", normalized):
        relation_type = "hierarchy_classification"
    elif re.search(r"(?:때문|따라|하여|해서|므로|생기)", normalized):
        relation_type = "causal"
    else:
        relation_type = "directional"
    participants = [element.element_id]
    participants.extend(
        f"{element.element_id}:source-anchor:{anchor_id}"
        for anchor_id in dict.fromkeys(anchor_ids)
        if anchor_id
    )
    participants = list(dict.fromkeys(participants))
    if len(participants) < 2:
        raise base.ConceptModelError(
            f"{element.element_id} relation has no explicit source anchor participant"
        )
    participants = participants[:6]
    role_bindings = {
        f"participant{index}": participant
        for index, participant in enumerate(participants, start=1)
    }
    edges = [
        {
            "from": participants[index],
            "predicate": relation_type,
            "to": participants[index + 1],
        }
        for index in range(len(participants) - 1)
    ]
    return {
        "relationType": relation_type,
        "participantIds": participants,
        "roleBindings": role_bindings,
        "relationEdges": edges,
        "relationEvidence": {
            "sourceField": "verbal_relation",
            "evidenceText": normalized,
            "sourceLocator": element.source_locator,
            "sourceSha256": base._sha256_bytes(normalized.encode("utf-8")),
            "classificationPolicy": "explicit-source-predicate-v1",
            "participantPolicy": "checked-in-source-anchor-v1",
        },
    }


@lru_cache(maxsize=None)
def audit_definition_role_evidence(
    element: base.ElementRecord,
) -> list[dict[str, str]]:
    existing = [item.report_dict() for item in base.definition_role_evidence(element)]
    seen = {str(item["roleId"]) for item in existing}
    definition = base.normalize_text(element.definition)
    source_sha = base._sha256_bytes(definition.encode("utf-8"))
    for role_id, rule_id, pattern in AUDIT_DEFINITION_ROLE_RULES:
        match = pattern.search(definition)
        if match is None or role_id in seen:
            continue
        seen.add(role_id)
        existing.append(
            {
                "roleId": role_id,
                "ruleId": rule_id,
                "sourceField": "definition",
                "evidenceText": match.group(0).rstrip("."),
                "sourceLocator": element.source_locator,
                "sourceSha256": source_sha,
            }
        )
    return existing


@lru_cache(maxsize=None)
def audit_definition_role_compatibility(
    target: base.ElementRecord,
    candidate: base.ElementRecord,
) -> dict[str, Any]:
    target_evidence = audit_definition_role_evidence(target)
    candidate_evidence = audit_definition_role_evidence(candidate)
    if not target_evidence or not candidate_evidence:
        return {
            "allowed": True,
            "reasonId": "insufficient-source-evidence",
            "targetEvidence": target_evidence,
            "candidateEvidence": candidate_evidence,
        }
    target_roles = {str(item["roleId"]) for item in target_evidence}
    candidate_roles = {str(item["roleId"]) for item in candidate_evidence}
    return {
        "allowed": not target_roles.isdisjoint(candidate_roles),
        "reasonId": (
            "source-backed-role-match"
            if not target_roles.isdisjoint(candidate_roles)
            else "definition-role-mismatch"
        ),
        "targetEvidence": target_evidence,
        "candidateEvidence": candidate_evidence,
    }


def generate_mutations(
    text: str,
    *,
    base_fact_id: str,
    target_element_id: str,
) -> list[dict[str, Any]]:
    """Generate one-change mutations whose opposite is explicit in the source."""

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rule in MUTATION_RULES:
        start = 0
        latin_boundary = bool(
            re.fullmatch(r"[A-Za-z][A-Za-z0-9 .&/-]*", rule.before)
        )
        while True:
            index = text.find(rule.before, start)
            if index < 0:
                break
            start = index + len(rule.before)
            if latin_boundary:
                before_char = text[index - 1] if index else ""
                after_index = index + len(rule.before)
                after_char = text[after_index] if after_index < len(text) else ""
                if before_char.isalnum() or after_char.isalnum():
                    continue
            mutated = text[:index] + rule.after + text[index + len(rule.before) :]
            key = base.normalized_key(mutated)
            if not key or key in seen or mutated == text:
                continue
            seen.add(key)
            mutation_id = (
                f"{base_fact_id}:{rule.rule_id}:"
                f"{base._sha256_bytes(mutated.encode('utf-8'))[:8]}"
            )
            result.append(
                {
                    "mutationId": mutation_id,
                    "targetElementId": target_element_id,
                    "baseFactId": base_fact_id,
                    "mutationRuleId": rule.rule_id,
                    "mutationCategory": rule.category,
                    "text": mutated,
                    "changedClaim": f"{rule.before} → {rule.after}",
                    "falsityRationale": (
                        f"출처의 참 문장은 ‘{rule.before}’라고 명시하지만 이 선지는 "
                        f"그 역할을 ‘{rule.after}’로 바꿨다. {rule.rationale}"
                    ),
                    "sourceTruthText": text,
                    "statementTruth": False,
                    "generatorConfidence": "source_antonym_exact",
                    "autoReviewPassed": rule.auto_safe,
                    "reviewReasons": []
                    if rule.auto_safe
                    else ["broad-token-replacement-needs-language-review"],
                }
            )
    return result


def selected_mutation_lint_reasons(text: str) -> list[str]:
    """Reject known Korean boundary breakage before a mutation is selectable."""

    patterns = {
        "broken-korean-particle": re.compile(
            r"(?:원금를|세율를|이익가 차지|가치이 차지|부채가가|자산이가)"
        ),
        "broken-comparative-ending": re.compile(
            r"보다 (?:작면|적면|많면)"
        ),
        "broken-compound-replacement": re.compile(
            r"(?:고정성|주기업가치|총부채 만기|기초부채|기말자산|"
            r"행사수량|리스자기자본)"
        ),
    }
    return [reason_id for reason_id, pattern in patterns.items() if pattern.search(text)]


def load_raw_elements(path: Path = DEFAULT_RAW_ELEMENTS) -> dict[str, dict[str, Any]]:
    value = json.loads(base._resolve_repo_path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise base.ConceptModelError("Raw element export must be a list")
    result = {
        str(item.get("elementId")): dict(item)
        for item in value
        if isinstance(item, Mapping) and item.get("elementId")
    }
    if len(result) != 135:
        raise base.ConceptModelError("Raw element export must contain 135 elements")
    return result


def build_atomic_facts(
    element: base.ElementRecord,
    raw: Mapping[str, Any],
    element_anchors: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[tuple[str, str]] = [
        ("definition", base.display_fact_text(element, "definition")),
    ]
    candidates.extend(
        ("intuition_claim", sentence)
        for sentence in re.split(
            r"(?<=[.!?])\s+", base.display_fact_text(element, "intuition")
        )
        if sentence.strip()
    )
    candidates.append(
        ("verbal_relation", base.display_fact_text(element, "verbal_relation"))
    )
    for field in ("formulaNotes", "checklist"):
        for line in str(raw.get(field, "")).splitlines():
            cleaned = re.sub(r"^\s*[-*•]+\s*", "", line).strip()
            if not cleaned:
                continue
            candidates.append(
                ("application_claim", base.mask_title_mentions(cleaned, element.title))
            )
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim_type, text in candidates:
        normalized = base.normalize_text(text)
        key = base.normalized_key(normalized)
        if (
            not key
            or key in seen
            or base.FORMULA_CHOICE_RE.search(normalized)
            or base.text_mentions_title(normalized, element.title)
        ):
            continue
        seen.add(key)
        source_sha = base._sha256_bytes(normalized.encode("utf-8"))
        record = {
            "factId": f"{element.element_id}:atomic:{len(result) + 1:02d}",
            "elementId": element.element_id,
            "claimType": claim_type,
            "text": normalized,
            "statementTruth": True,
            "sourceLocator": element.source_locator,
            "sourceSha256": source_sha,
            "reviewStatus": "source_reviewed_masked",
        }
        if claim_type == "verbal_relation":
            anchors_for_relation = [
                anchor_id
                for anchor_id, anchor in (element_anchors or {}).items()
                if any(
                    str(row.get("sourceField")) in {"intuition", "coreRelation", "definition"}
                    for row in anchor.get("evidence", [])
                )
            ]
            record.update(
                relation_metadata(
                    element=element,
                    text=normalized,
                    anchor_ids=anchors_for_relation,
                )
            )
        result.append(record)
    if len(result) < 4:
        raise base.ConceptModelError(
            f"{element.element_id} has fewer than four independent source facts"
        )
    return result


def _sentence_keywords(text: str, anchor_labels: set[str]) -> list[str]:
    stop = {
        "이", "그", "저", "개념", "분석", "값", "경우", "정도", "하나", "여러",
        "함께", "서로", "통해", "대한", "따라", "때문", "가장", "현재", "실제",
        "다음", "있다", "없다", "한다", "된다", "보여", "위해", "같은", "다른",
    }
    tokens = {
        token.casefold()
        for token in base.TOKEN_RE.findall(text)
        if len(token) >= 2 and token.casefold() not in stop
    }
    tokens -= {label.casefold() for label in anchor_labels}
    return sorted(tokens, key=lambda item: (-len(item), item))[:6]


def build_cross_concept_evidence(
    target: base.ElementRecord,
    candidate: base.ElementRecord,
    anchors: Mapping[str, Mapping[str, Mapping[str, Any]]],
    anchor_frequencies: Mapping[str, int] | None = None,
    target_text: str | None = None,
    candidate_text: str | None = None,
) -> dict[str, Any] | None:
    target_anchors = anchors[target.element_id]
    candidate_anchors = anchors[candidate.element_id]
    shared = sorted(set(target_anchors) & set(candidate_anchors))
    target_only = sorted(set(target_anchors) - set(candidate_anchors))
    candidate_only = sorted(set(candidate_anchors) - set(target_anchors))
    if not shared or not target_only or not candidate_only:
        return None
    frequencies = anchor_frequencies or anchor_document_frequency(anchors)
    target_text_anchors = (
        extract_text_anchor_evidence(
            element=target,
            text=target_text,
            source_field="displayedFact",
        )
        if target_text is not None
        else {}
    )
    candidate_text_anchors = (
        extract_text_anchor_evidence(
            element=candidate,
            text=candidate_text,
            source_field="displayedFact",
        )
        if candidate_text is not None
        else {}
    )
    displayed_shared = sorted(
        set(target_text_anchors) & set(candidate_text_anchors),
        key=lambda item: (int(frequencies[item]), item),
    )
    shared = sorted(shared, key=lambda item: (int(frequencies[item]), item))
    target_only = sorted(target_only, key=lambda item: (int(frequencies[item]), item))
    candidate_only = sorted(candidate_only, key=lambda item: (int(frequencies[item]), item))
    shared_records = []
    for anchor_id in shared:
        shared_records.append(
            {
                "anchorId": anchor_id,
                "label": target_anchors[anchor_id]["label"],
                "documentFrequency": int(frequencies[anchor_id]),
                "targetEvidence": target_anchors[anchor_id]["evidence"],
                "candidateEvidence": candidate_anchors[anchor_id]["evidence"],
            }
        )
    target_axis = target_anchors[target_only[0]]
    candidate_axis = candidate_anchors[candidate_only[0]]
    return {
        "sharedAnchorIds": shared,
        "sharedAnchors": shared_records,
        "minimumSharedAnchorDocumentFrequency": min(
            int(frequencies[item]) for item in shared
        ),
        "displayedSharedAnchorIds": displayed_shared,
        "displayedSharedAnchorCount": len(displayed_shared),
        "overlapType": "source_text_financial_anchor",
        "distinctAxis": {
            "targetAnchorId": target_only[0],
            "targetLabel": target_axis["label"],
            "candidateAnchorId": candidate_only[0],
            "candidateLabel": candidate_axis["label"],
            "targetEvidence": target_axis["evidence"],
            "candidateEvidence": candidate_axis["evidence"],
        },
        "distinctnessRationale": (
            f"두 개념은 ‘{target_anchors[shared[0]]['label']}’ 맥락을 공유하지만, "
            f"대상은 ‘{target_axis['label']}’, 후보는 ‘{candidate_axis['label']}’에 "
            "각각 출처 근거가 있어 동일한 개념이 아니다."
        ),
        "evidencePolicy": "explicit-source-anchor-v2-corpus-audited",
    }


def _selected_experiment(path: Path) -> dict[str, Any]:
    report = base._load_json_object(base._resolve_repo_path(path))
    if str(report.get("contractVersion")) != "3.1":
        raise base.ConceptModelError("Selected experiment is not v3.1")
    if report.get("adminWritten") or report.get("questionBankWritten"):
        raise base.ConceptModelError("Selected preview experiment has an unsafe write flag")
    return report


def _embedding_for_selection(
    selection: Mapping[str, Any],
    context: base.FeatureContext,
    config: Mapping[str, Any],
    device: str,
) -> base.EmbeddingRun:
    candidate_id = str(selection["embeddingId"])
    if candidate_id == "tfidf-word-char":
        return base.baseline_embedding_run(context)
    specs = {
        str(item["id"]): item
        for item in config.get("embeddingCandidates", [])
        if isinstance(item, Mapping)
    }
    spec = dict(specs[candidate_id])
    pins = config["v3Experiment"]["embeddingRevisionPins"]
    spec["revision"] = str(pins[candidate_id])
    embedding = experiment.load_or_run_embedding(
        spec, context, base.DEFAULT_BUILD_DIR / "embeddings", device
    )
    if embedding.status != "completed":
        raise base.ConceptModelError(
            f"Selected embedding did not load: {embedding.error}"
        )
    return embedding


def _profile_for_selection(selection: Mapping[str, Any]) -> dict[str, Any]:
    profile = {
        "id": str(selection["retrievalProfileId"]),
        **dict(selection["retrievalProfile"]),
    }
    profile.update(dict(selection.get("ratioTotals", {})))
    base._retrieval_weights(profile)
    return profile


def _candidate_model_score(
    *,
    context: base.FeatureContext,
    embedding: base.EmbeddingRun,
    ranker: Any,
    question_index: int,
    candidate_index: int,
) -> float:
    features = base._candidate_features(
        context,
        question_index,
        candidate_index,
        embedding,
    ).reshape(1, -1)
    if hasattr(ranker, "decision_function"):
        return float(np.asarray(ranker.decision_function(features)).reshape(-1)[0])
    return float(np.asarray(ranker.predict(features)).reshape(-1)[0])


def _select_cross_concept_choices(
    *,
    context: base.FeatureContext,
    ranked: Sequence[Sequence[tuple[int, float]]],
    anchors: Mapping[str, Mapping[str, Mapping[str, Any]]],
    embedding: base.EmbeddingRun | None = None,
    ranker: Any | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    selected: dict[str, list[dict[str, Any]]] = {}
    exceptions: list[dict[str, Any]] = []
    anchor_frequencies = anchor_document_frequency(anchors)
    for question_index, question in enumerate(context.questions):
        target = context.elements[question.element_index]
        eligible_records: list[dict[str, Any]] = []
        score_by_candidate = dict(ranked[question_index])
        candidate_pool = [item[0] for item in ranked[question_index]]
        if embedding is not None and ranker is not None:
            candidate_pool = base.eligible_candidate_indices(
                context.elements,
                question.element_index,
                question.question_type,
            )
        for candidate_index in candidate_pool:
            model_score = score_by_candidate.get(candidate_index)
            if model_score is None:
                if embedding is None or ranker is None:
                    continue
                model_score = _candidate_model_score(
                    context=context,
                    embedding=embedding,
                    ranker=ranker,
                    question_index=question_index,
                    candidate_index=candidate_index,
                )
            candidate = context.elements[candidate_index]
            fact_type = base.fact_type_for_question(question.question_type)
            text = base.display_fact_text(candidate, fact_type)
            evidence = build_cross_concept_evidence(
                target,
                candidate,
                anchors,
                anchor_frequencies,
                target_text=question.correct_answer,
                candidate_text=text,
            )
            if evidence is None:
                continue
            decision = base.candidate_filter_decision(
                context.elements,
                question.element_index,
                candidate_index,
                question.question_type,
            )
            reasons = []
            if base.text_mentions_title(text, target.title):
                reasons.append("target-name-exposure")
            if base.text_mentions_title(text, candidate.title):
                reasons.append("source-name-exposure")
            if not decision.allowed:
                reasons.append(decision.reason_id)
            record = {
                "choiceSourceType": "cross_concept_fact",
                "sourceElementId": candidate.element_id,
                "sourceElementTitle": candidate.title,
                "text": text,
                "statementTruth": True,
                "isAnswer": False,
                "modelScore": round(float(model_score), 8),
                "sourceLocator": candidate.source_locator,
                "sourceSha256": base._sha256_bytes(text.encode("utf-8")),
                "definitionRoleCompatibility": audit_definition_role_compatibility(
                    target,
                    candidate,
                )
                if question.question_type == "term_to_definition"
                else None,
                **evidence,
                "autoReviewPassed": not reasons,
                "reviewReasons": reasons,
            }
            if question.question_type == "term_to_verbal_relation":
                record.update(
                    relation_metadata(
                        element=candidate,
                        text=text,
                        anchor_ids=evidence["sharedAnchorIds"],
                    )
                )
            if (
                question.question_type == "term_to_definition"
                and not record["definitionRoleCompatibility"]["allowed"]
            ):
                continue
            if reasons:
                continue
            eligible_records.append(record)

        # The selected ranker remains the primary relevance signal.  The
        # explicit source evidence then breaks ties in favour of a less common
        # shared financial anchor, which prevents broad words such as 가치 or
        # 수익 from outranking a concrete overlap such as 채권 or 재고.
        eligible_records.sort(
            key=lambda item: (
                -int(item["displayedSharedAnchorCount"] > 0),
                int(item["minimumSharedAnchorDocumentFrequency"]),
                -len(item["sharedAnchorIds"]),
                -float(item["modelScore"]),
                str(item["sourceElementId"]),
            )
        )
        choices = eligible_records[:2]
        if len(choices) < 2:
            exceptions.append(
                {
                    "questionId": question.question_id,
                    "stage": "cross_concept",
                    "reasons": ["fewer-than-two-source-anchored-candidates"],
                    "record": {"selectedCount": len(choices)},
                }
            )
        selected[question.question_id] = choices
    return selected, exceptions


def _select_mutations_for_question(
    question: base.QuestionGroup,
    target: base.ElementRecord,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    generated = generate_mutations(
        question.correct_answer,
        base_fact_id=question.fact_id,
        target_element_id=question.element_id,
    )
    safe = [
        item
        for item in generated
        if item["autoReviewPassed"]
        and not base.text_mentions_title(item["text"], target.title)
        and not selected_mutation_lint_reasons(str(item["text"]))
    ]
    unsafe = [item for item in generated if not item["autoReviewPassed"]]
    selected: list[dict[str, Any]] = []
    categories: set[str] = set()
    for mutation in safe:
        if mutation["mutationCategory"] in categories:
            continue
        categories.add(str(mutation["mutationCategory"]))
        selected.append(mutation)
        if len(selected) == 2:
            break
    if len(selected) < 2:
        for mutation in safe:
            if mutation in selected:
                continue
            selected.append(mutation)
            if len(selected) == 2:
                break
    exceptions = []
    if len(selected) < 2:
        exceptions.append(
            {
                "questionId": question.question_id,
                "stage": "target_mutation",
                "reasons": ["fewer-than-two-auto-safe-mutations"],
                "record": {
                    "selectedCount": len(selected),
                    "unsafeCandidateCount": len(unsafe),
                    "unsafeCandidates": unsafe,
                },
            }
        )
    return selected, exceptions


def _attach_relation_mutation_metadata(
    mutation: Mapping[str, Any],
    relation: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(mutation)
    source_edges = [dict(item) for item in relation["relationEdges"]]
    if not source_edges:
        raise base.ConceptModelError("A relation mutation requires a source edge")
    mutated_edges = [dict(item) for item in source_edges]
    before_edge = dict(mutated_edges[0])
    after_edge = {
        **before_edge,
        "predicate": (
            f"{relation['relationType']}:mutation:"
            f"{mutation_rule_prefix(str(mutation['mutationRuleId']))}"
        ),
    }
    mutated_edges[0] = after_edge
    result.update(
        {
            "relationType": relation["relationType"],
            "participantIds": list(relation["participantIds"]),
            "roleBindings": dict(relation["roleBindings"]),
            "sourceRelationEdges": source_edges,
            "relationEdges": mutated_edges,
            "relationEvidence": dict(relation["relationEvidence"]),
            "changedRelation": {
                "operation": "replace_edge_predicate",
                "edgeIndex": 0,
                "beforeEdge": before_edge,
                "afterEdge": after_edge,
                "changedBindingOrEdgeCount": 1,
                "sourceMutationRuleId": mutation["mutationRuleId"],
            },
        }
    )
    return result


def _inverse_mutation(
    element_id: str,
    general_mutations: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Mapping[str, Any] | None:
    preferred = (
        f"{element_id}-term_to_verbal_relation-01",
        f"{element_id}-term_to_intuition-01",
        f"{element_id}-term_to_definition-01",
    )
    for question_id in preferred:
        mutations = general_mutations.get(question_id, ())
        if mutations:
            return mutations[0]
    return None


def _deterministic_choice_order(question_id: str, choices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        choices,
        key=lambda item: base._sha256_bytes(
            f"{question_id}:{item['text']}".encode("utf-8")
        ),
    )
    for key, item in zip(CHOICE_KEYS, ordered, strict=True):
        item["key"] = key
    return ordered


def _choice_source_counts(choices: Sequence[Mapping[str, Any]]) -> Counter[str]:
    return Counter(str(item.get("choiceSourceType")) for item in choices)


def hard_gate_reasons(question: Mapping[str, Any]) -> list[str]:
    """Apply the numerical hard gates copied from design sections 15-16."""

    reasons: list[str] = []
    choices = list(question["choices"])
    question_type = str(question["questionType"])
    target_id = str(question["elementId"])
    source_counts = _choice_source_counts(choices)
    if question_type not in {
        "term_to_definition",
        "term_to_intuition",
        "term_to_verbal_relation",
        "term_to_incorrect_statement",
    }:
        reasons.append("unsupported-question-type")
    if len(choices) != REFERENCE_GATE_THRESHOLDS["choiceCount"]:
        reasons.append("choice-count-not-five")
    if sum(bool(item.get("isAnswer")) for item in choices) != REFERENCE_GATE_THRESHOLDS["answerCount"]:
        reasons.append("answer-count-not-one")
    answer_choices = [item for item in choices if bool(item.get("isAnswer"))]
    if len(answer_choices) == 1 and question.get("answerChoiceKey") != answer_choices[0].get("key"):
        reasons.append("answer-choice-key-mismatch")
    if len({str(item.get("text")) for item in choices}) != len(choices):
        reasons.append("duplicate-choice-text")
    if any("statementTruth" not in item for item in choices):
        reasons.append("missing-statement-truth")
    if question_type == "term_to_incorrect_statement":
        if source_counts != Counter(
            {
                "target_fact": REFERENCE_GATE_THRESHOLDS["inverseTargetFactCount"],
                "target_mutation": REFERENCE_GATE_THRESHOLDS["inverseTargetMutationCount"],
            }
        ):
            reasons.append("inverse-source-composition-mismatch")
        if any(
            bool(item.get("isAnswer")) == bool(item.get("statementTruth"))
            for item in choices
        ):
            reasons.append("inverse-answer-truth-mismatch")
    elif source_counts != Counter(
        {
            "target_fact": REFERENCE_GATE_THRESHOLDS["generalTargetFactCount"],
            "cross_concept_fact": REFERENCE_GATE_THRESHOLDS[
                "generalCrossConceptFactCount"
            ],
            "target_mutation": REFERENCE_GATE_THRESHOLDS[
                "generalTargetMutationCount"
            ],
        }
    ):
        reasons.append("general-source-composition-mismatch")
    for choice in choices:
        source_type = str(choice.get("choiceSourceType"))
        text = str(choice.get("text", ""))
        if source_type == "cross_concept_fact":
            if str(choice.get("sourceElementId")) == target_id:
                reasons.append("cross-source-equals-target")
            if len(choice.get("sharedAnchorIds", [])) < REFERENCE_GATE_THRESHOLDS["minimumSharedAnchorCount"]:
                reasons.append("missing-shared-anchor")
            distinct = choice.get("distinctAxis", {})
            if not distinct.get("targetEvidence"):
                reasons.append("missing-target-distinct-axis")
            if not distinct.get("candidateEvidence"):
                reasons.append("missing-candidate-distinct-axis")
            if question_type == "term_to_definition":
                compatibility = choice.get("definitionRoleCompatibility", {})
                if not compatibility.get("allowed"):
                    reasons.append("definition-role-mismatch")
                for side in ("targetEvidence", "candidateEvidence"):
                    for evidence in compatibility.get(side, []):
                        if not all(
                            evidence.get(key)
                            for key in (
                                "evidenceText",
                                "sourceLocator",
                                "sourceSha256",
                            )
                        ):
                            reasons.append("definition-role-evidence-incomplete")
        elif source_type == "target_mutation":
            if str(choice.get("sourceElementId")) != target_id:
                reasons.append("mutation-source-not-target")
            if not all(
                choice.get(key)
                for key in (
                    "baseFactId",
                    "mutationRuleId",
                    "changedClaim",
                    "falsityRationale",
                    "sourceTruthText",
                )
            ):
                reasons.append("mutation-evidence-incomplete")
            if str(choice.get("changedClaim", "")).count("→") != 1:
                reasons.append("mutation-changed-span-count-not-one")
            reasons.extend(selected_mutation_lint_reasons(text))
        if base.text_mentions_title(text, str(question["elementTitle"])):
            reasons.append("target-name-exposure")
        if question_type == "term_to_verbal_relation":
            if base.FORMULA_CHOICE_RE.search(text):
                reasons.append("relation-formula-exposure")
            for key in (
                "relationType",
                "participantIds",
                "roleBindings",
                "relationEdges",
            ):
                if not choice.get(key):
                    reasons.append(f"relation-{key}-missing")
            if (
                len(choice.get("participantIds", []))
                < REFERENCE_GATE_THRESHOLDS["minimumRelationParticipantCount"]
            ):
                reasons.append("relation-participant-count-too-low")
            if (
                len(choice.get("relationEdges", []))
                < REFERENCE_GATE_THRESHOLDS["minimumRelationEdgeCount"]
            ):
                reasons.append("relation-edge-count-too-low")
            if source_type == "target_mutation":
                changed = choice.get("changedRelation", {})
                if changed.get("changedBindingOrEdgeCount") != 1:
                    reasons.append("relation-mutation-change-count-not-one")
    return sorted(set(reasons))


def soft_review_reasons(
    question: Mapping[str, Any],
    *,
    anchor_df_p75: int,
) -> list[str]:
    reasons: list[str] = []
    for choice in question["choices"]:
        if choice.get("choiceSourceType") == "cross_concept_fact":
            compatibility = choice.get("definitionRoleCompatibility") or {}
            if compatibility.get("reasonId") == "insufficient-source-evidence":
                reasons.append("definition-insufficient-source-evidence")
            if int(choice.get("minimumSharedAnchorDocumentFrequency", 0)) > anchor_df_p75:
                reasons.append("common-anchor-only")
            if int(choice.get("displayedSharedAnchorCount", 0)) == 0:
                reasons.append("no-displayed-fact-anchor-overlap")
    return sorted(set(reasons))


def soft_review_measurements(
    question: Mapping[str, Any],
    *,
    anchor_df_p75: int,
) -> list[dict[str, Any]]:
    """Record the exact candidate values that triggered a soft exception."""

    measurements: list[dict[str, Any]] = []
    for choice in question["choices"]:
        if choice.get("choiceSourceType") != "cross_concept_fact":
            continue
        compatibility = choice.get("definitionRoleCompatibility") or {}
        reason_ids: list[str] = []
        if compatibility.get("reasonId") == "insufficient-source-evidence":
            reason_ids.append("definition-insufficient-source-evidence")
        minimum_df = int(choice.get("minimumSharedAnchorDocumentFrequency", 0))
        if minimum_df > anchor_df_p75:
            reason_ids.append("common-anchor-only")
        displayed_count = int(choice.get("displayedSharedAnchorCount", 0))
        if displayed_count == 0:
            reason_ids.append("no-displayed-fact-anchor-overlap")
        if reason_ids:
            measurements.append(
                {
                    "sourceElementId": choice.get("sourceElementId"),
                    "sourceElementTitle": choice.get("sourceElementTitle"),
                    "reasonIds": reason_ids,
                    "minimumSharedAnchorDocumentFrequency": minimum_df,
                    "anchorDocumentFrequencyP75": anchor_df_p75,
                    "displayedSharedAnchorCount": displayed_count,
                    "displayedSharedAnchorIds": list(
                        choice.get("displayedSharedAnchorIds", [])
                    ),
                    "definitionRoleReasonId": compatibility.get("reasonId"),
                }
            )
    return measurements


def build_complete_preview(
    *,
    selected_experiment_path: Path = DEFAULT_SELECTED_EXPERIMENT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    device: str = "cpu",
) -> dict[str, Any]:
    output, _ = experiment._output_policy(output_dir, experiment.DEFAULT_BUILD_DIR)
    config = base._load_json_object(base.DEFAULT_CONFIG)
    selected_experiment = _selected_experiment(selected_experiment_path)
    selection = selected_experiment["selection"]
    elements = base.load_elements()
    raw_by_id = load_raw_elements()
    assignments, split_manifest = base.build_split(elements, config)
    _, questions = base.build_facts_and_questions(elements, assignments)
    context = experiment.build_v3_feature_context(
        elements,
        questions,
        experiment._weak_profile(config),
        int(config["fusionBaseline"]["rrfK"]),
    )
    embedding = _embedding_for_selection(selection, context, config, device)
    profile = _profile_for_selection(selection)
    retrieved = base.retrieve_candidates(
        context,
        embedding,
        int(config.get("retrievalLimit", 30)),
        profile,
        int(config["fusionBaseline"]["rrfK"]),
    )
    model_path = base._resolve_repo_path(
        Path(selected_experiment["artifacts"]["selectedModel"])
    )
    if base._sha256_file(model_path) != str(selection["modelSha256"]):
        raise base.ConceptModelError("Selected v3 model hash does not match its report")
    ranker = joblib.load(model_path)
    ranked = base.rank_candidates(context, embedding, retrieved, ranker)
    anchors = {
        element.element_id: extract_anchor_evidence(
            element, raw_by_id[element.element_id]
        )
        for element in elements
    }
    gate_policy = reference_gate_policy(anchors)
    atomic_facts = {
        element.element_id: build_atomic_facts(
            element,
            raw_by_id[element.element_id],
            anchors[element.element_id],
        )
        for element in elements
    }
    cross_choices, cross_exceptions = _select_cross_concept_choices(
        context=context,
        ranked=ranked,
        anchors=anchors,
        embedding=embedding,
        ranker=ranker,
    )
    by_element = {item.element_id: item for item in elements}
    relation_by_element = {
        element.element_id: relation_metadata(
            element=element,
            text=base.display_fact_text(element, "verbal_relation"),
            anchor_ids=tuple(anchors[element.element_id]),
        )
        for element in elements
    }
    general_mutations: dict[str, list[dict[str, Any]]] = {}
    mutation_exceptions: list[dict[str, Any]] = []
    for question in questions:
        selected, exceptions = _select_mutations_for_question(
            question, by_element[question.element_id]
        )
        if question.question_type == "term_to_verbal_relation":
            selected = [
                _attach_relation_mutation_metadata(
                    item,
                    relation_by_element[question.element_id],
                )
                for item in selected
            ]
        general_mutations[question.question_id] = selected
        mutation_exceptions.extend(exceptions)

    if cross_exceptions or mutation_exceptions:
        raise base.ConceptModelError(
            "The complete preview cannot be assembled: "
            f"cross={len(cross_exceptions)}, mutation={len(mutation_exceptions)}"
        )
    preview_questions: list[dict[str, Any]] = []
    for question in questions:
        target = by_element[question.element_id]
        correct = {
            "choiceSourceType": "target_fact",
            "sourceElementId": target.element_id,
            "text": question.correct_answer,
            "statementTruth": True,
            "isAnswer": True,
            "factId": question.fact_id,
            "sourceLocator": target.source_locator,
            "sourceSha256": base._sha256_bytes(
                question.correct_answer.encode("utf-8")
            ),
        }
        if question.question_type == "term_to_verbal_relation":
            correct.update(
                {
                    key: relation_by_element[target.element_id][key]
                    for key in (
                        "relationType",
                        "participantIds",
                        "roleBindings",
                        "relationEdges",
                        "relationEvidence",
                    )
                }
            )
        mutations = [
            {
                **dict(item),
                "choiceSourceType": "target_mutation",
                "sourceElementId": target.element_id,
                "isAnswer": False,
            }
            for item in general_mutations[question.question_id]
        ]
        choices = [correct, *cross_choices[question.question_id], *mutations]
        preview_questions.append(
            {
                "questionId": question.question_id,
                "elementId": question.element_id,
                "elementTitle": target.title,
                "domainId": question.domain_id,
                "split": question.split,
                "questionType": question.question_type,
                "stem": question.stem,
                "choices": _deterministic_choice_order(question.question_id, choices)
                if len(choices) == 5
                else choices,
                "autoReviewPassed": False,
            }
        )

    for element in elements:
        question_id = f"{element.element_id}-term_to_incorrect_statement-01"
        facts = atomic_facts[element.element_id][:4]
        mutation = _inverse_mutation(element.element_id, general_mutations)
        choices = [
            {
                **dict(fact),
                "choiceSourceType": "target_fact",
                "sourceElementId": element.element_id,
                "isAnswer": False,
            }
            for fact in facts
        ]
        if mutation is not None:
            choices.append(
                {
                    **dict(mutation),
                    "choiceSourceType": "target_mutation",
                    "sourceElementId": element.element_id,
                    "isAnswer": True,
                }
            )
        preview_questions.append(
            {
                "questionId": question_id,
                "elementId": element.element_id,
                "elementTitle": element.title,
                "domainId": element.domain_id,
                "split": assignments[element.element_id],
                "questionType": "term_to_incorrect_statement",
                "stem": f"용어: {element.title}\n다음 중 이 용어에 관한 설명으로 옳지 않은 것은?",
                "choices": _deterministic_choice_order(question_id, choices)
                if len(choices) == 5
                else choices,
                "autoReviewPassed": False,
            }
        )

    for question in preview_questions:
        answer_choices = [item for item in question["choices"] if item.get("isAnswer")]
        question["answerChoiceKey"] = (
            answer_choices[0].get("key") if len(answer_choices) == 1 else None
        )

    question_counts_by_element = Counter(
        str(item["elementId"]) for item in preview_questions
    )
    wrong_element_counts = {
        element_id: count
        for element_id, count in question_counts_by_element.items()
        if count != REFERENCE_GATE_THRESHOLDS["questionsPerElement"]
    }
    missing_element_ids = sorted(
        set(by_element) - set(question_counts_by_element)
    )
    if (
        len(preview_questions) != REFERENCE_GATE_THRESHOLDS["questionCount"]
        or wrong_element_counts
        or missing_element_ids
    ):
        raise base.ConceptModelError(
            "Reference question-count gates failed; preview was not written: "
            + json.dumps(
                {
                    "questionCount": len(preview_questions),
                    "wrongElementCounts": wrong_element_counts,
                    "missingElementIds": missing_element_ids,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    hard_failures: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    anchor_df_p75 = int(gate_policy["anchorCorpus"]["documentFrequencyP75"])
    for question in preview_questions:
        hard_reasons = hard_gate_reasons(question)
        if hard_reasons:
            hard_failures.append(
                {
                    "questionId": question["questionId"],
                    "reasons": hard_reasons,
                }
            )
            continue
        review_reasons = soft_review_reasons(
            question,
            anchor_df_p75=anchor_df_p75,
        )
        question["autoReviewPassed"] = not review_reasons
        question["reviewReasons"] = review_reasons
        if review_reasons:
            measurements = soft_review_measurements(
                question,
                anchor_df_p75=anchor_df_p75,
            )
            exceptions.append(
                {
                    "questionId": question["questionId"],
                    "stage": "soft_review",
                    "reasons": review_reasons,
                    "record": {
                        "criteria": {
                            reason: SOFT_REVIEW_CRITERIA[reason]
                            for reason in review_reasons
                        },
                        "anchorDocumentFrequencyP75": anchor_df_p75,
                        "measurements": measurements,
                    },
                }
            )
    if hard_failures:
        summary = Counter(
            reason for failure in hard_failures for reason in failure["reasons"]
        )
        raise base.ConceptModelError(
            "Reference hard gates failed; preview was not written: "
            + json.dumps(dict(summary), ensure_ascii=False, sort_keys=True)
        )
    now = datetime.now(timezone.utc)
    preview_id = (
        f"cmq-v3-preview-{now.strftime('%Y%m%d-%H%M%S')}-"
        f"{str(selected_experiment['experimentId'])[-8:]}"
    )
    full_path = output / f"{preview_id}.json"
    full_md_path = output / f"{preview_id}-all-questions.md"
    exception_md_path = output / f"{preview_id}-review-exceptions.md"
    report_md_path = output / f"{preview_id}-report.md"
    preview = {
        "previewId": preview_id,
        "contractVersion": "3.1",
        "status": "preview_only",
        "releaseReady": False,
        "adminWritten": False,
        "questionBankWritten": False,
        "androidContentWritten": False,
        "selectedExperimentId": selected_experiment["experimentId"],
        "selection": selection,
        "referenceGatePolicy": gate_policy,
        "splitSha256": split_manifest["splitSha256"],
        "questionCount": len(preview_questions),
        "autoPassedQuestionCount": sum(
            bool(item["autoReviewPassed"]) for item in preview_questions
        ),
        "reviewQuestionCount": len(
            {item["questionId"] for item in exceptions}
        ),
        "exceptionCount": len(exceptions),
        "hardGateFailureCount": 0,
        "softReviewReasonCounts": dict(
            sorted(
                Counter(
                    reason
                    for item in exceptions
                    for reason in item["reasons"]
                ).items()
            )
        ),
        "questions": preview_questions,
        "exceptions": exceptions,
        "artifacts": {
            "jsonPreview": base._report_path(full_path),
            "allQuestionsMarkdown": base._report_path(full_md_path),
            "reviewExceptionsMarkdown": base._report_path(exception_md_path),
            "reportMarkdown": base._report_path(report_md_path),
        },
    }
    base._atomic_json(full_path, preview)
    base._atomic_text(full_md_path, render_all_questions(preview))
    base._atomic_text(exception_md_path, render_exception_review(preview))
    base._atomic_text(report_md_path, render_preview_report(preview))
    return preview


def _render_choice(choice: Mapping[str, Any]) -> list[str]:
    marker = "정답" if choice.get("isAnswer") else ""
    truth = "참" if choice.get("statementTruth") else "거짓"
    source_type = str(choice.get("choiceSourceType", "unknown"))
    lines = [
        f"- **{choice.get('key', '?')}.** {choice['text']} `[{source_type}·{truth}{'·' + marker if marker else ''}]`"
    ]
    if source_type == "cross_concept_fact":
        labels = ", ".join(
            str(item["label"]) for item in choice.get("sharedAnchors", [])
        )
        lines.append(
            f"  - 출처: `{choice['sourceElementId']}` {choice['sourceElementTitle']} / 공유 앵커: {labels}"
        )
        lines.append(f"  - 구별축: {choice['distinctnessRationale']}")
    elif source_type == "target_mutation":
        lines.append(
            f"  - 변형: `{choice['changedClaim']}` / {choice['falsityRationale']}"
        )
    return lines


def _render_gate_policy(preview: Mapping[str, Any]) -> list[str]:
    policy = preview["referenceGatePolicy"]
    thresholds = policy["hardGateThresholds"]
    corpus = policy["anchorCorpus"]
    reason_counts = preview["softReviewReasonCounts"]
    lines = [
        "## 레퍼런스 기반 판정 기준",
        "",
        f"- 기준 문서: `{policy['referencePath']}` 5.1~5.3, 6, 11.2~11.4, 15~16절",
        f"- 정책 ID: `{policy['policyId']}`",
        "- 하드 게이트 위반 처리: 생성 중단, 산출물 미작성",
        "- 소프트 예외 처리: 하드 게이트 통과 후 해당 문항만 검수 큐에 포함",
        "- 예외 수는 목표 검수율이나 모델 점수로 맞추지 않음",
        "",
        "### 하드 게이트 수치",
        "",
        "| 검사 | 기준 | 이번 실행 |",
        "|---|---:|---:|",
        f"| 전체 문항 | {thresholds['questionCount']} | {preview['questionCount']} |",
        f"| 요소별 문항 | {thresholds['questionsPerElement']} | {thresholds['questionsPerElement']} |",
        f"| 문항당 선지 | {thresholds['choiceCount']} | {thresholds['choiceCount']} |",
        f"| 문항당 정답 | {thresholds['answerCount']} | {thresholds['answerCount']} |",
        (
            "| 일반형 구성 | "
            f"{thresholds['generalTargetFactCount']}+"
            f"{thresholds['generalCrossConceptFactCount']}+"
            f"{thresholds['generalTargetMutationCount']} | 일치 |"
        ),
        (
            "| 옳지 않은 것 구성 | "
            f"참 {thresholds['inverseTargetFactCount']}+거짓 "
            f"{thresholds['inverseTargetMutationCount']} | 일치 |"
        ),
        f"| 타개념 공유 앵커 | ≥ {thresholds['minimumSharedAnchorCount']} | 일치 |",
        (
            "| 대상/후보 구별축 | 각각 ≥ "
            f"{thresholds['minimumTargetDistinctAxisCount']}/"
            f"{thresholds['minimumCandidateDistinctAxisCount']} | 일치 |"
        ),
        f"| 변형 변경 구절 | = {thresholds['mutationChangedSpanCount']} | 일치 |",
        (
            "| 관계 참여 ID/간선 | 각각 ≥ "
            f"{thresholds['minimumRelationParticipantCount']}/"
            f"{thresholds['minimumRelationEdgeCount']} | 일치 |"
        ),
        (
            "| 관계 변형 변경 바인딩·간선 | = "
            f"{thresholds['maximumRelationMutationChangedBindingOrEdgeCount']} | 일치 |"
        ),
        (
            "| 개념명/수식/중복 노출 | 각각 ≤ "
            f"{thresholds['maximumConceptNameExposureCount']}/"
            f"{thresholds['maximumFormulaExposureCount']}/"
            f"{thresholds['maximumDuplicateChoiceTextCount']} | 0/0/0 |"
        ),
        f"| 하드 게이트 실패 | 0 | {preview['hardGateFailureCount']} |",
        "",
        "### 코퍼스 기반 소프트 예외 수치",
        "",
        (
            f"- 코퍼스: 요소 {corpus['elementCount']}개, 실제 출현 앵커 "
            f"{corpus['anchorVocabularyCount']}개"
        ),
        (
            f"- p75 방식: `{corpus['nearestRankFormula']}` → "
            f"`ceil(0.75 × {corpus['anchorVocabularyCount']}) = "
            f"{corpus['nearestRank']}`번째 값"
        ),
        f"- 산출된 앵커 문서빈도 p75: **{corpus['documentFrequencyP75']}개 요소**",
        "",
        "| 예외 ID | 구체 판정식 | 이번 문항 수 |",
        "|---|---|---:|",
    ]
    for reason_id, description in policy["softReviewCriteria"].items():
        formula = policy["softReviewFormulas"][reason_id]
        count = int(reason_counts.get(reason_id, 0))
        lines.append(
            f"| `{reason_id}` | {description}; `{formula}` | {count} |"
        )
    lines.extend(
        (
            "",
            "> `common-anchor-only`의 p75는 설계서 12.1의 문장 핵심부·구별 가능성 "
            "감사를 코퍼스에 맞춰 수치화한 소프트 기준이다. 공유 앵커 ≥1이라는 "
            "설계 하드 게이트를 대체하지 않는다.",
            "",
        )
    )
    return lines


def render_all_questions(preview: Mapping[str, Any]) -> str:
    lines = [
        f"# {preview['previewId']} 전체 문항 미리보기",
        "",
        "> Admin 미반영 v3.1 완성 문항 미리보기다. 검수 대상만 보려면 예외 검수 문서를 사용한다.",
        "",
        f"- 전체 문항: {preview['questionCount']}개",
        f"- 자동 통과: {preview['autoPassedQuestionCount']}개",
        f"- 검수 문항: {preview['reviewQuestionCount']}개",
        "",
    ]
    current_domain = None
    for question in preview["questions"]:
        if question["domainId"] != current_domain:
            current_domain = question["domainId"]
            lines.extend((f"## {current_domain}", ""))
        status = "자동 통과" if question["autoReviewPassed"] else "검수 필요"
        lines.extend(
            (
                f"### {question['questionId']} · {question['elementTitle']}",
                "",
                f"- 상태: **{status}** / 유형: `{question['questionType']}` / 분할: `{question['split']}`",
                f"- 문제: {str(question['stem']).replace(chr(10), ' — ')}",
                "",
            )
        )
        for choice in question["choices"]:
            lines.extend(_render_choice(choice))
        lines.append("")
    return "\n".join(lines)


def render_exception_review(preview: Mapping[str, Any]) -> str:
    exception_by_question: dict[str, list[Mapping[str, Any]]] = {}
    for item in preview["exceptions"]:
        exception_by_question.setdefault(str(item["questionId"]), []).append(item)
    question_by_id = {
        str(item["questionId"]): item for item in preview["questions"]
    }
    lines = [
        f"# {preview['previewId']} 예외 검수",
        "",
        "> 540문항을 모두 생성·자동 검사한 뒤 통과하지 못한 문항만 모은 검수 큐다.",
        "",
        f"- 전체 문항: {preview['questionCount']}개",
        f"- 자동 통과: {preview['autoPassedQuestionCount']}개",
        f"- 검수 문항: {preview['reviewQuestionCount']}개",
        f"- 예외 레코드: {preview['exceptionCount']}건",
        "",
    ]
    lines.extend(_render_gate_policy(preview))
    if not exception_by_question:
        lines.extend(("검수할 예외가 없다.", ""))
        return "\n".join(lines)
    for question_id in sorted(exception_by_question):
        question = question_by_id[question_id]
        reasons = sorted(
            {
                reason
                for item in exception_by_question[question_id]
                for reason in item["reasons"]
            }
        )
        lines.extend(
            (
                f"## {question_id} · {question['elementTitle']}",
                "",
                f"- 사유: {', '.join(f'`{item}`' for item in reasons)}",
                f"- 문제: {str(question['stem']).replace(chr(10), ' — ')}",
            )
        )
        measurements = [
            measurement
            for item in exception_by_question[question_id]
            for measurement in item.get("record", {}).get("measurements", [])
        ]
        for measurement in measurements:
            lines.append(
                "- 판정값: "
                f"`{measurement['sourceElementId']}` / "
                "공유 앵커 최소 문서빈도 "
                f"**{measurement['minimumSharedAnchorDocumentFrequency']}** "
                f"(p75 **{measurement['anchorDocumentFrequencyP75']}**) / "
                "표시 문장 공유 앵커 "
                f"**{measurement['displayedSharedAnchorCount']}개** / "
                "사유 "
                + ", ".join(
                    f"`{reason_id}`" for reason_id in measurement["reasonIds"]
                )
            )
        lines.append("")
        for choice in question["choices"]:
            lines.extend(_render_choice(choice))
        lines.append("")
    return "\n".join(lines)


def render_preview_report(preview: Mapping[str, Any]) -> str:
    selection = preview["selection"]
    lines = [
        f"# {preview['previewId']} 생성 보고서",
        "",
        f"- 상태: `{preview['status']}` / 릴리스 불가",
        f"- 전체 문항: {preview['questionCount']}개",
        f"- 자동 통과: {preview['autoPassedQuestionCount']}개",
        f"- 검수 문항: {preview['reviewQuestionCount']}개",
        f"- 예외 레코드: {preview['exceptionCount']}건",
        f"- 선택 모델: `{selection['embeddingId']}/{selection['retrievalProfileId']}/{selection['rankerId']}`",
        "- 일반형 구성: 대상 참 1 + 출처 앵커가 있는 타개념 참 2 + 출처 문장 단일 변형 거짓 2",
        "- 역문항 구성: 대상 참 4 + 출처 문장 단일 변형 거짓 1",
        "- 공유 앵커: 양쪽 출처 텍스트에서 명시적으로 검출된 금융 주제·역할만 사용",
        "- 구별축: 대상과 후보 각각에만 존재하는 출처 앵커 및 실제 근거 구절 사용",
        "- 변형: 완전 구절 또는 문법 안전성이 검토된 방향·조건 치환만 자동 통과",
        "- Admin/Supabase/문항은행/Android 반영: 없음",
        "",
    ]
    lines.extend(_render_gate_policy(preview))
    lines.extend(
        (
            "## 산출물",
            "",
            f"- [전체 문항]({Path(preview['artifacts']['allQuestionsMarkdown']).name})",
            f"- [예외 검수]({Path(preview['artifacts']['reviewExceptionsMarkdown']).name})",
            "",
        )
    )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-coverage", action="store_true")
    parser.add_argument(
        "--selected-experiment", type=Path, default=DEFAULT_SELECTED_EXPERIMENT
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--device", default="cpu")
    return parser.parse_args(argv)


def audit_coverage() -> dict[str, Any]:
    config = base._load_json_object(base.DEFAULT_CONFIG)
    elements = base.load_elements()
    assignments, _ = base.build_split(elements, config)
    _, questions = base.build_facts_and_questions(elements, assignments)
    raw_values = json.loads(DEFAULT_RAW_ELEMENTS.read_text(encoding="utf-8"))
    raw_by_id = {str(item["elementId"]): item for item in raw_values}
    anchor_map = {
        item.element_id: extract_anchor_evidence(item, raw_by_id[item.element_id])
        for item in elements
    }
    candidate_capacity = {}
    for question in questions:
        target_ids = set(anchor_map[question.element_id])
        count = 0
        for candidate_index in base.eligible_candidate_indices(
            elements, question.element_index, question.question_type
        ):
            candidate = elements[candidate_index]
            candidate_ids = set(anchor_map[candidate.element_id])
            if target_ids & candidate_ids and target_ids - candidate_ids and candidate_ids - target_ids:
                count += 1
        candidate_capacity[question.question_id] = count
    mutation_capacity = {
        question.question_id: len(
            generate_mutations(
                question.correct_answer,
                base_fact_id=question.fact_id,
                target_element_id=question.element_id,
            )
        )
        for question in questions
    }
    report = {
        "anchorCountByElement": {
            element_id: len(items) for element_id, items in anchor_map.items()
        },
        "minimumAnchorCandidateCapacity": min(candidate_capacity.values()),
        "questionsWithFewerThanTwoAnchorCandidates": [
            question_id for question_id, count in candidate_capacity.items() if count < 2
        ],
        "mutationCapacityCounts": dict(Counter(mutation_capacity.values())),
        "questionsWithFewerThanTwoMutations": [
            question_id for question_id, count in mutation_capacity.items() if count < 2
        ],
    }
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.audit_coverage:
        print(json.dumps(audit_coverage(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    preview = build_complete_preview(
        selected_experiment_path=args.selected_experiment,
        output_dir=args.output_dir,
        device=args.device,
    )
    print(
        json.dumps(
            {
                "previewId": preview["previewId"],
                "questionCount": preview["questionCount"],
                "autoPassedQuestionCount": preview["autoPassedQuestionCount"],
                "reviewQuestionCount": preview["reviewQuestionCount"],
                "artifacts": preview["artifacts"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
