"""Offline, source-bound professional language candidates for English news.

This is a small curated index, not a CEFR list. Reference URLs identify an
official terminology source or a dictionary's published business usage. The
short Korean glosses and reusable patterns are editorial translations; no
source definitions or example sentences are copied. Candidate contexts always
come from the supplied article, and long or incomplete sentences are omitted.
Automatic vocabulary uses a closed list of specialist financial concepts and
business terms. Standalone investment bank, ETF, hedge fund, reinsurance,
prediction market and profit margin labels are intentionally excluded, even
when fewer than four candidates remain.
Named reinsurance mechanisms and retrocession remain eligible. This selection
does not restrict manual saving of an expression from an article.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


MAX_ARTICLE_CHARS = 20_000
MAX_CONTEXT_CHARS = 700
MAX_CONTEXT_WORDS = 40

NAIC_GLOSSARY = "https://content.naic.org/glossary-insurance-terms"
NAIC_GROUPS = "https://content.naic.org/insurance-topics/internationally-active-insurance-group"
NAIC_RBC = "https://content.naic.org/cipr_topics/topic_risk_based_capital.htm"
NAIC_PROFITS = "https://content.naic.org/publications"
CFA_INSTITUTIONS = "https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/analysis-of-financial-institutions"
CFA_PORTFOLIOS = "https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/portfolio-management-institutional-investors"
CFA_FLOWS = "https://rpc.cfainstitute.org/research/reports/2024/responsible-investment-funds"
CFA_FIXED_INCOME = "https://www.cfainstitute.org/sites/default/files/-/media/documents/book/curriculum-update/rr-v-2017-n2-1.pdf"
SIFMA_BROKERS = "https://www.sifma.org/about"
BIS_BASEL = "https://www.bis.org/committees/bcbs/basel-framework"
BIS_MONETARY = "https://www.bis.org/publications/aer-2024/monetary-policy-21st-century-lessons-learned-challenges-ahead"
CFA_ALTERNATIVES = "https://www.cfainstitute.org/sites/default/files/-/media/documents/book/rf-publication/2015/rf-v2015-n5-1-pdf.pdf"
CFA_PRIVATE_CREDIT = "https://rpc.cfainstitute.org/research/reports/2026/private-credit-market-structure-fund-design-retail-access"
CFA_SUCCESSION = "https://www.cfainstitute.org/insights/articles/succession-planning-for-financial-advisors"
SEC_BLOCK_TRADES = "https://www.sec.gov/files/litigation/admin/2024/34-99336.pdf"
SEC_INSTITUTIONAL_LIQUIDITY = "https://www.sec.gov/rules/sro/nyse/2013/34-70909.pdf"
CFTC_PREDICTION_MARKETS = "https://www.cftc.gov/LearnandProtect/PredictionMarkets"
HFMA_CODING = "https://www.hfma.org/data-and-insights/peer-review/"
CMS_SECONDARY_DIAGNOSES = "https://www.cms.gov/outreach-and-education/mln/wbt/mln7388180-mln-wbt-1450/1450/lesson05/23/index.html"
HFMA_REVENUE_CYCLE = "https://www.hfma.org/data-and-insights/map-initiative/map-keys/"
HFMA_AUTONOMOUS_CODING = "https://www.hfma.org/wp-content/uploads/2024/04/spring2024day2-newmexico.pdf"


@dataclass(frozen=True)
class LanguageCandidate:
    candidate_id: str
    term: str
    lemma: str
    context: str
    reference: str
    category: str
    meaning_ko: str
    reuse_pattern: str = ""
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class _Entry:
    lemma: str
    pattern: str
    meaning_ko: str
    reference: str
    category: str
    priority: int = 0
    reuse_pattern: str = ""
    guard: str = ""


# Only named variants are accepted. A hyphen is not a general stemming rule.
_SPACE = r"[^\S\r\n]+"
_GLOSSARY = (
    _Entry("combined ratio", r"combined ratios?", "합산비율", NAIC_GLOSSARY, "insurance"),
    _Entry("underwriting profit", r"underwriting profits?", "보험영업이익", NAIC_PROFITS, "insurance"),
    _Entry("gross written premiums", r"gross (?:written premiums?|premiums? written)", "총수입보험료", NAIC_GROUPS, "insurance"),
    _Entry("excess of loss reinsurance", r"excess(?: of loss|[-\u2010\u2011]of[-\u2010\u2011]loss) reinsurance", "초과손해 재보험", NAIC_GLOSSARY, "insurance"),
    _Entry("facultative reinsurance", r"facultative reinsurance", "임의재보험", NAIC_GLOSSARY, "insurance"),
    _Entry("loss adjustment expense", r"loss adjustment expenses?", "손해사정비용", NAIC_GLOSSARY, "insurance"),
    _Entry("ceded premium", r"ceded premiums?", "출재보험료", NAIC_GLOSSARY, "insurance"),
    _Entry("loss reserve", r"loss reserves?", "지급준비금", NAIC_GLOSSARY, "insurance"),
    _Entry("risk-based capital", r"risk(?:[-\u2010\u2011]| )based capital", "위험기준자본", NAIC_RBC, "insurance"),
    _Entry("unearned premium reserve", r"unearned premium reserves?", "미경과보험료적립금", NAIC_GLOSSARY, "insurance"),
    _Entry("medical coding", r"medical coding", "진단·진료를 청구용 표준코드로 변환", HFMA_CODING, "insurance"),
    _Entry("secondary diagnosis", r"secondary diagnos(?:is|es)", "주진단 외 동반·추가 진단", CMS_SECONDARY_DIAGNOSES, "insurance"),
    _Entry("revenue cycle management", r"revenue(?:[-\u2010\u2011]| )cycle management", "진료기록·청구·대금회수 전반의 수입관리", HFMA_REVENUE_CYCLE, "insurance"),
    _Entry("autonomous medical coding", r"autonomous(?: medical)? coding", "인간 검토 없는 자동코딩", HFMA_AUTONOMOUS_CODING, "insurance"),
    _Entry("broker-dealer", r"broker(?:[-\u2010\u2011]| )dealers?", "증권 중개·매매업자", SIFMA_BROKERS, "capital_markets"),
    _Entry("assets under management", r"assets under management", "운용자산", CFA_PORTFOLIOS, "asset_management"),
    _Entry("net inflows", r"net inflows?", "순유입액", CFA_FLOWS, "asset_management"),
    _Entry("capital adequacy", r"capital adequacy", "자본적정성", CFA_INSTITUTIONS, "banking"),
    _Entry("liquidity coverage ratio", r"liquidity coverage ratios?", "유동성커버리지비율", BIS_BASEL, "banking"),
    _Entry("net stable funding ratio", r"net stable funding ratios?", "순안정자금조달비율", BIS_BASEL, "banking"),
    _Entry("non-performing loan", r"non(?:[-\u2010\u2011]| )performing loans?", "부실채권", BIS_BASEL, "banking"),
    _Entry("credit spread", r"credit spreads?", "신용스프레드", CFA_FIXED_INCOME, "capital_markets"),
    _Entry("liquidity premium", r"liquidity premi(?:um|ums|a)", "유동성프리미엄", CFA_FIXED_INCOME, "capital_markets"),
    _Entry("yield curve", r"yield curves?", "수익률곡선", CFA_FIXED_INCOME, "capital_markets"),
    _Entry("quantitative tightening", r"quantitative tightening", "양적긴축", BIS_MONETARY, "banking"),
    _Entry("term premium", r"term premi(?:um|ums|a)", "기간프리미엄", BIS_MONETARY, "capital_markets"),
    _Entry("net interest margin", r"net interest margins?", "순이자마진", BIS_MONETARY, "banking"),
    _Entry("succession planning", r"succession (?:plans?|planning)", "경영진·사업 승계계획", CFA_SUCCESSION, "capital_markets"),
    _Entry("pure play", r"pure(?:[-\u2010\u2011]| )play", "특정 사업에 집중한 기업·사업모델", "https://dictionary.cambridge.org/dictionary/english/pure-play", "capital_markets"),
    _Entry("alternative asset manager", r"alternative asset managers?", "대체자산 운용사", CFA_ALTERNATIVES, "asset_management"),
    _Entry("alternative asset management", r"alternative asset management", "대체자산 운용", CFA_ALTERNATIVES, "asset_management"),
    _Entry("private credit", r"private credit", "비상장 사모대출", CFA_PRIVATE_CREDIT, "asset_management"),
    _Entry("investment banking fee", r"investment banking fees?", "투자은행 수수료 수익", "https://www.sifma.org/wp-content/uploads/2022/07/CM-Fact-Book-2022-SIFMA.pdf", "capital_markets"),
    _Entry("block trade", r"block trades?", "대량 협의매매", SEC_BLOCK_TRADES, "capital_markets"),
    _Entry("institutional liquidity", r"institutional liquidity", "기관투자자가 공급하는 거래 유동성", SEC_INSTITUTIONAL_LIQUIDITY, "capital_markets"),
    _Entry("event contract", r"event contracts?", "사건 결과에 따라 정산되는 계약", CFTC_PREDICTION_MARKETS, "capital_markets"),
    # Prefer named multiword concepts; retrocession remains a specialist term.
    _Entry("retrocession", r"retrocessions?", "재재보험", NAIC_GLOSSARY, "insurance", priority=1),
)

_PHRASES = (
    _Entry("raise capital", r"rais(?:e|es|ed|ing) capital", "자본을 조달하다", "https://dictionary.cambridge.org/dictionary/english/raise-money-funds-capital-etc", "business_phrase", reuse_pattern="raise capital to + 동사"),
    _Entry("shore up", r"shor(?:e|es|ed|ing) up", "재무 기반을 보강하다", "https://dictionary.cambridge.org/dictionary/english/shore-up", "business_phrase", reuse_pattern="shore up + 보강할 대상", guard="shore"),
    _Entry("weigh on", r"weigh(?:s|ed|ing)?(?: heavily)? on", "실적·시장에 부담을 주다", "https://dictionary.cambridge.org/dictionary/english/weigh-on", "business_phrase", reuse_pattern="악재 + weigh on + 영향받는 대상", guard="weigh"),
    _Entry("beat estimates", r"beat(?:s|ing|en)? (?:(?:analysts?[’']|consensus) )?(?:estimates|expectations|forecasts)", "예상치를 웃돌다", "https://dictionary.cambridge.org/us/dictionary/english/beat", "business_phrase", reuse_pattern="실적 + beat + estimates / expectations"),
    _Entry("under pressure", r"under(?: (?:increasing|sustained|severe))? pressure", "경영·시장 압박을 받는", "https://www.oxfordlearnersdictionaries.co.uk/definition/english/pressure_1", "business_phrase", reuse_pattern="대상 + be / remain + under pressure", guard="pressure"),
    _Entry("book a loss", r"book(?:s|ed|ing)? (?:a loss|losses)", "손실을 장부에 반영하다", "https://www.collinsdictionary.com/dictionary/english/book", "business_phrase", reuse_pattern="book a loss on + 손실이 난 거래"),
    _Entry("back on track", r"back on track", "사업·계획이 정상 궤도로 돌아온", "https://dictionary.cambridge.org/us/dictionary/english/on-track", "business_phrase", reuse_pattern="get / put + 대상 + back on track", guard="track"),
    _Entry("on the sidelines", r"on the sidelines", "참여하지 않고 관망하는", "https://dictionary.cambridge.org/dictionary/english/sideline", "business_phrase", reuse_pattern="stay / wait / sit + on the sidelines"),
    _Entry("at an inflection point", r"at (?:an|a strategic) inflection point", "사업·시장이 중요한 전환점에 있는", "https://dictionary.cambridge.org/us/dictionary/english/inflection-point", "business_phrase", reuse_pattern="사업·시장 + be + at an inflection point", guard="inflection"),
    _Entry("make a play for", r"(?:mak(?:e|es|ing)|made) a play for", "확보·영입을 위해 움직이다", "https://www.collinsdictionary.com/dictionary/english/make-a-play-for", "business_phrase", reuse_pattern="make a play for + 확보할 대상", guard="play"),
    _Entry("lame duck", r"lame(?:[-\u2010\u2011]| )ducks?", "실권·영향력을 잃은 인물·조직", "https://dictionary.cambridge.org/us/dictionary/english/lame-duck", "business_phrase", reuse_pattern="become / be seen as + a lame duck", guard="leader"),
    _Entry("push into", r"push(?:es|ed|ing)? into", "새 시장·사업 진출을 추진하다", "https://dictionary.cambridge.org/us/dictionary/english/push", "business_phrase", reuse_pattern="make a push into + 진출할 시장", guard="push"),
    _Entry("double down on", r"doubl(?:e|es|ed|ing) down on", "기존 전략에 자원·노력을 더 투입하다", "https://www.dictionary.com/browse/double-down", "business_phrase", reuse_pattern="double down on + 집중할 전략"),
    _Entry("at stake", r"at stake", "성패에 따라 잃을 수 있는", "https://dictionary.cambridge.org/dictionary/english/at-stake", "business_phrase", reuse_pattern="위험에 놓인 가치 + be + at stake"),
    _Entry("push back on", r"push(?:es|ed|ing)? back on", "주장·방침에 이의를 제기하다", "https://www.oxfordlearnersdictionaries.com/definition/english/push-back", "business_phrase", reuse_pattern="push back on + 주장·분석·제안", guard="push_back"),
)

_BUSINESS = re.compile(
    r"\b(?:banks?|banking|insurers?|insurance|brokers?|companies|company|business|capital|"
    r"profits?|earnings|revenues?|margins?|markets?|shares?|stocks?|bonds?|funds?|"
    r"investors?|currency|currencies|dollar|euro|pound|rupee|economy|growth|"
    r"inflation|liquidity|reserves?|financial|finances|debt|costs?|assets?|"
    r"ceo|boards?|executives?|suitors?|contracts?|exchanges?|traders?|hospitals?|healthcare)\b", re.I,
)
_SHORE_TARGET = re.compile(
    r"\s+(?:(?:its|their|the|our|a)\s+){0,2}(?:capital|balance sheets?|"
    r"financial position|finances|liquidity|reserves?|currency|rupee|dollar|"
    r"euro|business|economy|confidence|funds?|banks?)\b", re.I,
)
_WEIGH_TARGET = re.compile(
    r"\s+(?:(?:the|its|their|our|a|an|bank|insurer)[’']?s?\s+){0,2}"
    r"(?:profits?|earnings|revenues?|margins?|markets?|shares?|stocks?|bonds?|"
    r"growth|economy|banks?|insurers?|prices?|returns?|demand|investment)\b", re.I,
)
_PUSH_BACK_TARGET = re.compile(
    r"\s+(?:(?:the|this|that|its|their|our|a|an)\s+){0,2}"
    r"(?:[A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*){0,2}[’']s?\s+)?"
    r"(?:(?:proposed|planned|new)\s+)?"
    r"(?:analysis|analyses|claims?|findings|proposals?|plans?|rules|polic(?:y|ies)|"
    r"changes?|criticism|requirements|decisions?|(?:rate|premium|cost) increases?)\b", re.I,
)
_ABBREVIATIONS = frozenset({"mr.", "mrs.", "ms.", "dr.", "prof.", "inc.", "co.", "ltd.", "jr.", "sr.", "no.", "e.g.", "i.e.", "etc."})


def _bounded_limit(text: str, limit: int, maximum: int) -> int:
    if not isinstance(text, str) or len(text) > MAX_ARTICLE_CHARS:
        raise ValueError("Language candidates require at most 20,000 article characters")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("Candidate limit must be a nonnegative integer")
    return min(limit, maximum)


def _sentence_spans(text: str):
    """Yield exact complete sentence offsets; never cut an oversized sentence."""
    for line in re.finditer(r"[^\r\n]+", text):
        value = line.group()
        start = 0
        for boundary in re.finditer(r"[.!?][\"'’”\])]*(?=\s|$)", value):
            punctuation = boundary.start()
            if value[punctuation] == "." and boundary.end() < len(value):
                token = re.search(r"[A-Za-z][A-Za-z.]*\.$", value[:punctuation + 1])
                if token and (token.group().casefold() in _ABBREVIATIONS
                              or re.fullmatch(r"(?:[A-Za-z]\.)+", token.group())):
                    continue
            left = start
            while left < boundary.end() and value[left].isspace():
                left += 1
            right = boundary.end()
            sentence = value[left:right]
            start = right
            if (sentence and len(sentence) <= MAX_CONTEXT_CHARS
                    and len(sentence.split()) <= MAX_CONTEXT_WORDS
                    and not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]|https?://|www\.", sentence, re.I)):
                yield line.start() + left, line.start() + right


def _pattern(entry: _Entry) -> re.Pattern[str]:
    # Horizontal whitespace variants retain the exact span in the returned term.
    pattern = entry.pattern.replace(" ", _SPACE)
    return re.compile(r"(?<![\w\u2010\u2011-])(?:" + pattern + r")(?![\w\u2010\u2011-])", re.I)


def _phrase_has_business_sense(entry: _Entry, sentence: str, match: re.Match[str]) -> bool:
    if not _BUSINESS.search(sentence):
        return False
    suffix = sentence[match.end():]
    if entry.guard == "shore":
        return bool(_SHORE_TARGET.match(suffix))
    if entry.guard == "weigh":
        return bool(_WEIGH_TARGET.match(suffix))
    if entry.guard == "pressure":
        return not re.search(r"\b(?:steam|gases?|liquids?|boiler|container|tank|blood)\b", sentence, re.I)
    if entry.guard == "track":
        return not re.search(r"\b(?:train|railway|railroad|racetrack|racing|racecourse)\b", sentence, re.I)
    if entry.guard == "inflection":
        return not re.search(r"\b(?:calculus|derivative|curvature|mathematical|graph|function)\b", sentence, re.I)
    if entry.guard == "play":
        return not re.search(r"\b(?:girlfriend|boyfriend|romance|romantic|dating)\b", sentence, re.I)
    if entry.guard == "leader":
        return bool(re.search(r"\b(?:ceo|executive|chairman|chair|leader|leadership|bank|company|board|director|chief|authority|retir\w*)\b", sentence, re.I))
    if entry.guard == "push":
        return bool(re.match(r"\s+(?:(?:the|its|new|a|an)\s+){0,2}(?:[A-Z][\w-]*\s+)?(?:markets?|business|banking|insurance|lending|credit|asset management|wealth management)\b", suffix, re.I))
    if entry.guard == "push_back":
        return bool(_PUSH_BACK_TARGET.match(suffix))
    return True


def _select(text: str, entries: tuple[_Entry, ...], limit: int, *, phrases: bool) -> tuple[LanguageCandidate, ...]:
    found = []
    patterns = tuple((entry, _pattern(entry)) for entry in entries)
    for left, right in _sentence_spans(text):
        sentence = text[left:right]
        for entry, pattern in patterns:
            for match in pattern.finditer(sentence):
                if phrases and not _phrase_has_business_sense(entry, sentence, match):
                    continue
                found.append((entry.priority, left + match.start(), left + match.end(), entry, sentence))
    # Keep a longer named term instead of also offering its nested noun.
    ordered = sorted(found, key=lambda item: (item[0], item[1], -(item[2] - item[1]), item[3].lemma))
    selected = []
    seen = set()
    occupied = []
    for _, start, end, entry, context in ordered:
        if entry.lemma in seen or any(start < prior_end and end > prior_start for prior_start, prior_end in occupied):
            continue
        fingerprint = hashlib.sha256(f"{entry.category}\0{entry.lemma}\0{start}\0{end}\0{context}".encode("utf-8")).hexdigest()[:24]
        selected.append(LanguageCandidate(fingerprint, text[start:end], entry.lemma, context, entry.reference,
                                          entry.category, entry.meaning_ko, entry.reuse_pattern, start, end))
        seen.add(entry.lemma)
        occupied.append((start, end))
        if len(selected) >= limit:
            break
    return tuple(selected)


def select_specialist_vocabulary(text: str, limit: int = 4) -> tuple[LanguageCandidate, ...]:
    """Return up to four specialist terms without basic industry-label padding."""
    count = _bounded_limit(text, limit, 4)
    return _select(text, _GLOSSARY, count, phrases=False) if count else ()


def select_business_phrases(text: str, limit: int = 3) -> tuple[LanguageCandidate, ...]:
    """Return up to three original business expressions with reusable patterns."""
    count = _bounded_limit(text, limit, 3)
    return _select(text, _PHRASES, count, phrases=True) if count else ()
