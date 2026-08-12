
# 증권사·자산운용사 금융 용어 Master Inventory

- 문서 버전: `v1.0`
- 기준일: `2026-08-12`
- 사용 목적: 금융 직무·전략·딜·방법론·산출물 ontology의 초기 seed corpus
- 구조: `canonical English name / 한국어 실무표현 / 약어·별칭`

## 0. 범위와 사용 원칙

이 문서에서 말하는 “전체”는 **증권사·자산운용사·투자은행·리서치·운용·트레이딩·리스크·사모시장 입문~중급 DB v1의 전체 범위**를 뜻한다. 전 세계 금융법령 조문, 모든 구조화상품 payoff, 산업별 수천 개 operational KPI까지 완전 포괄한다는 뜻은 아니다.

### 포함

- 회사 유형, 부서, 직무
- 자산군과 금융상품
- 투자전략
- IB 거래와 실행 프로세스
- 실사, 가치평가, 재무모델링
- 기업리서치, 회계, 기업재무 지표
- 포트폴리오, 리스크, 성과
- 트레이딩, 채권, 파생상품
- 대체투자, 산업 KPI
- 규제·공시, 데이터·기술, 업무 산출물

### 후속 확장팩으로 분리할 영역

- 국가별 세법과 법률 조문 전체
- 구조화상품별 payoff와 term-sheet 조항 전체
- 보험계리·은행 ALM의 고급 수리모형
- 개별 산업의 기업별 고유 KPI
- 상품별 회계처리 분개와 IFRS/K-GAAP 세부 예외

### DB 입력 규칙

1. 행 하나는 원칙적으로 concept 하나다.
2. 약어·번역·실무 별칭은 concept를 새로 만들지 않고 label로 저장한다.
3. 동일 표현이 다른 의미를 가지면 별도 concept로 분리한다.
4. 법적 대응어는 exact synonym이 아니라 `FUNCTIONAL_EQUIVALENT_TO` 관계를 검토한다.
5. 이 문서는 용어 후보 inventory다. 최종 정의와 관계는 `3_term_definition_agent_spec.md` 절차를 거쳐 승인한다.
6. `FIN-01-001` 형식은 inventory 정렬용 임시 ID다. DB 승인 단계에서는 UUID와 `FIN-METHOD-DCF` 같은 안정적 semantic code를 별도로 부여한다.

## 0.1 Source code

- **[S01]** EDM Council, Financial Industry Business Ontology (FIBO): https://spec.edmcouncil.org/fibo/
- **[S02]** EDM Council, FIBO Vocabulary: https://spec.edmcouncil.org/fibo/page/vocabulary
- **[S03]** CFA Institute, CFA Program Glossary: https://www.cfainstitute.org/programs/cfa-program/candidate-resources/glossary-terms
- **[S04]** CFA Institute, Investment Foundations Certificate: https://www.cfainstitute.org/programs/investment-foundations-certificate
- **[S05]** CFA Institute, Refresher Readings: https://www.cfainstitute.org/insights/professional-learning/refresher-readings
- **[S06]** CFA Institute, Definitions for Responsible Investment Approaches: https://rpc.cfainstitute.org/research/reports/2023/definitions-for-responsible-investment-approaches
- **[S07]** FINRA, Series 79 Investment Banking Representative Exam: https://www.finra.org/registration-exams-ce/qualification-exams/series79
- **[S08]** FINRA, Securities Industry Essentials Exam: https://www.finra.org/registration-exams-ce/qualification-exams/securities-industry-essentials-exam
- **[S09]** SEC Investor.gov, Investment Glossary: https://www.investor.gov/introduction-investing/investing-basics/glossary
- **[S10]** O*NET, Financial and Investment Analysts: https://www.onetonline.org/link/summary/13-2051.00
- **[S11]** O*NET, Investment Fund Managers: https://www.onetonline.org/link/details/11-3031.03
- **[S12]** O*NET, Financial Quantitative Analysts: https://www.onetonline.org/link/summary/13-2099.01
- **[S13]** O*NET, Financial Risk Specialists: https://www.onetonline.org/link/summary/13-2054.00
- **[S14]** NCS, 금융·보험/자산운용 관련 능력단위: https://www.ncs.go.kr/
- **[S15]** 금융투자교육원, 금융투자 직무역량 체계: https://www.kifin.or.kr/intro/intro02.do
- **[S16]** XBRL International, Taxonomies: https://www.xbrl.org/the-standard/what/key-concepts-in-xbrl/taxonomies/
- **[S17]** IFRS Foundation, Accounting Standards Navigator: https://www.ifrs.org/issued-standards/list-of-standards/
- **[S18]** Global Investment Performance Standards (GIPS): https://www.gipsstandards.org/standards/gips-standards-for-firms/
- **[S19]** Basel Committee, Basel Framework: https://www.bis.org/basel_framework/
- **[S20]** ISDA, Derivatives Glossary and Definitions: https://www.isda.org/1985/01/01/glossary/
- **[S21]** MSCI, Index Glossary: https://www.msci.com/index/methodology/latest/IndexGlossary
- **[S22]** ILPA, Private Equity Glossary: https://ilpa.org/resources-tools/private-equity-101/private-equity-glossary/
- **[S23]** CAIA, Fundamentals of Alternative Investments: https://caia.org/index.php/content/fundamentals-alternative-investments-learning-modules
- **[S24]** Preqin Academy, Industry Definitions: https://www.preqin.com/academy/industry-definitions
- **[S25]** 금융감독원 DART, 기업공시 길라잡이: https://dart.fss.or.kr/info/main.do?menu=210
- **[S26]** 한국거래소 정보데이터시스템/투자자 교육: https://data.krx.co.kr/
- **[S27]** OpenDART: https://opendart.fss.or.kr/
- **[S28]** SASB Standards Navigator: https://navigator.sasb.ifrs.org/

## 0.2 목차 및 수량
- 01. 기관·시장참여자 — **65개**
- 02. 증권사·자산운용사 조직 기능 및 부서 — **99개**
- 03. 직무·직책 — **72개**
- 04. 자산군·금융상품·계약 — **94개**
- 05. 투자전략·운용스타일 — **104개**
- 06. IB·기업금융 거래 유형 — **72개**
- 07. 딜 실행·자금조달 프로세스 — **71개**
- 08. 실사(Due Diligence) 세부 유형 및 검토항목 — **33개**
- 09. 기업가치평가·재무모델링 방법론 — **85개**
- 10. 기업·산업 리서치 용어 — **65개**
- 11. 회계·재무제표 개념 — **91개**
- 12. 기업재무·가치평가 지표 — **81개**
- 13. 포트폴리오 구성·리스크·성과 — **96개**
- 14. 트레이딩·시장미시구조·오퍼레이션 — **70개**
- 15. 채권·크레딧 분석 — **75개**
- 16. 파생상품·헤지·옵션 지표 — **63개**
- 17. 대체투자·사모시장 — **71개**
- 18. 산업별 핵심 KPI — **132개**
- 19. 규제·공시·지배구조 — **68개**
- 20. 금융 데이터·기술·식별자 — **76개**
- 21. 업무 산출물·문서 — **66개**

**총 용어 후보: 1649개**

---

## 01. 기관·시장참여자

- Primary type: `INSTITUTION / MARKET_INFRA`
- 기본 레퍼런스: [S01] [S02] [S04] [S08] [S09]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-01-001 | Securities Firm | 증권사 | securities company |
| FIN-01-002 | Broker-Dealer | 브로커딜러 | B/D |
| FIN-01-003 | Investment Bank | 투자은행 | IB |
| FIN-01-004 | Commercial Bank | 상업은행 | commercial banking institution |
| FIN-01-005 | Universal Bank | 종합금융은행 | universal banking group |
| FIN-01-006 | Asset Management Company | 자산운용사 | AMC / investment management firm |
| FIN-01-007 | Investment Adviser | 투자자문업자 | investment advisor |
| FIN-01-008 | Hedge Fund | 헤지펀드 | alternative investment fund |
| FIN-01-009 | Mutual Fund | 뮤추얼펀드 / 공모펀드 | open-end fund |
| FIN-01-010 | Exchange-Traded Fund Sponsor | ETF 운용사 / ETF 스폰서 | ETF sponsor |
| FIN-01-011 | Private Equity Firm | 사모펀드 운용사 | PE firm |
| FIN-01-012 | Venture Capital Firm | 벤처캐피털 | VC firm |
| FIN-01-013 | Private Credit Manager | 사모대출 운용사 | private debt manager |
| FIN-01-014 | Real Estate Investment Manager | 부동산 투자운용사 | real estate manager |
| FIN-01-015 | Infrastructure Fund Manager | 인프라 펀드 운용사 | infrastructure manager |
| FIN-01-016 | Pension Fund | 연기금 | pension plan / retirement fund |
| FIN-01-017 | Sovereign Wealth Fund | 국부펀드 | SWF |
| FIN-01-018 | Insurance Company | 보험회사 | insurer |
| FIN-01-019 | Endowment | 기부기금 / 대학기금 | endowment fund |
| FIN-01-020 | Foundation | 재단기금 | foundation investor |
| FIN-01-021 | Family Office | 패밀리오피스 | SFO / MFO |
| FIN-01-022 | Fund of Funds Manager | 재간접펀드 | FoF |
| FIN-01-023 | Real Estate Investment Trust | 부동산투자회사 | REIT |
| FIN-01-024 | Business Development Company | 사업개발회사 | BDC |
| FIN-01-025 | Special Purpose Acquisition Company | 기업인수목적회사 | SPAC |
| FIN-01-026 | Special Purpose Vehicle | 특수목적기구 | SPV / SPE |
| FIN-01-027 | Issuer | 발행인 | issuing entity |
| FIN-01-028 | Listed Company | 상장회사 | public company |
| FIN-01-029 | Private Company | 비상장회사 | privately held company |
| FIN-01-030 | Institutional Investor | 기관투자자 | institution |
| FIN-01-031 | Retail Investor | 개인투자자 | individual investor |
| FIN-01-032 | Accredited Investor | 적격투자자 / 공인투자자 | US accredited investor |
| FIN-01-033 | Professional Investor | 전문투자자 | professional client |
| FIN-01-034 | Qualified Institutional Buyer | 적격기관투자자 | QIB |
| FIN-01-035 | General Partner | 업무집행사원 / GP | GP |
| FIN-01-036 | Limited Partner | 유한책임사원 / 출자자 | LP |
| FIN-01-037 | Investment Committee | 투자위원회 | IC |
| FIN-01-038 | Stock Exchange | 증권거래소 | exchange |
| FIN-01-039 | Alternative Trading System | 대체거래시스템 | ATS |
| FIN-01-040 | Electronic Communication Network | 전자통신망 거래시스템 | ECN |
| FIN-01-041 | Central Counterparty | 중앙청산소 | CCP |
| FIN-01-042 | Central Securities Depository | 중앙예탁기관 | CSD |
| FIN-01-043 | Clearinghouse | 청산기관 | clearing house |
| FIN-01-044 | Custodian | 수탁기관 / 보관기관 | custody bank |
| FIN-01-045 | Prime Broker | 프라임브로커 | PB |
| FIN-01-046 | Depositary Bank | 예탁은행 | depositary |
| FIN-01-047 | Transfer Agent | 명의개서대리인 | transfer agency |
| FIN-01-048 | Registrar | 등록기관 / 명부관리기관 | share registrar |
| FIN-01-049 | Trustee | 수탁자 / 신탁업자 | bond trustee |
| FIN-01-050 | Fund Administration Company | 펀드 사무관리회사 | fund admin |
| FIN-01-051 | Fund Accounting Service Provider | 펀드회계 담당기관 | fund accounting agent |
| FIN-01-052 | Credit Rating Agency | 신용평가사 | CRA |
| FIN-01-053 | Index Provider | 지수사업자 | index administrator |
| FIN-01-054 | Financial Data Vendor | 금융데이터 사업자 | market data vendor |
| FIN-01-055 | Auditor | 외부감사인 | external auditor |
| FIN-01-056 | Law Firm | 법무법인 | legal adviser |
| FIN-01-057 | Consulting Firm | 컨설팅사 | advisory firm |
| FIN-01-058 | Underwriter | 인수인 / 주관사 | securities underwriter |
| FIN-01-059 | Lead Manager | 대표주관회사 | lead underwriter / bookrunner |
| FIN-01-060 | Syndicate | 인수단 / 신디케이트 | underwriting syndicate |
| FIN-01-061 | Placement Agent | 주선인 / 사모주선사 | private placement agent |
| FIN-01-062 | Market-Making Firm | 시장조성자 | MM |
| FIN-01-063 | Liquidity Provider | 유동성공급자 | LP in market making context |
| FIN-01-064 | Selling Shareholder | 구주매출 주주 | selling stockholder |
| FIN-01-065 | Proxy Adviser | 의결권 자문기관 | proxy advisory firm |

---

## 02. 증권사·자산운용사 조직 기능 및 부서

- Primary type: `BUSINESS_FUNCTION / ORG_UNIT`
- 기본 레퍼런스: [S07] [S10] [S11] [S14] [S15]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-02-001 | Front Office | 프런트오피스 | FO |
| FIN-02-002 | Middle Office | 미들오피스 | MO |
| FIN-02-003 | Back Office | 백오피스 | BO |
| FIN-02-004 | Investment Banking | 투자은행 업무 | IB |
| FIN-02-005 | Corporate Finance Advisory | 기업금융 자문 | corporate finance |
| FIN-02-006 | Industry Coverage | 산업 커버리지 | coverage group |
| FIN-02-007 | Corporate Coverage | 기업 커버리지 | client coverage |
| FIN-02-008 | Product Group | 상품·딜 전문 그룹 | product team |
| FIN-02-009 | Equity Capital Markets | 주식자본시장 | ECM |
| FIN-02-010 | Debt Capital Markets | 채권자본시장 | DCM |
| FIN-02-011 | Mergers and Acquisitions Advisory | 인수합병 자문 | M&A Advisory |
| FIN-02-012 | Leveraged Finance | 레버리지드 파이낸스 | LevFin |
| FIN-02-013 | Acquisition Finance | 인수금융 | acq fin |
| FIN-02-014 | Project Finance | 프로젝트 파이낸스 | PF |
| FIN-02-015 | Structured Finance | 구조화금융 | SF |
| FIN-02-016 | Real Estate Finance | 부동산금융 | REF |
| FIN-02-017 | Infrastructure Finance | 인프라금융 | infra finance |
| FIN-02-018 | Securitization | 유동화금융 | asset securitization |
| FIN-02-019 | Syndicate Desk | 신디케이트 데스크 | syndicate |
| FIN-02-020 | Equity Origination | 주식발행 영업·주선 | ECM origination |
| FIN-02-021 | Equity Execution | 주식발행 실행 | ECM execution |
| FIN-02-022 | Debt Origination | 채권발행 영업·주선 | DCM origination |
| FIN-02-023 | Debt Execution | 채권발행 실행 | DCM execution |
| FIN-02-024 | Research Center | 리서치센터 | research division |
| FIN-02-025 | Equity Research | 주식 리서치 | company research |
| FIN-02-026 | Fixed Income Research | 채권 리서치 | FI research |
| FIN-02-027 | Credit Research | 크레딧 리서치 | credit analysis |
| FIN-02-028 | Macro Research | 거시경제 리서치 | macro strategy |
| FIN-02-029 | Investment Strategy Research | 투자전략 리서치 | strategy research |
| FIN-02-030 | Quantitative Research | 퀀트 리서치 | quant research |
| FIN-02-031 | Sales and Trading | 세일즈앤트레이딩 | S&T |
| FIN-02-032 | Equity Sales | 주식 세일즈 | cash equity sales |
| FIN-02-033 | Fixed Income Sales | 채권 세일즈 | FI sales |
| FIN-02-034 | Institutional Sales | 기관영업 | institutional business |
| FIN-02-035 | Retail Brokerage | 리테일 브로커리지 | retail securities brokerage |
| FIN-02-036 | Institutional Brokerage | 법인영업 / 기관 브로커리지 | institutional brokerage |
| FIN-02-037 | Cash Equities | 현물주식 부문 | cash equity desk |
| FIN-02-038 | Equity Derivatives | 주식파생 부문 | equity derivatives desk |
| FIN-02-039 | Rates Trading | 금리 트레이딩 | rates desk |
| FIN-02-040 | Credit Trading | 크레딧 트레이딩 | credit desk |
| FIN-02-041 | Foreign Exchange Trading | 외환 트레이딩 | FX desk |
| FIN-02-042 | Commodities Trading | 원자재 트레이딩 | commodities desk |
| FIN-02-043 | Delta One | 델타원 부문 | delta-one desk |
| FIN-02-044 | Program Trading | 프로그램 매매 | PT |
| FIN-02-045 | Electronic Trading | 전자거래 | e-trading |
| FIN-02-046 | Sales Trading | 세일즈 트레이딩 | sales trader desk |
| FIN-02-047 | Structuring | 금융상품 구조화 | structuring desk |
| FIN-02-048 | Prime Brokerage | 프라임브로커리지 | PBS |
| FIN-02-049 | Securities Lending | 증권대차 | stock lending |
| FIN-02-050 | Repo Desk | 환매조건부채권 데스크 | repo |
| FIN-02-051 | Principal Investment | 자기자본투자 | PI |
| FIN-02-052 | Treasury | 재무·자금부 | corporate treasury |
| FIN-02-053 | Balance Sheet Management | 재무상태표 관리 | BSM |
| FIN-02-054 | Wealth Management | 자산관리 | WM |
| FIN-02-055 | Private Banking | 프라이빗뱅킹 | PB |
| FIN-02-056 | Investment Banking Operations | IB 오퍼레이션 | IB ops |
| FIN-02-057 | Trade Support | 거래지원 | trade control |
| FIN-02-058 | Clearing Operations | 청산업무 | clearing ops |
| FIN-02-059 | Settlement Operations | 결제업무 | settlements |
| FIN-02-060 | Custody Operations | 수탁·보관업무 | custody ops |
| FIN-02-061 | Product Control | 상품손익 관리 | P&L control |
| FIN-02-062 | Valuation Control | 독립가격검증 | IPV / valuation control |
| FIN-02-063 | Market Risk Management | 시장리스크관리 | market risk |
| FIN-02-064 | Credit Risk Management | 신용리스크관리 | credit risk |
| FIN-02-065 | Liquidity Risk Management | 유동성리스크관리 | liquidity risk |
| FIN-02-066 | Operational Risk Management | 운영리스크관리 | op risk |
| FIN-02-067 | Enterprise Risk Management | 전사리스크관리 | ERM |
| FIN-02-068 | Compliance | 준법감시 | compliance |
| FIN-02-069 | Legal | 법무 | legal department |
| FIN-02-070 | Internal Audit | 내부감사 | internal audit |
| FIN-02-071 | Anti-Money Laundering Function | 자금세탁방지 | AML |
| FIN-02-072 | Know Your Customer | 고객확인 | KYC |
| FIN-02-073 | Chief Investment Office | 최고투자책임자 조직 | CIO Office |
| FIN-02-074 | Asset Allocation | 자산배분 | AA |
| FIN-02-075 | Equity Investment | 주식운용 | equity management |
| FIN-02-076 | Fixed Income Investment | 채권운용 | bond management |
| FIN-02-077 | Multi-Asset Investment | 멀티에셋 운용 | multi-asset |
| FIN-02-078 | Quantitative and Systematic Investment | 퀀트·시스템 운용 | quant/systematic |
| FIN-02-079 | Index and ETF Investment | 인덱스·ETF 운용 | passive investment |
| FIN-02-080 | Alternative Investment | 대체투자 | alternatives |
| FIN-02-081 | Private Equity Investment | 사모주식 투자 | PE investment |
| FIN-02-082 | Private Credit Investment | 사모대출 투자 | private debt |
| FIN-02-083 | Real Assets Investment | 실물자산 투자 | real assets |
| FIN-02-084 | Real Estate Investment | 부동산 투자 | real estate |
| FIN-02-085 | Infrastructure Investment | 인프라 투자 | infrastructure |
| FIN-02-086 | Liability-Driven Investment | 부채연계투자 | LDI |
| FIN-02-087 | Outsourced Chief Investment Officer | 외부위탁 CIO | OCIO |
| FIN-02-088 | Manager Research | 운용사 리서치 | manager selection |
| FIN-02-089 | Investment Operations | 운용지원 | investment ops |
| FIN-02-090 | Performance Measurement | 성과측정 | performance measurement |
| FIN-02-091 | Performance Attribution Function | 성과요인분석 | attribution |
| FIN-02-092 | Fund Accounting | 펀드회계 | NAV accounting |
| FIN-02-093 | Product Management | 상품기획 | product development |
| FIN-02-094 | Fund Distribution Function | 상품판매·채널관리 | distribution |
| FIN-02-095 | Client Service | 고객관리 | client servicing |
| FIN-02-096 | Stewardship | 스튜어드십 | ownership practice |
| FIN-02-097 | Responsible Investment | 책임투자 | RI |
| FIN-02-098 | Proxy Voting Function | 의결권 행사 | voting |
| FIN-02-099 | Investment Compliance | 운용 컴플라이언스 | pre/post-trade compliance |

---

## 03. 직무·직책

- Primary type: `ROLE`
- 기본 레퍼런스: [S07] [S10] [S11] [S12] [S13] [S14] [S15]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-03-001 | Investment Banking Analyst | IB 애널리스트 | IB analyst |
| FIN-03-002 | Investment Banking Associate | IB 어소시에이트 | IB associate |
| FIN-03-003 | Investment Banking Vice President | IB 부사장급 / VP | IB VP |
| FIN-03-004 | Investment Banking Director | IB 디렉터 | director |
| FIN-03-005 | Managing Director | 매니징디렉터 | MD |
| FIN-03-006 | Coverage Banker | 커버리지 뱅커 | relationship banker |
| FIN-03-007 | M&A Banker | M&A 뱅커 | M&A adviser |
| FIN-03-008 | ECM Banker | ECM 뱅커 | equity capital markets banker |
| FIN-03-009 | DCM Banker | DCM 뱅커 | debt capital markets banker |
| FIN-03-010 | Leveraged Finance Banker | 레버리지드 파이낸스 뱅커 | LevFin banker |
| FIN-03-011 | Project Finance Banker | 프로젝트금융 담당자 | PF banker |
| FIN-03-012 | Structured Finance Banker | 구조화금융 담당자 | SF banker |
| FIN-03-013 | Syndicate Banker | 신디케이트 담당자 | syndicate manager |
| FIN-03-014 | Originator | 딜 발굴·주선 담당자 | origination banker |
| FIN-03-015 | Execution Banker | 딜 실행 담당자 | execution banker |
| FIN-03-016 | Equity Research Analyst | 주식 리서치 애널리스트 | sell-side analyst |
| FIN-03-017 | Sector Analyst | 섹터 애널리스트 | industry analyst |
| FIN-03-018 | Research Associate | 리서치 어소시에이트 | RA |
| FIN-03-019 | Supervisory Analyst | 리서치 심사역 | supervisory analyst |
| FIN-03-020 | Economist | 이코노미스트 | macro economist |
| FIN-03-021 | Investment Strategist | 투자전략가 | market strategist |
| FIN-03-022 | Credit Analyst | 신용분석가 | credit research analyst |
| FIN-03-023 | Fixed Income Analyst | 채권분석가 | bond analyst |
| FIN-03-024 | Investment Analyst | 투자분석가 | buy-side analyst |
| FIN-03-025 | Portfolio Manager | 포트폴리오 매니저 | PM / 펀드매니저 |
| FIN-03-026 | Assistant Portfolio Manager | 주니어 PM / 보조운용역 | APM |
| FIN-03-027 | Chief Investment Officer | 최고투자책임자 | CIO |
| FIN-03-028 | Head of Investments | 투자부문장 | investment head |
| FIN-03-029 | Asset Allocator | 자산배분 담당자 | allocation strategist |
| FIN-03-030 | Quantitative Researcher | 퀀트 리서처 | quant researcher |
| FIN-03-031 | Quantitative Developer | 퀀트 개발자 | quant developer |
| FIN-03-032 | Financial Engineer | 금융공학자 | financial engineering specialist |
| FIN-03-033 | Data Scientist | 데이터 사이언티스트 | DS |
| FIN-03-034 | Systematic Portfolio Manager | 시스템 운용역 | systematic PM |
| FIN-03-035 | Trader | 트레이더 | dealer |
| FIN-03-036 | Execution Trader | 주문집행 트레이더 | execution trader |
| FIN-03-037 | Sales Trader | 세일즈 트레이더 | sales trader |
| FIN-03-038 | Market-Making Trader | 시장조성 트레이더 | market-making trader |
| FIN-03-039 | Structurer | 구조화 담당자 | product structurer |
| FIN-03-040 | Institutional Salesperson | 기관영업 담당자 | institutional sales |
| FIN-03-041 | Private Banker | 프라이빗뱅커 | PB |
| FIN-03-042 | Wealth Manager | 자산관리사 | WM adviser |
| FIN-03-043 | Product Specialist | 상품전문가 | investment specialist |
| FIN-03-044 | Client Portfolio Manager | 고객 포트폴리오 매니저 | CPM |
| FIN-03-045 | Fund Selector | 펀드선정 담당자 | fund analyst |
| FIN-03-046 | Manager Research Analyst | 운용사 평가 애널리스트 | manager researcher |
| FIN-03-047 | Investment Risk Manager | 투자리스크 관리자 | investment risk |
| FIN-03-048 | Market Risk Analyst | 시장리스크 분석가 | market risk analyst |
| FIN-03-049 | Credit Risk Analyst | 신용리스크 분석가 | credit risk analyst |
| FIN-03-050 | Liquidity Risk Analyst | 유동성리스크 분석가 | liquidity risk analyst |
| FIN-03-051 | Operational Risk Analyst | 운영리스크 분석가 | operational risk analyst |
| FIN-03-052 | Model Risk Manager | 모델리스크 관리자 | model validation |
| FIN-03-053 | Performance Analyst | 성과분석가 | performance analyst |
| FIN-03-054 | Attribution Analyst | 성과요인 분석가 | attribution analyst |
| FIN-03-055 | Fund Accountant | 펀드회계 담당자 | NAV accountant |
| FIN-03-056 | Investment Operations Analyst | 운용지원 담당자 | investment ops analyst |
| FIN-03-057 | Compliance Officer | 준법감시인 | compliance officer |
| FIN-03-058 | Anti-Money Laundering Officer | 자금세탁방지 담당자 | AML officer |
| FIN-03-059 | Legal Counsel | 사내변호사 / 법무담당 | counsel |
| FIN-03-060 | Internal Auditor | 내부감사인 | internal audit |
| FIN-03-061 | Treasurer | 재무·자금 책임자 | corporate treasurer |
| FIN-03-062 | Controller | 재무통제 책임자 | financial controller |
| FIN-03-063 | Product Controller | 상품손익 통제 담당자 | P&L controller |
| FIN-03-064 | Valuation Controller | 가치평가 통제 담당자 | IPV analyst |
| FIN-03-065 | Fund Administrator | 펀드 사무관리 담당자 | administrator |
| FIN-03-066 | Stewardship Analyst | 스튜어드십 담당자 | engagement analyst |
| FIN-03-067 | ESG Analyst | ESG 분석가 | sustainability analyst |
| FIN-03-068 | Private Equity Associate | PE 어소시에이트 | PE associate |
| FIN-03-069 | Private Credit Analyst | 사모대출 심사역 | private debt analyst |
| FIN-03-070 | Investment Committee Member | 투자위원 | IC member |
| FIN-03-071 | Operating Partner | 운영 파트너 | PE operating partner |
| FIN-03-072 | Venture Capitalist | 벤처캐피털리스트 | VC investor |

---

## 04. 자산군·금융상품·계약

- Primary type: `ASSET_CLASS / INSTRUMENT`
- 기본 레퍼런스: [S01] [S03] [S08] [S09] [S17] [S20]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-04-001 | Equity Asset Class | 주식 자산군 | stocks |
| FIN-04-002 | Common Stock | 보통주 | ordinary share |
| FIN-04-003 | Preferred Stock | 우선주 | preference share |
| FIN-04-004 | Depositary Receipt | 주식예탁증서 | DR |
| FIN-04-005 | American Depositary Receipt | 미국주식예탁증서 | ADR |
| FIN-04-006 | Global Depositary Receipt | 글로벌주식예탁증서 | GDR |
| FIN-04-007 | Subscription Right | 신주인수권 | rights |
| FIN-04-008 | Warrant | 워런트 / 신주인수권증권 | warrant security |
| FIN-04-009 | Convertible Preferred Stock | 전환우선주 | CPS |
| FIN-04-010 | Redeemable Convertible Preferred Stock | 상환전환우선주 | RCPS |
| FIN-04-011 | Treasury Stock | 자기주식 | treasury shares |
| FIN-04-012 | Fixed Income | 채권 자산군 | bonds |
| FIN-04-013 | Government Bond | 국채 | sovereign bond |
| FIN-04-014 | Treasury Bond | 재무부채권 | treasury security |
| FIN-04-015 | Municipal Bond | 지방채 / 지방정부채 | muni |
| FIN-04-016 | Agency Bond | 정부기관채 | agency security |
| FIN-04-017 | Corporate Bond | 회사채 | corporate debt |
| FIN-04-018 | Financial Bond | 금융채 | bank/financial institution bond |
| FIN-04-019 | Covered Bond | 커버드본드 | covered debt |
| FIN-04-020 | Secured Bond | 담보부채권 | secured note |
| FIN-04-021 | Unsecured Bond | 무담보채권 | debenture |
| FIN-04-022 | Senior Bond | 선순위채 | senior note |
| FIN-04-023 | Subordinated Bond | 후순위채 | sub debt |
| FIN-04-024 | Perpetual Bond | 영구채 | perpetual security |
| FIN-04-025 | Callable Bond | 콜옵션부채권 | callable note |
| FIN-04-026 | Putable Bond | 풋옵션부채권 | putable note |
| FIN-04-027 | Floating-Rate Note | 변동금리채 | FRN |
| FIN-04-028 | Zero-Coupon Bond | 무이표채 | zero |
| FIN-04-029 | Inflation-Linked Bond | 물가연동채 | linker |
| FIN-04-030 | Green Bond | 녹색채권 | green debt |
| FIN-04-031 | Social Bond | 사회적채권 | social bond |
| FIN-04-032 | Sustainability Bond | 지속가능채권 | sustainability bond |
| FIN-04-033 | Sustainability-Linked Bond | 지속가능연계채권 | SLB |
| FIN-04-034 | Convertible Bond | 전환사채 | CB |
| FIN-04-035 | Exchangeable Bond | 교환사채 | EB |
| FIN-04-036 | Bond with Warrant | 신주인수권부사채 | BW |
| FIN-04-037 | Commercial Paper | 기업어음 | CP |
| FIN-04-038 | Certificate of Deposit | 양도성예금증서 | CD |
| FIN-04-039 | Money Market Instrument | 단기금융상품 | MM instrument |
| FIN-04-040 | Repurchase Agreement | 환매조건부거래 | Repo / RP |
| FIN-04-041 | Reverse Repurchase Agreement | 역환매조건부거래 | reverse repo |
| FIN-04-042 | Leveraged Loan | 레버리지론 | leveraged lending |
| FIN-04-043 | Term Loan | 기간대출 | TL |
| FIN-04-044 | Revolving Credit Facility | 회전한도대출 | RCF / revolver |
| FIN-04-045 | Bridge Loan | 브리지론 | bridge financing |
| FIN-04-046 | Mezzanine Debt | 메자닌 부채 | mezz debt |
| FIN-04-047 | Unitranche Loan | 유니트랜치 대출 | unitranche |
| FIN-04-048 | Payment-in-Kind Note | 현물지급채 | PIK note |
| FIN-04-049 | Mortgage-Backed Security | 주택저당증권 | MBS |
| FIN-04-050 | Commercial Mortgage-Backed Security | 상업용부동산저당증권 | CMBS |
| FIN-04-051 | Asset-Backed Security | 자산유동화증권 | ABS |
| FIN-04-052 | Collateralized Loan Obligation | 대출채권담보부증권 | CLO |
| FIN-04-053 | Collateralized Debt Obligation | 부채담보부증권 | CDO |
| FIN-04-054 | Foreign Exchange | 외환 | FX |
| FIN-04-055 | Spot FX | 현물환 | spot |
| FIN-04-056 | FX Forward | 선물환 | currency forward |
| FIN-04-057 | Non-Deliverable Forward | 차액결제선물환 | NDF |
| FIN-04-058 | Currency Swap | 통화스왑 | cross-currency swap / CCS |
| FIN-04-059 | Interest Rate Swap | 금리스왑 | IRS |
| FIN-04-060 | Total Return Swap | 총수익스왑 | TRS |
| FIN-04-061 | Credit Default Swap | 신용부도스왑 | CDS |
| FIN-04-062 | Forward Contract | 선도계약 | forward |
| FIN-04-063 | Futures Contract | 선물계약 | futures |
| FIN-04-064 | Option Contract | 옵션계약 | option |
| FIN-04-065 | Call Option | 콜옵션 | call |
| FIN-04-066 | Put Option | 풋옵션 | put |
| FIN-04-067 | Swaption | 스왑션 | swap option |
| FIN-04-068 | Equity Swap | 주식스왑 | equity total return swap |
| FIN-04-069 | Commodity Swap | 상품스왑 | commodity swap |
| FIN-04-070 | Structured Note | 구조화채권 | structured product |
| FIN-04-071 | Equity-Linked Security | 주가연계증권 | ELS / equity-linked note |
| FIN-04-072 | Derivative-Linked Security | 파생결합증권 | DLS |
| FIN-04-073 | Exchange-Traded Note | 상장지수증권 | ETN |
| FIN-04-074 | Mutual Fund Share | 펀드 수익증권 | fund unit |
| FIN-04-075 | Exchange-Traded Fund | 상장지수펀드 | ETF |
| FIN-04-076 | Closed-End Investment Fund | 폐쇄형펀드 | CEF |
| FIN-04-077 | Money Market Fund | 머니마켓펀드 | MMF |
| FIN-04-078 | Target-Date Fund | 타깃데이트펀드 | TDF |
| FIN-04-079 | Fund of Funds Product | 재간접펀드 상품 | FoF product |
| FIN-04-080 | Real Estate | 부동산 자산군 | real estate |
| FIN-04-081 | Infrastructure | 인프라 자산군 | infrastructure |
| FIN-04-082 | Private Equity | 사모주식 | PE |
| FIN-04-083 | Venture Capital | 벤처투자 | VC |
| FIN-04-084 | Growth Equity | 성장자본 | growth capital |
| FIN-04-085 | Private Credit | 사모대출 | private debt |
| FIN-04-086 | Direct Lending Asset Class | 직접대출 | direct lending |
| FIN-04-087 | Distressed Debt Asset Class | 부실채권 투자 | distressed credit |
| FIN-04-088 | Natural Resources | 천연자원 | natural resource investment |
| FIN-04-089 | Commodity | 원자재 | commodities |
| FIN-04-090 | Precious Metals | 귀금속 | gold/silver |
| FIN-04-091 | Digital Asset | 디지털자산 | crypto asset |
| FIN-04-092 | Carbon Allowance | 탄소배출권 | emissions allowance |
| FIN-04-093 | Insurance-Linked Security | 보험연계증권 | ILS |
| FIN-04-094 | Catastrophe Bond | 대재해채권 | cat bond |

---

## 05. 투자전략·운용스타일

- Primary type: `STRATEGY`
- 기본 레퍼런스: [S03] [S05] [S06] [S21] [S23]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-05-001 | Active Management | 액티브 운용 | active investing |
| FIN-05-002 | Passive Management | 패시브 운용 | index investing |
| FIN-05-003 | Index Tracking | 지수추종 | index replication |
| FIN-05-004 | Full Replication | 완전복제 | full replication indexing |
| FIN-05-005 | Stratified Sampling | 층화표본 복제 | sampling |
| FIN-05-006 | Optimization-Based Indexing | 최적화 기반 지수추종 | optimized replication |
| FIN-05-007 | Fundamental Investing | 펀더멘털 투자 | fundamental strategy |
| FIN-05-008 | Bottom-Up Investing | 상향식 투자 | bottom-up |
| FIN-05-009 | Top-Down Investing | 하향식 투자 | top-down |
| FIN-05-010 | Value Investing | 가치투자 | value |
| FIN-05-011 | Growth Investing | 성장주 투자 | growth |
| FIN-05-012 | Growth at a Reasonable Price | 합리적 가격의 성장주 투자 | GARP |
| FIN-05-013 | Quality Investing | 퀄리티 투자 | quality |
| FIN-05-014 | Dividend Investing | 배당투자 | income investing |
| FIN-05-015 | High Dividend Yield | 고배당 전략 | high yield equity |
| FIN-05-016 | Small-Cap Investing | 소형주 투자 | small cap |
| FIN-05-017 | Large-Cap Investing | 대형주 투자 | large cap |
| FIN-05-018 | Contrarian Investing | 역발상 투자 | contrarian |
| FIN-05-019 | Buy and Hold | 매수 후 보유 | buy-and-hold |
| FIN-05-020 | Concentrated Investing | 집중투자 | concentrated portfolio |
| FIN-05-021 | Core-Satellite Strategy | 코어-새틀라이트 전략 | core-satellite |
| FIN-05-022 | Sector Rotation | 섹터 로테이션 | industry rotation |
| FIN-05-023 | Thematic Investing | 테마투자 | thematic |
| FIN-05-024 | Long-Only Strategy | 롱온리 전략 | long only |
| FIN-05-025 | Equity Long/Short | 주식 롱숏 | ELS hedge strategy |
| FIN-05-026 | Fundamental Long/Short | 펀더멘털 롱숏 | fundamental L/S |
| FIN-05-027 | Market-Neutral Strategy | 시장중립 전략 | market neutral |
| FIN-05-028 | Equity Market Neutral | 주식시장중립 | EMN |
| FIN-05-029 | 130/30 Strategy | 130/30 전략 | extended equity |
| FIN-05-030 | Short-Bias Strategy | 숏바이어스 전략 | short biased |
| FIN-05-031 | Dedicated Short Strategy | 전문 공매도 전략 | dedicated short |
| FIN-05-032 | Activist Investing | 주주행동주의 투자 | activist |
| FIN-05-033 | Event-Driven Strategy | 이벤트드리븐 전략 | event driven |
| FIN-05-034 | Merger Arbitrage | 합병차익거래 | risk arbitrage |
| FIN-05-035 | Special Situations | 특수상황 투자 | special sits |
| FIN-05-036 | Distressed Investing | 부실기업 투자 | distressed |
| FIN-05-037 | Spin-Off Investing | 기업분할 이벤트 투자 | spin-off strategy |
| FIN-05-038 | Capital Structure Arbitrage | 자본구조 차익거래 | cap structure arb |
| FIN-05-039 | Relative Value Strategy | 상대가치 전략 | relative value |
| FIN-05-040 | Statistical Arbitrage | 통계적 차익거래 | stat arb |
| FIN-05-041 | Pairs Trading | 페어트레이딩 | pair trade |
| FIN-05-042 | Index Arbitrage | 지수차익거래 | index arb |
| FIN-05-043 | Convertible Arbitrage | 전환사채 차익거래 | convert arb |
| FIN-05-044 | Fixed Income Arbitrage | 채권 차익거래 | FI arb |
| FIN-05-045 | Volatility Arbitrage | 변동성 차익거래 | vol arb |
| FIN-05-046 | Cash-and-Carry Arbitrage | 현선물 차익거래 | cash and carry |
| FIN-05-047 | Reverse Cash-and-Carry | 역현선물 차익거래 | reverse cash and carry |
| FIN-05-048 | Basis Trade | 베이시스 거래 | basis strategy |
| FIN-05-049 | Calendar Spread Strategy | 캘린더 스프레드 전략 | time spread |
| FIN-05-050 | Cross-Sectional Momentum | 횡단면 모멘텀 | relative momentum |
| FIN-05-051 | Time-Series Momentum | 시계열 모멘텀 | trend following |
| FIN-05-052 | Managed Futures | 매니지드 퓨처스 | CTA |
| FIN-05-053 | Commodity Trading Adviser Strategy | CTA 전략 | CTA strategy |
| FIN-05-054 | Global Macro | 글로벌 매크로 | macro |
| FIN-05-055 | Discretionary Macro | 재량적 매크로 | discretionary global macro |
| FIN-05-056 | Systematic Macro | 시스템 매크로 | systematic macro |
| FIN-05-057 | Factor Investing | 팩터투자 | factor strategy |
| FIN-05-058 | Smart Beta | 스마트베타 | alternative beta |
| FIN-05-059 | Value Factor | 가치 팩터 | value premium |
| FIN-05-060 | Momentum Factor | 모멘텀 팩터 | momentum premium |
| FIN-05-061 | Quality Factor | 퀄리티 팩터 | quality premium |
| FIN-05-062 | Size Factor | 규모 팩터 | small-size premium |
| FIN-05-063 | Low-Volatility Factor | 저변동성 팩터 | minimum volatility factor |
| FIN-05-064 | Carry Strategy | 캐리 전략 | carry |
| FIN-05-065 | Defensive Equity | 방어주 전략 | defensive |
| FIN-05-066 | Multi-Factor Strategy | 멀티팩터 전략 | multi-factor |
| FIN-05-067 | Risk Parity | 리스크패리티 | equal risk contribution |
| FIN-05-068 | Minimum-Variance Strategy | 최소분산 전략 | min variance |
| FIN-05-069 | Maximum-Diversification Strategy | 최대분산효과 전략 | max diversification |
| FIN-05-070 | Volatility Targeting | 변동성 타기팅 | vol targeting |
| FIN-05-071 | Portable Alpha | 포터블 알파 | alpha transport |
| FIN-05-072 | Overlay Strategy | 오버레이 전략 | currency/risk overlay |
| FIN-05-073 | Strategic Asset Allocation | 전략적 자산배분 | SAA |
| FIN-05-074 | Tactical Asset Allocation | 전술적 자산배분 | TAA |
| FIN-05-075 | Dynamic Asset Allocation | 동적 자산배분 | DAA |
| FIN-05-076 | Total Portfolio Approach | 총포트폴리오 접근 | TPA |
| FIN-05-077 | Liability-Driven Investing | 부채연계투자 | LDI |
| FIN-05-078 | Cash-Flow Matching | 현금흐름 매칭 | CF matching |
| FIN-05-079 | Immunization Strategy | 면역화 전략 | immunization |
| FIN-05-080 | Duration Matching | 듀레이션 매칭 | duration match |
| FIN-05-081 | Bond Ladder | 채권 래더 | ladder |
| FIN-05-082 | Barbell Strategy | 바벨 전략 | barbell |
| FIN-05-083 | Bullet Strategy | 불릿 전략 | bullet |
| FIN-05-084 | Roll-Down Strategy | 롤다운 전략 | roll down |
| FIN-05-085 | Yield-Curve Steepener | 수익률곡선 스티프너 | steepener |
| FIN-05-086 | Yield-Curve Flattener | 수익률곡선 플래트너 | flattener |
| FIN-05-087 | Credit Carry Strategy | 크레딧 캐리 | credit carry |
| FIN-05-088 | Spread Compression Strategy | 스프레드 축소 전략 | tightening trade |
| FIN-05-089 | Long Volatility | 롱 변동성 | long vol |
| FIN-05-090 | Short Volatility | 숏 변동성 | short vol |
| FIN-05-091 | Covered Call Strategy | 커버드콜 전략 | buy-write |
| FIN-05-092 | Protective Put Strategy | 프로텍티브풋 | married put |
| FIN-05-093 | Collar Strategy | 칼라 전략 | collar |
| FIN-05-094 | Option Overwriting | 옵션 오버라이트 | overwrite |
| FIN-05-095 | Delta-Neutral Strategy | 델타중립 전략 | delta neutral |
| FIN-05-096 | Gamma Scalping | 감마 스캘핑 | gamma trading |
| FIN-05-097 | Currency Hedging | 환헤지 | FX hedge |
| FIN-05-098 | Unhedged Currency Exposure | 환오픈 | unhedged FX |
| FIN-05-099 | ESG Integration | ESG 통합 | ESG integration |
| FIN-05-100 | Negative Screening | 네거티브 스크리닝 | exclusionary screening |
| FIN-05-101 | Positive Screening | 포지티브 스크리닝 | best-in-class |
| FIN-05-102 | Impact Investing | 임팩트 투자 | impact |
| FIN-05-103 | Stewardship Strategy | 스튜어드십 전략 | active ownership |
| FIN-05-104 | Tax-Loss Harvesting | 세금손실 수확 | tax-loss harvesting |

---

## 06. IB·기업금융 거래 유형

- Primary type: `DEAL`
- 기본 레퍼런스: [S07] [S08] [S09] [S25] [S26]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-06-001 | Initial Public Offering | 기업공개 | IPO |
| FIN-06-002 | Direct Listing | 직상장 | direct public listing |
| FIN-06-003 | SPAC IPO | 스팩 상장 | blank-check IPO |
| FIN-06-004 | De-SPAC Transaction | 스팩 합병상장 | de-SPAC |
| FIN-06-005 | Follow-On Offering | 후속 공모 | FPO |
| FIN-06-006 | Seasoned Equity Offering | 기상장기업 주식공모 | SEO |
| FIN-06-007 | Primary Offering | 신주모집 | primary issue |
| FIN-06-008 | Secondary Offering | 구주매출 | secondary sale |
| FIN-06-009 | Rights Offering | 주주배정 유상증자 | rights issue |
| FIN-06-010 | Public Offering | 공모 | registered offering |
| FIN-06-011 | Private Placement | 사모발행 | private offering |
| FIN-06-012 | PIPE Transaction | 상장기업 사모투자 | PIPE |
| FIN-06-013 | Block Trade | 블록딜 | block sale |
| FIN-06-014 | Accelerated Bookbuild | 신속수요예측 블록딜 | ABB |
| FIN-06-015 | At-the-Market Offering | 시장가 발행 | ATM offering |
| FIN-06-016 | Shelf Offering | 선반등록 발행 | shelf takedown |
| FIN-06-017 | Bonus Issue | 무상증자 | stock dividend issue |
| FIN-06-018 | Stock Split | 액면분할 | share split |
| FIN-06-019 | Reverse Stock Split | 주식병합 | reverse split |
| FIN-06-020 | Share Repurchase | 자사주 매입 | buyback |
| FIN-06-021 | Tender Offer | 공개매수 | tender |
| FIN-06-022 | Dutch Auction Tender | 더치옥션 공개매수 | modified Dutch auction |
| FIN-06-023 | Equity-Linked Offering | 주식연계증권 발행 | equity linked |
| FIN-06-024 | Convertible Bond Offering | 전환사채 발행 | CB offering |
| FIN-06-025 | Exchangeable Bond Offering | 교환사채 발행 | EB offering |
| FIN-06-026 | Bond with Warrant Offering | 신주인수권부사채 발행 | BW offering |
| FIN-06-027 | Investment-Grade Bond Offering | 투자등급 회사채 발행 | IG issuance |
| FIN-06-028 | High-Yield Bond Offering | 하이일드채 발행 | HY issuance |
| FIN-06-029 | Medium-Term Note Program | 중기채 프로그램 | MTN |
| FIN-06-030 | Commercial Paper Program | 기업어음 발행 프로그램 | CP program |
| FIN-06-031 | Liability Management Exercise | 부채관리 거래 | LME |
| FIN-06-032 | Debt Tender Offer | 채권 공개매입 | debt tender |
| FIN-06-033 | Consent Solicitation | 채권자 동의요청 | consent |
| FIN-06-034 | Exchange Offer | 교환제안 | exchange offer |
| FIN-06-035 | Debt Refinancing | 차환조달 | refinancing |
| FIN-06-036 | Recapitalization | 자본재조정 | recap |
| FIN-06-037 | Merger | 합병 | statutory merger |
| FIN-06-038 | Acquisition | 인수 | acquisition |
| FIN-06-039 | Stock Purchase | 주식 인수 | share purchase |
| FIN-06-040 | Asset Purchase | 영업·자산 양수 | asset deal |
| FIN-06-041 | Buy-Side M&A | 인수자측 M&A | buy-side advisory |
| FIN-06-042 | Sell-Side M&A | 매도자측 M&A | sell-side advisory |
| FIN-06-043 | Friendly Takeover | 우호적 인수 | friendly deal |
| FIN-06-044 | Hostile Takeover | 적대적 인수 | hostile bid |
| FIN-06-045 | Management Buyout | 경영자 인수 | MBO |
| FIN-06-046 | Leveraged Buyout | 차입매수 | LBO |
| FIN-06-047 | Public-to-Private Transaction | 상장폐지형 인수 | P2P / take-private |
| FIN-06-048 | Divestiture | 사업매각 | divestment |
| FIN-06-049 | Carve-Out | 사업부 분리매각 | carveout |
| FIN-06-050 | Equity Carve-Out | 자회사 일부 상장 | equity carve-out |
| FIN-06-051 | Spin-Off | 인적분할형 독립 | spin off |
| FIN-06-052 | Split-Off | 교환형 분할 | split off |
| FIN-06-053 | Demerger | 회사분할 | corporate separation |
| FIN-06-054 | Joint Venture | 합작투자 | JV |
| FIN-06-055 | Strategic Alliance | 전략적 제휴 | alliance |
| FIN-06-056 | Minority Investment | 소수지분 투자 | minority stake |
| FIN-06-057 | Strategic Investment | 전략적 투자 | SI investment |
| FIN-06-058 | Financial Investment | 재무적 투자 | FI investment |
| FIN-06-059 | Acquisition Financing | 인수금융 거래 | acquisition finance |
| FIN-06-060 | Bridge Financing | 브리지 파이낸싱 | bridge |
| FIN-06-061 | Syndicated Loan | 신디케이티드론 | syndication |
| FIN-06-062 | Club Deal | 클럽딜 | club financing |
| FIN-06-063 | Project Financing | 프로젝트금융 거래 | PF deal |
| FIN-06-064 | Real Estate Project Financing | 부동산 PF | real estate PF |
| FIN-06-065 | Infrastructure Financing | 인프라 금융거래 | infrastructure deal |
| FIN-06-066 | Securitization Transaction | 자산유동화 거래 | securitization |
| FIN-06-067 | Restructuring | 기업구조조정 | restructuring |
| FIN-06-068 | Out-of-Court Restructuring | 사적 구조조정 | workout |
| FIN-06-069 | Debt-to-Equity Swap | 출자전환 | DES |
| FIN-06-070 | Debtor-in-Possession Financing | 회생기업 신규금융 | DIP financing |
| FIN-06-071 | Bankruptcy Reorganization | 법정회생 | Chapter 11 / rehabilitation |
| FIN-06-072 | Liquidation | 청산 | winding-up |

---

## 07. 딜 실행·자금조달 프로세스

- Primary type: `PROCESS / ACTIVITY`
- 기본 레퍼런스: [S07] [S14] [S25] [S26]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-07-001 | Origination | 딜 소싱·발굴 | deal origination |
| FIN-07-002 | Client Pitch | 고객 제안 | pitch |
| FIN-07-003 | Beauty Contest | 주관사 선정 경쟁 프레젠테이션 | bank bake-off |
| FIN-07-004 | Mandate | 주관·자문 위임 | engagement mandate |
| FIN-07-005 | Engagement Letter Execution | 자문계약서 | engagement agreement |
| FIN-07-006 | Kick-Off Meeting | 착수회의 | kick-off |
| FIN-07-007 | Deal Team Formation | 딜팀 구성 | team staffing |
| FIN-07-008 | Transaction Timetable | 거래 일정 수립 | deal calendar |
| FIN-07-009 | Confidentiality Agreement Execution | 비밀유지계약 | NDA / CA |
| FIN-07-010 | Conflict Check | 이해상충 점검 | conflicts clearance |
| FIN-07-011 | Know Your Client Review | 고객확인 심사 | KYC review |
| FIN-07-012 | Due Diligence | 실사 | DD |
| FIN-07-013 | Virtual Data Room Setup | 가상자료실 구축 | VDR setup |
| FIN-07-014 | Data Room Review | 자료실 검토 | data-room diligence |
| FIN-07-015 | Question and Answer Process | 실사 질의응답 | Q&A |
| FIN-07-016 | Management Interview | 경영진 인터뷰 | management session |
| FIN-07-017 | Site Visit | 현장실사 | site inspection |
| FIN-07-018 | Financial Modeling | 재무모델링 | model build |
| FIN-07-019 | Valuation Analysis | 가치평가 | valuation work |
| FIN-07-020 | Capital Structure Analysis | 자본구조 분석 | capital structure review |
| FIN-07-021 | Transaction Structuring | 거래구조 설계 | deal structuring |
| FIN-07-022 | Financing Structure Design | 조달구조 설계 | financing mix |
| FIN-07-023 | Buyer Universe Development | 잠재매수자 목록 작성 | buyer list |
| FIN-07-024 | Investor Targeting | 투자자 타기팅 | investor targeting |
| FIN-07-025 | Teaser Distribution | 티저 배포 | teaser launch |
| FIN-07-026 | Confidential Information Memorandum Distribution | 투자설명자료 배포 | CIM distribution |
| FIN-07-027 | Process Letter Distribution | 절차안내문 배포 | process letter |
| FIN-07-028 | Indication of Interest | 예비 인수의향 | IOI |
| FIN-07-029 | Non-Binding Offer | 비구속적 제안 | NBO |
| FIN-07-030 | Letter of Intent Submission | 인수의향서 | LOI |
| FIN-07-031 | Binding Offer | 구속적 인수제안 | final bid |
| FIN-07-032 | Exclusivity | 독점협상 | exclusivity period |
| FIN-07-033 | Negotiation | 조건협상 | deal negotiation |
| FIN-07-034 | Definitive Agreement Drafting | 본계약서 작성 | definitive docs |
| FIN-07-035 | Signing | 계약 체결 | signing |
| FIN-07-036 | Conditions Precedent Satisfaction | 선행조건 충족 | CP satisfaction |
| FIN-07-037 | Regulatory Approval | 규제 승인 | reg approval |
| FIN-07-038 | Antitrust Review | 기업결합 심사 | competition clearance |
| FIN-07-039 | Shareholder Approval | 주주승인 | shareholder vote |
| FIN-07-040 | Financing Commitment | 인수자금 확약 | commitment financing |
| FIN-07-041 | Closing | 거래종결 | completion |
| FIN-07-042 | Post-Closing Adjustment | 종결 후 가격조정 | closing adjustment |
| FIN-07-043 | Purchase Price Adjustment | 매매대금 조정 | PPA adjustment |
| FIN-07-044 | Integration Planning | 인수 후 통합 계획 | PMI planning |
| FIN-07-045 | Post-Merger Integration | 합병 후 통합 | PMI |
| FIN-07-046 | Underwriter Selection | 주관사 선정 | bank selection |
| FIN-07-047 | Equity Story Development | 상장 투자포인트 개발 | equity story |
| FIN-07-048 | IPO Readiness Assessment | 상장 준비도 진단 | IPO readiness |
| FIN-07-049 | Pre-Filing Consultation | 사전협의 | pre-filing |
| FIN-07-050 | Registration Statement Filing | 증권신고서 제출 | filing |
| FIN-07-051 | Regulatory Review | 감독기관 심사 | review process |
| FIN-07-052 | Prospectus Preparation | 투자설명서 작성 | prospectus drafting |
| FIN-07-053 | Analyst Presentation | 애널리스트 프레젠테이션 | analyst teach-in |
| FIN-07-054 | Investor Education | 투자자 사전교육 | investor education |
| FIN-07-055 | Roadshow | 로드쇼 | management roadshow |
| FIN-07-056 | Bookbuilding | 수요예측 / 주문집계 | book build |
| FIN-07-057 | Offering Price Discovery | 가격발견 | pricing discovery |
| FIN-07-058 | Offer Price Determination | 공모가 결정 | pricing |
| FIN-07-059 | Allocation | 배정 | share allocation |
| FIN-07-060 | Underwriting | 증권 인수 | firm commitment underwriting |
| FIN-07-061 | Stabilization | 시장안정조치 | price stabilization |
| FIN-07-062 | Greenshoe Exercise | 초과배정옵션 행사 | over-allotment option |
| FIN-07-063 | Lock-Up Arrangement | 의무보유·매각제한 | lock-up |
| FIN-07-064 | Listing | 상장 | admission to trading |
| FIN-07-065 | Rating Process | 신용평가 절차 | rating engagement |
| FIN-07-066 | Bond Investor Marketing | 채권 투자자 마케팅 | debt roadshow |
| FIN-07-067 | Order Book Management | 주문장 관리 | book management |
| FIN-07-068 | Bond Pricing | 채권 발행조건 결정 | pricing call |
| FIN-07-069 | Syndication | 대주단·인수단 구성 | syndication process |
| FIN-07-070 | Deal Settlement | 결제 | closing and settlement |
| FIN-07-071 | Tombstone Announcement | 딜 실적 광고 | tombstone |

---

## 08. 실사(Due Diligence) 세부 유형 및 검토항목

- Primary type: `ACTIVITY / ARTIFACT`
- 기본 레퍼런스: [S07] [S22] [S23] [S25]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-08-001 | Buy-Side Due Diligence | 인수자측 실사 | buy-side DD |
| FIN-08-002 | Vendor Due Diligence | 매도자측 사전실사 | VDD |
| FIN-08-003 | Financial Due Diligence | 재무실사 | FDD |
| FIN-08-004 | Commercial Due Diligence | 상업실사 | CDD |
| FIN-08-005 | Legal Due Diligence | 법률실사 | LDD |
| FIN-08-006 | Tax Due Diligence | 세무실사 | TDD |
| FIN-08-007 | Operational Due Diligence | 운영실사 | ODD |
| FIN-08-008 | Technical Due Diligence | 기술실사 | tech DD |
| FIN-08-009 | IT Due Diligence | IT 실사 | IT DD |
| FIN-08-010 | Cybersecurity Due Diligence | 사이버보안 실사 | cyber DD |
| FIN-08-011 | Human Resources Due Diligence | 인사·노무 실사 | HR DD |
| FIN-08-012 | Environmental Due Diligence | 환경실사 | environmental DD |
| FIN-08-013 | ESG Due Diligence | ESG 실사 | ESG DD |
| FIN-08-014 | Regulatory Due Diligence | 규제실사 | regulatory DD |
| FIN-08-015 | Insurance Due Diligence | 보험실사 | insurance DD |
| FIN-08-016 | Intellectual Property Due Diligence | 지식재산 실사 | IP DD |
| FIN-08-017 | Accounting Due Diligence | 회계실사 | accounting DD |
| FIN-08-018 | Quality of Earnings Analysis | 이익의 질 분석 | QoE |
| FIN-08-019 | Normalized EBITDA Analysis | 정상화 EBITDA 분석 | EBITDA normalization |
| FIN-08-020 | Net Debt Analysis | 순차입금 분석 | net debt review |
| FIN-08-021 | Working Capital Analysis | 운전자본 분석 | NWC review |
| FIN-08-022 | Customer Concentration Review | 고객집중도 검토 | customer concentration |
| FIN-08-023 | Supplier Concentration Review | 공급자집중도 검토 | supplier concentration |
| FIN-08-024 | Contract Review | 계약 검토 | material contracts |
| FIN-08-025 | Contingent Liability Review | 우발부채 검토 | contingencies |
| FIN-08-026 | Off-Balance-Sheet Liability Review | 부외부채 검토 | off-BS review |
| FIN-08-027 | Change-of-Control Review | 지배권변경 조항 검토 | CoC review |
| FIN-08-028 | Related-Party Transaction Review | 특수관계자 거래 검토 | RPT review |
| FIN-08-029 | Red Flag Review | 핵심위험 검토 | red flag |
| FIN-08-030 | Bring-Down Due Diligence | 종결 직전 재확인 실사 | bring-down DD |
| FIN-08-031 | Comfort Letter Procedure | 컴포트레터 절차 | accountant comfort |
| FIN-08-032 | Management Representation | 경영진 확인서 | management rep |
| FIN-08-033 | Material Adverse Change Review | 중대한 부정적 변화 검토 | MAC review |

---

## 09. 기업가치평가·재무모델링 방법론

- Primary type: `METHODOLOGY / MODEL`
- 기본 레퍼런스: [S03] [S05] [S07] [S10] [S17]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-09-001 | Intrinsic Valuation | 내재가치평가 | intrinsic value method |
| FIN-09-002 | Relative Valuation | 상대가치평가 | relative value method |
| FIN-09-003 | Discounted Cash Flow | 현금흐름할인법 | DCF |
| FIN-09-004 | Free Cash Flow to Firm Model | 기업잉여현금흐름 모형 | FCFF model |
| FIN-09-005 | Free Cash Flow to Equity Model | 주주잉여현금흐름 모형 | FCFE model |
| FIN-09-006 | Dividend Discount Model | 배당할인모형 | DDM |
| FIN-09-007 | Gordon Growth Model | 고든성장모형 | GGM |
| FIN-09-008 | Two-Stage Dividend Discount Model | 2단계 배당할인모형 | two-stage DDM |
| FIN-09-009 | Three-Stage Dividend Discount Model | 3단계 배당할인모형 | three-stage DDM |
| FIN-09-010 | Adjusted Present Value | 조정현재가치법 | APV |
| FIN-09-011 | Residual Income Model | 잔여이익모형 | RIM |
| FIN-09-012 | Economic Value Added Valuation | 경제적부가가치 평가 | EVA valuation |
| FIN-09-013 | Comparable Companies Analysis | 유사기업 비교평가 | Trading Comps / CCA |
| FIN-09-014 | Precedent Transactions Analysis | 유사거래 비교평가 | Transaction Comps / PTA |
| FIN-09-015 | Sum-of-the-Parts Valuation | 사업부문별 합산가치평가 | SOTP |
| FIN-09-016 | Net Asset Value Valuation | 순자산가치 평가 | NAV method |
| FIN-09-017 | Revalued Net Asset Value | 재평가순자산가치 | RNAV |
| FIN-09-018 | Liquidation Value | 청산가치 | liquidation analysis |
| FIN-09-019 | Replacement Cost Valuation | 대체원가 평가 | replacement cost |
| FIN-09-020 | Leveraged Buyout Analysis | 차입매수 분석 | LBO analysis |
| FIN-09-021 | Venture Capital Method | 벤처캐피털 평가법 | VC method |
| FIN-09-022 | First Chicago Method | 퍼스트시카고법 | First Chicago |
| FIN-09-023 | Option-Based Valuation | 옵션기반 가치평가 | real-option approach |
| FIN-09-024 | Real Options Analysis | 실물옵션 분석 | real options |
| FIN-09-025 | Football Field Valuation | 풋볼필드 가치평가 | football field |
| FIN-09-026 | Enterprise Value to Equity Value Bridge | 기업가치-주주가치 브리지 | EV bridge |
| FIN-09-027 | Three-Statement Model | 3개 재무제표 연계모형 | 3-statement model |
| FIN-09-028 | Operating Model | 영업모형 | operating forecast model |
| FIN-09-029 | Revenue Build | 매출추정 모델 | revenue model |
| FIN-09-030 | Cost Build | 비용추정 모델 | cost model |
| FIN-09-031 | Segment Model | 사업부문 모델 | segment build |
| FIN-09-032 | Earnings Model | 실적추정 모델 | earnings model |
| FIN-09-033 | Debt Schedule | 부채 스케줄 | debt model |
| FIN-09-034 | Interest Schedule | 이자비용 스케줄 | interest schedule |
| FIN-09-035 | Fixed Asset Schedule | 유형자산 스케줄 | PPE schedule |
| FIN-09-036 | Working Capital Schedule | 운전자본 스케줄 | NWC schedule |
| FIN-09-037 | Tax Schedule | 세금 스케줄 | tax model |
| FIN-09-038 | Share Count Schedule | 주식수 스케줄 | share schedule |
| FIN-09-039 | Merger Modeling Method | 합병모형 | M&A model |
| FIN-09-040 | Accretion-Dilution Analysis | 주당가치 증감 분석 | accretion/dilution |
| FIN-09-041 | Purchase Price Allocation | 인수가격배분 | PPA |
| FIN-09-042 | Pro Forma Financial Statements | 가정 결합재무제표 | pro forma |
| FIN-09-043 | Sources and Uses | 자금조달·사용표 | sources & uses |
| FIN-09-044 | Leveraged Buyout Model | LBO 모형 | buyout model |
| FIN-09-045 | Cash Sweep | 현금흐름 부채상환 구조 | cash sweep model |
| FIN-09-046 | Returns Model | 투자수익률 모형 | returns analysis |
| FIN-09-047 | Waterfall Model | 분배워터폴 모형 | waterfall |
| FIN-09-048 | Cap Table Model | 지분구조표 | capitalization table |
| FIN-09-049 | Valuation Scenario Analysis | 시나리오 분석 | scenario |
| FIN-09-050 | Valuation Sensitivity Analysis | 민감도 분석 | sensitivity table |
| FIN-09-051 | Data Table Analysis | 데이터테이블 분석 | Excel data table |
| FIN-09-052 | Monte Carlo Simulation | 몬테카를로 시뮬레이션 | MCS |
| FIN-09-053 | Break-Even Analysis | 손익분기 분석 | BEP analysis |
| FIN-09-054 | Contribution Margin Analysis | 공헌이익 분석 | CM analysis |
| FIN-09-055 | Unit Economics Analysis | 단위경제성 분석 | unit economics |
| FIN-09-056 | Cohort Analysis | 코호트 분석 | cohort |
| FIN-09-057 | Common-Size Analysis | 공통형 재무제표 분석 | vertical analysis |
| FIN-09-058 | Horizontal Analysis | 추세분석 | horizontal analysis |
| FIN-09-059 | DuPont Analysis | 듀퐁분석 | DuPont |
| FIN-09-060 | Calendarization | 회계기간 조정 | calendarize |
| FIN-09-061 | Last Twelve Months | 최근 12개월 | LTM |
| FIN-09-062 | Next Twelve Months | 향후 12개월 | NTM |
| FIN-09-063 | Stub Period | 부분기간 | stub |
| FIN-09-064 | Annualization | 연율화 | annualize |
| FIN-09-065 | Normalization | 정상화 조정 | normalized earnings |
| FIN-09-066 | Non-Recurring Item Adjustment | 비경상항목 조정 | one-off adjustment |
| FIN-09-067 | Control Premium Analysis | 경영권 프리미엄 분석 | control premium |
| FIN-09-068 | Minority Discount Analysis | 소수지분 할인 분석 | DLOC |
| FIN-09-069 | Marketability Discount | 유동성·시장성 할인 | DLOM |
| FIN-09-070 | Synergy Valuation | 시너지 가치평가 | synergy value |
| FIN-09-071 | Terminal Value | 계속가치 | TV |
| FIN-09-072 | Perpetuity Growth Method | 영구성장법 | PGM |
| FIN-09-073 | Exit Multiple Method | Exit multiple 방식 | exit method |
| FIN-09-074 | Mid-Year Convention | 중간연도 할인 관행 | mid-year |
| FIN-09-075 | Weighted Average Cost of Capital | 가중평균자본비용 | WACC |
| FIN-09-076 | Cost of Equity | 자기자본비용 | Ke |
| FIN-09-077 | Cost of Debt | 타인자본비용 | Kd |
| FIN-09-078 | Capital Asset Pricing Model | 자본자산가격결정모형 | CAPM |
| FIN-09-079 | Build-Up Method | 가산식 자본비용 추정 | build-up |
| FIN-09-080 | Unlevered Beta | 무부채베타 | asset beta |
| FIN-09-081 | Relevered Beta | 재레버드 베타 | equity beta |
| FIN-09-082 | Country Risk Premium | 국가위험프리미엄 | CRP |
| FIN-09-083 | Equity Risk Premium | 주식위험프리미엄 | ERP |
| FIN-09-084 | Risk-Free Rate | 무위험수익률 | Rf |
| FIN-09-085 | Terminal Growth Rate | 영구성장률 | TGR |

---

## 10. 기업·산업 리서치 용어

- Primary type: `ACTIVITY / EVENT / ARTIFACT`
- 기본 레퍼런스: [S03] [S05] [S10] [S14] [S25]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-10-001 | Company Research | 기업분석 | company analysis |
| FIN-10-002 | Industry Research | 산업분석 | sector research |
| FIN-10-003 | Macro Analysis | 거시경제분석 | macro analysis |
| FIN-10-004 | Investment Thesis | 투자논거 | thesis |
| FIN-10-005 | Variant Perception | 시장과 다른 핵심 견해 | variant view |
| FIN-10-006 | Catalyst | 촉매 / 주가재료 | catalyst |
| FIN-10-007 | Risk Factor | 투자위험요인 | risk |
| FIN-10-008 | Bull Case | 낙관 시나리오 | bull |
| FIN-10-009 | Base Case | 기준 시나리오 | base |
| FIN-10-010 | Bear Case | 비관 시나리오 | bear |
| FIN-10-011 | Earnings Estimate | 실적추정치 | estimate |
| FIN-10-012 | Consensus Estimate | 시장 컨센서스 | consensus |
| FIN-10-013 | Earnings Surprise | 실적 서프라이즈 | beat/miss |
| FIN-10-014 | Earnings Beat | 예상 상회 | beat |
| FIN-10-015 | Earnings Miss | 예상 하회 | miss |
| FIN-10-016 | Guidance | 회사 전망치 | management guidance |
| FIN-10-017 | Guidance Raise | 가이던스 상향 | raise |
| FIN-10-018 | Guidance Cut | 가이던스 하향 | cut |
| FIN-10-019 | Estimate Revision | 추정치 변경 | revision |
| FIN-10-020 | Earnings Revision Momentum | 실적추정치 수정 모멘텀 | revision momentum |
| FIN-10-021 | Target Price | 목표주가 | TP |
| FIN-10-022 | Investment Rating | 투자의견 | rating |
| FIN-10-023 | Buy Rating | 매수 의견 | BUY |
| FIN-10-024 | Hold Rating | 중립·보유 의견 | HOLD |
| FIN-10-025 | Sell Rating | 매도 의견 | SELL |
| FIN-10-026 | Initiation of Coverage | 분석개시 | initiation |
| FIN-10-027 | Research Update | 업데이트 보고서 | update note |
| FIN-10-028 | Earnings Preview | 실적 프리뷰 | preview |
| FIN-10-029 | Earnings Review | 실적 리뷰 | post-earnings |
| FIN-10-030 | Morning Meeting | 모닝미팅 | morning call |
| FIN-10-031 | Channel Check | 유통·공급망 점검 | channel check |
| FIN-10-032 | Expert Call | 전문가 인터뷰 | expert network call |
| FIN-10-033 | Management Meeting | 경영진 미팅 | NDR meeting |
| FIN-10-034 | Non-Deal Roadshow | 비딜 로드쇼 | NDR |
| FIN-10-035 | Investor Relations Meeting | IR 미팅 | IR meeting |
| FIN-10-036 | Scuttlebutt Research | 현장 탐문조사 | scuttlebutt |
| FIN-10-037 | Total Addressable Market | 총시장규모 | TAM |
| FIN-10-038 | Serviceable Available Market | 유효시장규모 | SAM |
| FIN-10-039 | Serviceable Obtainable Market | 획득가능시장규모 | SOM |
| FIN-10-040 | Market Share | 시장점유율 | share |
| FIN-10-041 | Competitive Advantage | 경쟁우위 | moat |
| FIN-10-042 | Economic Moat | 경제적 해자 | moat |
| FIN-10-043 | Pricing Power | 가격결정력 | pricing power |
| FIN-10-044 | Switching Cost | 전환비용 | switching costs |
| FIN-10-045 | Network Effect | 네트워크 효과 | network effects |
| FIN-10-046 | Operating Leverage | 영업레버리지 | op leverage |
| FIN-10-047 | Financial Leverage | 재무레버리지 | fin leverage |
| FIN-10-048 | Volume-Price-Mix Analysis | 물량·가격·믹스 분석 | VPM |
| FIN-10-049 | Average Selling Price | 평균판매가격 | ASP |
| FIN-10-050 | Product Mix | 제품믹스 | mix |
| FIN-10-051 | Backlog | 수주잔고 | order backlog |
| FIN-10-052 | Customer Order Book | 수주장부 | orders |
| FIN-10-053 | Book-to-Bill Ratio | 수주출하비율 | book-to-bill |
| FIN-10-054 | Production Capacity | 생산능력 | capacity |
| FIN-10-055 | Capacity Utilization | 가동률 | utilization |
| FIN-10-056 | Capital Allocation | 자본배분 | capital allocation |
| FIN-10-057 | Management Quality | 경영진 역량 | management assessment |
| FIN-10-058 | Corporate Governance Analysis | 지배구조 분석 | governance review |
| FIN-10-059 | Related-Party Transaction | 특수관계자 거래 | RPT |
| FIN-10-060 | Segment Analysis | 사업부문 분석 | segment review |
| FIN-10-061 | Peer Group | 비교기업군 | peer set |
| FIN-10-062 | Peer Benchmarking | 동종기업 비교 | peer comparison |
| FIN-10-063 | Investment Case Update | 투자논거 업데이트 | thesis update |
| FIN-10-064 | Materiality Assessment | 중요성 평가 | materiality |
| FIN-10-065 | Event Impact Analysis | 이벤트 영향분석 | impact analysis |

---

## 11. 회계·재무제표 개념

- Primary type: `ACCOUNTING_CONCEPT`
- 기본 레퍼런스: [S16] [S17] [S25] [S27]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-11-001 | Financial Statements | 재무제표 | FS |
| FIN-11-002 | Statement of Financial Position | 재무상태표 | balance sheet / BS |
| FIN-11-003 | Income Statement | 손익계산서 | statement of profit or loss / IS |
| FIN-11-004 | Statement of Comprehensive Income | 포괄손익계산서 | SCI |
| FIN-11-005 | Statement of Cash Flows | 현금흐름표 | cash flow statement / CFS |
| FIN-11-006 | Statement of Changes in Equity | 자본변동표 | SOCE |
| FIN-11-007 | Notes to Financial Statements | 재무제표 주석 | notes |
| FIN-11-008 | Consolidated Financial Statements | 연결재무제표 | consolidated FS |
| FIN-11-009 | Separate Financial Statements | 별도재무제표 | separate FS |
| FIN-11-010 | Interim Financial Statements | 중간재무제표 | interim FS |
| FIN-11-011 | Revenue | 매출액 | sales / turnover |
| FIN-11-012 | Cost of Sales | 매출원가 | COGS |
| FIN-11-013 | Gross Profit | 매출총이익 | gross margin dollars |
| FIN-11-014 | Selling General and Administrative Expense | 판매비와관리비 | SG&A |
| FIN-11-015 | Research and Development Expense | 연구개발비 | R&D |
| FIN-11-016 | Operating Profit | 영업이익 | operating income / EBIT in some contexts |
| FIN-11-017 | Finance Income | 금융수익 | finance income |
| FIN-11-018 | Finance Cost | 금융비용 | finance expense |
| FIN-11-019 | Interest Income | 이자수익 | interest revenue |
| FIN-11-020 | Interest Expense | 이자비용 | interest cost |
| FIN-11-021 | Profit Before Tax | 법인세비용차감전순이익 | PBT / EBT |
| FIN-11-022 | Income Tax Expense | 법인세비용 | tax expense |
| FIN-11-023 | Net Income | 당기순이익 | profit for the period |
| FIN-11-024 | Profit Attributable to Owners of Parent | 지배기업 소유주 귀속순이익 | controlling NI |
| FIN-11-025 | Non-Controlling Interest Profit | 비지배지분 귀속순이익 | NCI profit |
| FIN-11-026 | Other Comprehensive Income | 기타포괄손익 | OCI |
| FIN-11-027 | Earnings per Share | 주당이익 | EPS |
| FIN-11-028 | Basic Earnings per Share | 기본주당이익 | basic EPS |
| FIN-11-029 | Diluted Earnings per Share | 희석주당이익 | diluted EPS |
| FIN-11-030 | Asset | 자산 | assets |
| FIN-11-031 | Current Asset | 유동자산 | current assets |
| FIN-11-032 | Non-Current Asset | 비유동자산 | non-current assets |
| FIN-11-033 | Cash and Cash Equivalents | 현금및현금성자산 | cash |
| FIN-11-034 | Restricted Cash | 사용제한현금 | restricted cash |
| FIN-11-035 | Trade Receivables | 매출채권 | accounts receivable / AR |
| FIN-11-036 | Other Receivables | 기타채권 | other AR |
| FIN-11-037 | Allowance for Doubtful Accounts | 대손충당금 | loss allowance |
| FIN-11-038 | Inventory | 재고자산 | inventories |
| FIN-11-039 | Prepaid Expense | 선급비용 | prepayment |
| FIN-11-040 | Property Plant and Equipment | 유형자산 | PPE |
| FIN-11-041 | Investment Property | 투자부동산 | IP |
| FIN-11-042 | Right-of-Use Asset | 사용권자산 | ROU asset |
| FIN-11-043 | Intangible Asset | 무형자산 | intangibles |
| FIN-11-044 | Goodwill | 영업권 | goodwill |
| FIN-11-045 | Investment in Associates | 관계기업투자 | associate investment |
| FIN-11-046 | Deferred Tax Asset | 이연법인세자산 | DTA |
| FIN-11-047 | Financial Asset | 금융자산 | financial asset |
| FIN-11-048 | Liability | 부채 | liabilities |
| FIN-11-049 | Current Liability | 유동부채 | current liabilities |
| FIN-11-050 | Non-Current Liability | 비유동부채 | non-current liabilities |
| FIN-11-051 | Trade Payables | 매입채무 | accounts payable / AP |
| FIN-11-052 | Accrued Expense | 미지급비용 | accrual |
| FIN-11-053 | Deferred Revenue | 계약부채 / 이연수익 | contract liability |
| FIN-11-054 | Short-Term Borrowing | 단기차입금 | short-term debt |
| FIN-11-055 | Long-Term Borrowing | 장기차입금 | long-term debt |
| FIN-11-056 | Bonds Payable | 사채 | bond liability |
| FIN-11-057 | Lease Liability | 리스부채 | lease obligation |
| FIN-11-058 | Provision | 충당부채 | provision |
| FIN-11-059 | Contingent Liability | 우발부채 | contingency |
| FIN-11-060 | Deferred Tax Liability | 이연법인세부채 | DTL |
| FIN-11-061 | Shareholders' Equity | 자본 | equity |
| FIN-11-062 | Share Capital | 자본금 | paid-in capital |
| FIN-11-063 | Share Premium | 주식발행초과금 | additional paid-in capital |
| FIN-11-064 | Retained Earnings | 이익잉여금 | RE |
| FIN-11-065 | Other Reserves | 기타자본항목 | reserves |
| FIN-11-066 | Non-Controlling Interests | 비지배지분 | NCI |
| FIN-11-067 | Treasury Shares | 자기주식 | treasury stock |
| FIN-11-068 | Operating Cash Flow | 영업활동현금흐름 | CFO / OCF |
| FIN-11-069 | Investing Cash Flow | 투자활동현금흐름 | CFI |
| FIN-11-070 | Financing Cash Flow | 재무활동현금흐름 | CFF |
| FIN-11-071 | Capital Expenditure | 자본적지출 | Capex |
| FIN-11-072 | Depreciation | 감가상각비 | D&A component |
| FIN-11-073 | Amortization | 무형자산상각비 | amortization |
| FIN-11-074 | Share-Based Compensation | 주식기준보상 | SBC |
| FIN-11-075 | Impairment Loss | 손상차손 | impairment |
| FIN-11-076 | Reversal of Impairment | 손상차손환입 | impairment reversal |
| FIN-11-077 | Foreign Currency Translation Adjustment | 해외사업환산차이 | CTA |
| FIN-11-078 | Revenue Recognition | 수익인식 | revenue recognition |
| FIN-11-079 | Lease Accounting | 리스회계 | lease accounting |
| FIN-11-080 | Expected Credit Loss | 기대신용손실 | ECL |
| FIN-11-081 | Fair Value | 공정가치 | FV |
| FIN-11-082 | Historical Cost | 역사적원가 | historical cost |
| FIN-11-083 | Amortized Cost | 상각후원가 | AC |
| FIN-11-084 | Fair Value Through Profit or Loss | 당기손익-공정가치 | FVTPL |
| FIN-11-085 | Fair Value Through Other Comprehensive Income | 기타포괄손익-공정가치 | FVOCI |
| FIN-11-086 | Business Combination | 사업결합 | business combination accounting |
| FIN-11-087 | Purchase Price Allocation Accounting | 인수가격배분 회계 | PPA accounting |
| FIN-11-088 | Accounting Policy | 회계정책 | accounting policy |
| FIN-11-089 | Accounting Estimate | 회계추정 | accounting estimate |
| FIN-11-090 | Restatement | 재작성 | restatement |
| FIN-11-091 | Prior-Period Error | 전기오류 | prior error |

---

## 12. 기업재무·가치평가 지표

- Primary type: `METRIC`
- 기본 레퍼런스: [S03] [S05] [S09] [S17]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-12-001 | Market Capitalization | 시가총액 | market cap |
| FIN-12-002 | Enterprise Value | 기업가치 | EV / TEV |
| FIN-12-003 | Equity Value | 주주가치 | equity market value |
| FIN-12-004 | Net Debt | 순차입금 | net debt |
| FIN-12-005 | Net Cash | 순현금 | net cash |
| FIN-12-006 | Invested Capital | 투하자본 | IC |
| FIN-12-007 | Working Capital | 운전자본 | WC |
| FIN-12-008 | Net Working Capital | 순운전자본 | NWC |
| FIN-12-009 | Free Cash Flow | 잉여현금흐름 | FCF |
| FIN-12-010 | Free Cash Flow to Firm | 기업잉여현금흐름 | FCFF |
| FIN-12-011 | Free Cash Flow to Equity | 주주잉여현금흐름 | FCFE |
| FIN-12-012 | Earnings Before Interest and Taxes | 이자·세전이익 | EBIT |
| FIN-12-013 | Earnings Before Interest Taxes Depreciation and Amortization | 이자·세금·감가상각 전 이익 | EBITDA |
| FIN-12-014 | Adjusted EBITDA | 조정 EBITDA | adj. EBITDA |
| FIN-12-015 | Net Operating Profit After Tax | 세후영업이익 | NOPAT |
| FIN-12-016 | Funds from Operations | 운영자금지표 | FFO |
| FIN-12-017 | Adjusted Funds from Operations | 조정 운영자금지표 | AFFO |
| FIN-12-018 | Annual Recurring Revenue | 연간반복매출 | ARR |
| FIN-12-019 | Monthly Recurring Revenue | 월간반복매출 | MRR |
| FIN-12-020 | Gross Merchandise Value | 총거래액 | GMV |
| FIN-12-021 | Total Payment Volume | 총결제액 | TPV |
| FIN-12-022 | Bookings | 계약수주액 / 예약매출 | bookings |
| FIN-12-023 | Billings | 청구액 | billings |
| FIN-12-024 | Revenue Growth | 매출성장률 | sales growth |
| FIN-12-025 | Year-over-Year Growth | 전년동기대비 성장률 | YoY |
| FIN-12-026 | Quarter-over-Quarter Growth | 전분기대비 성장률 | QoQ |
| FIN-12-027 | Month-over-Month Growth | 전월대비 성장률 | MoM |
| FIN-12-028 | Compound Annual Growth Rate | 연평균성장률 | CAGR |
| FIN-12-029 | Gross Margin | 매출총이익률 | GM |
| FIN-12-030 | Operating Margin | 영업이익률 | OP margin |
| FIN-12-031 | EBIT Margin | EBIT 마진 | EBIT margin |
| FIN-12-032 | EBITDA Margin | EBITDA 마진 | EBITDA margin |
| FIN-12-033 | Net Profit Margin | 순이익률 | net margin |
| FIN-12-034 | Free Cash Flow Margin | FCF 마진 | FCF margin |
| FIN-12-035 | Return on Equity | 자기자본이익률 | ROE |
| FIN-12-036 | Return on Assets | 총자산이익률 | ROA |
| FIN-12-037 | Return on Invested Capital | 투하자본이익률 | ROIC |
| FIN-12-038 | Return on Capital Employed | 사용자본이익률 | ROCE |
| FIN-12-039 | Return on Tangible Equity | 유형자기자본이익률 | ROTE |
| FIN-12-040 | Asset Turnover | 총자산회전율 | asset turnover |
| FIN-12-041 | Inventory Turnover | 재고자산회전율 | inventory turns |
| FIN-12-042 | Receivables Turnover | 매출채권회전율 | AR turnover |
| FIN-12-043 | Days Sales Outstanding | 매출채권회수기간 | DSO |
| FIN-12-044 | Days Inventory Outstanding | 재고보유일수 | DIO |
| FIN-12-045 | Days Payables Outstanding | 매입채무지급기간 | DPO |
| FIN-12-046 | Cash Conversion Cycle | 현금전환주기 | CCC |
| FIN-12-047 | Current Ratio | 유동비율 | current ratio |
| FIN-12-048 | Quick Ratio | 당좌비율 | quick ratio |
| FIN-12-049 | Cash Ratio | 현금비율 | cash ratio |
| FIN-12-050 | Debt-to-Equity Ratio | 부채비율 / 부채자본비율 | D/E |
| FIN-12-051 | Debt-to-Assets Ratio | 부채자산비율 | D/A |
| FIN-12-052 | Net Debt to EBITDA | 순차입금/EBITDA | ND/EBITDA |
| FIN-12-053 | Gross Debt to EBITDA | 총차입금/EBITDA | Debt/EBITDA |
| FIN-12-054 | Interest Coverage Ratio | 이자보상배율 | ICR |
| FIN-12-055 | Fixed-Charge Coverage Ratio | 고정비용보상배율 | FCCR |
| FIN-12-056 | Debt Service Coverage Ratio | 부채상환커버리지 | DSCR |
| FIN-12-057 | Dividend Yield | 배당수익률 | DY |
| FIN-12-058 | Dividend Payout Ratio | 배당성향 | payout |
| FIN-12-059 | Free Cash Flow Yield | FCF 수익률 | FCF yield |
| FIN-12-060 | Earnings Yield | 이익수익률 | E/P |
| FIN-12-061 | Price-to-Earnings Ratio | 주가수익비율 | PER / P/E |
| FIN-12-062 | Price-to-Book Ratio | 주가순자산비율 | PBR / P/B |
| FIN-12-063 | Price-to-Sales Ratio | 주가매출비율 | PSR / P/S |
| FIN-12-064 | Price-to-Cash-Flow Ratio | 주가현금흐름비율 | P/CF |
| FIN-12-065 | Enterprise Value to Sales | EV/매출 | EV/Sales |
| FIN-12-066 | Enterprise Value to EBITDA | EV/EBITDA | EV/EBITDA |
| FIN-12-067 | Enterprise Value to EBIT | EV/EBIT | EV/EBIT |
| FIN-12-068 | Price/Earnings-to-Growth Ratio | 성장조정 PER | PEG |
| FIN-12-069 | Price Target Upside | 목표주가 상승여력 | upside |
| FIN-12-070 | Fully Diluted Share Count | 완전희석주식수 | FDSO |
| FIN-12-071 | Weighted Average Shares Outstanding | 가중평균유통주식수 | WASO |
| FIN-12-072 | Net Asset Value | 순자산가치 | NAV |
| FIN-12-073 | Tangible Book Value | 유형순자산 | TBV |
| FIN-12-074 | Book Value per Share | 주당순자산 | BPS / BVPS |
| FIN-12-075 | Tangible Book Value per Share | 주당유형순자산 | TBVPS |
| FIN-12-076 | Minority Interest | 비지배지분가치 | NCI value |
| FIN-12-077 | Pension Deficit | 연금부족액 | pension shortfall |
| FIN-12-078 | Capital Intensity | 자본집약도 | capex intensity |
| FIN-12-079 | Research and Development Intensity | 연구개발집약도 | R&D/revenue |
| FIN-12-080 | Effective Tax Rate | 유효세율 | ETR |
| FIN-12-081 | Cash Tax Rate | 현금세율 | cash tax |

---

## 13. 포트폴리오 구성·리스크·성과

- Primary type: `METHODOLOGY / METRIC / RISK`
- 기본 레퍼런스: [S03] [S05] [S11] [S12] [S13] [S18] [S21]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-13-001 | Investment Policy Statement | 투자정책서 | IPS |
| FIN-13-002 | Investment Mandate | 운용지침 | mandate |
| FIN-13-003 | Investment Objective | 투자목표 | objective |
| FIN-13-004 | Investment Universe | 투자가능종목군 | universe |
| FIN-13-005 | Benchmark | 벤치마크 | BM |
| FIN-13-006 | Policy Benchmark | 정책 벤치마크 | policy BM |
| FIN-13-007 | Reference Portfolio | 기준 포트폴리오 | reference portfolio |
| FIN-13-008 | Strategic Asset Allocation Process | 전략적 자산배분 | SAA |
| FIN-13-009 | Portfolio Construction | 포트폴리오 구성 | portfolio build |
| FIN-13-010 | Security Selection | 종목선정 | selection |
| FIN-13-011 | Position Sizing | 포지션 규모 결정 | position sizing |
| FIN-13-012 | Rebalancing | 리밸런싱 | rebalance |
| FIN-13-013 | Optimization | 최적화 | portfolio optimization |
| FIN-13-014 | Mean-Variance Optimization | 평균-분산 최적화 | MVO |
| FIN-13-015 | Efficient Frontier | 효율적 프런티어 | efficient set |
| FIN-13-016 | Capital Market Line | 자본시장선 | CML |
| FIN-13-017 | Security Market Line | 증권시장선 | SML |
| FIN-13-018 | Black-Litterman Model | 블랙리터만 모형 | BL |
| FIN-13-019 | Risk Budgeting | 리스크 버저팅 | risk budget |
| FIN-13-020 | Equal Risk Contribution | 동일위험기여 | ERC |
| FIN-13-021 | Factor Model | 팩터모형 | factor risk model |
| FIN-13-022 | Single-Index Model | 단일지수모형 | SIM |
| FIN-13-023 | Multi-Factor Model | 다요인모형 | MFM |
| FIN-13-024 | Fundamental Factor Model | 펀더멘털 팩터모형 | fundamental risk model |
| FIN-13-025 | Statistical Factor Model | 통계적 팩터모형 | statistical risk model |
| FIN-13-026 | Risk Model | 리스크모형 | risk model |
| FIN-13-027 | Expected Return | 기대수익률 | expected return |
| FIN-13-028 | Portfolio Return | 포트폴리오 수익률 | portfolio performance |
| FIN-13-029 | Total Return | 총수익률 | total return |
| FIN-13-030 | Price Return | 가격수익률 | price return |
| FIN-13-031 | Time-Weighted Return | 시간가중수익률 | TWR |
| FIN-13-032 | Money-Weighted Return | 금액가중수익률 | MWR |
| FIN-13-033 | Internal Rate of Return | 내부수익률 | IRR |
| FIN-13-034 | Modified Internal Rate of Return | 수정내부수익률 | MIRR |
| FIN-13-035 | Public Market Equivalent | 공모시장등가 | PME |
| FIN-13-036 | Alpha | 알파 | excess risk-adjusted return |
| FIN-13-037 | Beta | 베타 | market beta |
| FIN-13-038 | Jensen's Alpha | 젠슨 알파 | Jensen alpha |
| FIN-13-039 | Sharpe Ratio | 샤프지수 | Sharpe |
| FIN-13-040 | Sortino Ratio | 소르티노지수 | Sortino |
| FIN-13-041 | Information Ratio | 정보비율 | IR |
| FIN-13-042 | Treynor Ratio | 트레이너지수 | Treynor |
| FIN-13-043 | Calmar Ratio | 칼마비율 | Calmar |
| FIN-13-044 | Tracking Error | 추적오차 | active risk |
| FIN-13-045 | Active Return | 초과수익률 | benchmark-relative return |
| FIN-13-046 | Active Share | 액티브셰어 | active share |
| FIN-13-047 | Hit Rate | 적중률 | hit ratio |
| FIN-13-048 | Win-Loss Ratio | 손익비 | win/loss |
| FIN-13-049 | Maximum Drawdown | 최대낙폭 | MDD |
| FIN-13-050 | Drawdown Duration | 낙폭 지속기간 | drawdown length |
| FIN-13-051 | Volatility | 변동성 | standard deviation |
| FIN-13-052 | Downside Deviation | 하방편차 | downside risk |
| FIN-13-053 | Correlation | 상관계수 | corr |
| FIN-13-054 | Covariance | 공분산 | cov |
| FIN-13-055 | Value at Risk | 위험가치 | VaR |
| FIN-13-056 | Expected Shortfall | 기대손실 | ES / CVaR |
| FIN-13-057 | Stress Testing | 스트레스테스트 | stress test |
| FIN-13-058 | Risk Scenario Analysis | 시나리오 분석 | scenario risk |
| FIN-13-059 | Risk Sensitivity Analysis | 민감도 분석 | sensitivity |
| FIN-13-060 | Market Risk | 시장리스크 | market risk |
| FIN-13-061 | Credit Risk | 신용리스크 | credit risk |
| FIN-13-062 | Liquidity Risk | 유동성리스크 | liquidity risk |
| FIN-13-063 | Operational Risk | 운영리스크 | op risk |
| FIN-13-064 | Concentration Risk | 집중위험 | concentration |
| FIN-13-065 | Counterparty Risk | 거래상대방위험 | counterparty credit risk |
| FIN-13-066 | Model Risk | 모델리스크 | model risk |
| FIN-13-067 | Basis Risk | 베이시스위험 | basis risk |
| FIN-13-068 | Tail Risk | 꼬리위험 | tail risk |
| FIN-13-069 | Systematic Risk | 체계적위험 | systematic |
| FIN-13-070 | Idiosyncratic Risk | 고유위험 | idiosyncratic |
| FIN-13-071 | Gross Exposure | 총익스포저 | gross |
| FIN-13-072 | Net Exposure | 순익스포저 | net |
| FIN-13-073 | Long Exposure | 롱 익스포저 | long |
| FIN-13-074 | Short Exposure | 숏 익스포저 | short |
| FIN-13-075 | Leverage | 레버리지 | gross leverage |
| FIN-13-076 | Factor Exposure | 팩터노출 | factor loading |
| FIN-13-077 | Risk Contribution | 위험기여도 | risk contribution |
| FIN-13-078 | Marginal Contribution to Risk | 한계위험기여도 | MCR |
| FIN-13-079 | Component Contribution to Risk | 구성위험기여도 | CCR |
| FIN-13-080 | Risk-Adjusted Return | 위험조정수익률 | risk-adjusted performance |
| FIN-13-081 | Portfolio Turnover | 포트폴리오 회전율 | turnover |
| FIN-13-082 | Strategy Capacity | 전략 수용가능 규모 | strategy capacity |
| FIN-13-083 | Liquidity Budget | 유동성 버짓 | liquidity budget |
| FIN-13-084 | Performance Attribution Analysis | 성과요인분석 | attribution |
| FIN-13-085 | Brinson Attribution | 브린슨 성과요인분석 | Brinson |
| FIN-13-086 | Allocation Effect | 자산배분효과 | allocation effect |
| FIN-13-087 | Selection Effect | 종목선택효과 | selection effect |
| FIN-13-088 | Interaction Effect | 상호작용효과 | interaction |
| FIN-13-089 | Contribution Analysis | 수익기여도 분석 | contribution |
| FIN-13-090 | Currency Attribution | 환효과 분석 | FX attribution |
| FIN-13-091 | Factor Attribution | 팩터 성과요인분석 | factor attribution |
| FIN-13-092 | Composite | 성과 공시용 포트폴리오 집합 | GIPS composite |
| FIN-13-093 | Assets Under Management | 운용자산 | AUM |
| FIN-13-094 | Net Asset Value of Fund | 펀드 순자산가치 | fund NAV |
| FIN-13-095 | High-Water Mark | 고수위기준 | HWM |
| FIN-13-096 | Investment Hurdle Rate | 기준수익률 | hurdle |

---

## 14. 트레이딩·시장미시구조·오퍼레이션

- Primary type: `MARKET_INFRA / ACTIVITY / METRIC`
- 기본 레퍼런스: [S08] [S09] [S20] [S26]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-14-001 | Primary Market | 발행시장 | primary |
| FIN-14-002 | Secondary Market | 유통시장 | secondary |
| FIN-14-003 | Exchange-Traded Market | 거래소시장 | lit market |
| FIN-14-004 | Over-the-Counter Market | 장외시장 | OTC |
| FIN-14-005 | Limit Order Book | 호가장 | limit order book / LOB |
| FIN-14-006 | Bid Price | 매수호가 | bid |
| FIN-14-007 | Ask Price | 매도호가 | offer |
| FIN-14-008 | Bid-Ask Spread | 매수매도호가차 | spread |
| FIN-14-009 | Market Depth | 시장심도 | depth |
| FIN-14-010 | Liquidity | 유동성 | liquidity |
| FIN-14-011 | Trading Volume | 거래량 | volume |
| FIN-14-012 | Trading Value | 거래대금 | turnover value |
| FIN-14-013 | Market Turnover | 시장회전율 | turnover |
| FIN-14-014 | Market Price Discovery | 가격발견 | price formation |
| FIN-14-015 | Market Order | 시장가주문 | market |
| FIN-14-016 | Limit Order | 지정가주문 | limit |
| FIN-14-017 | Stop Order | 손절·정지주문 | stop |
| FIN-14-018 | Stop-Limit Order | 스톱리밋주문 | stop limit |
| FIN-14-019 | Immediate-or-Cancel Order | 즉시체결 잔량취소 | IOC |
| FIN-14-020 | Fill-or-Kill Order | 전량즉시체결 아니면 취소 | FOK |
| FIN-14-021 | Good-Till-Cancelled Order | 취소시까지 유효주문 | GTC |
| FIN-14-022 | Iceberg Order | 빙산주문 | reserve order |
| FIN-14-023 | Block Order | 대량주문 | block |
| FIN-14-024 | Auction | 단일가매매 / 경매 | auction |
| FIN-14-025 | Opening Auction | 시가 단일가 | opening cross |
| FIN-14-026 | Closing Auction | 종가 단일가 | closing cross |
| FIN-14-027 | Continuous Trading | 접속매매 | continuous session |
| FIN-14-028 | Dark Pool | 다크풀 | non-displayed venue |
| FIN-14-029 | Crossing Network | 교차매매 네트워크 | crossing system |
| FIN-14-030 | Algorithmic Trading | 알고리즘 매매 | algo trading |
| FIN-14-031 | High-Frequency Trading | 고빈도매매 | HFT |
| FIN-14-032 | Direct Market Access | 직접시장접속 | DMA |
| FIN-14-033 | Smart Order Routing | 스마트 주문라우팅 | SOR |
| FIN-14-034 | Volume-Weighted Average Price | 거래량가중평균가격 | VWAP |
| FIN-14-035 | Time-Weighted Average Price | 시간가중평균가격 | TWAP |
| FIN-14-036 | Implementation Shortfall | 실행부족비용 | IS |
| FIN-14-037 | Slippage | 슬리피지 | slippage |
| FIN-14-038 | Market Impact | 시장충격비용 | impact |
| FIN-14-039 | Transaction Cost Analysis | 거래비용분석 | TCA |
| FIN-14-040 | Best Execution | 최선집행 | best ex |
| FIN-14-041 | Short Sale | 공매도 | short selling |
| FIN-14-042 | Stock Borrow | 주식대차 차입 | borrow |
| FIN-14-043 | Locate | 공매도 주식 확보 확인 | locate |
| FIN-14-044 | Recall | 대차회수 | recall |
| FIN-14-045 | Securities Lending Fee | 대차수수료 | borrow fee |
| FIN-14-046 | Margin | 증거금 | margin |
| FIN-14-047 | Initial Margin | 개시증거금 | IM |
| FIN-14-048 | Variation Margin | 변동증거금 | VM |
| FIN-14-049 | Haircut | 담보할인율 | haircut |
| FIN-14-050 | Collateral | 담보 | collateral |
| FIN-14-051 | Mark-to-Market | 시가평가 | MTM |
| FIN-14-052 | Margin Call | 추가증거금 요구 | margin call |
| FIN-14-053 | Trade Date | 매매일 | T |
| FIN-14-054 | Settlement Date | 결제일 | value date |
| FIN-14-055 | Clearing | 청산 | clearing |
| FIN-14-056 | Securities Settlement | 결제 | settlement |
| FIN-14-057 | Delivery Versus Payment | 증권대금동시결제 | DVP |
| FIN-14-058 | Free of Payment | 무대금 증권이체 | FOP |
| FIN-14-059 | Fail to Deliver | 결제불이행 | FTD |
| FIN-14-060 | Corporate Action Processing | 권리처리 | corporate actions |
| FIN-14-061 | Trade Confirmation | 거래확인서 | confirmation |
| FIN-14-062 | Trade Matching | 거래대사 | matching |
| FIN-14-063 | Reconciliation | 계정·잔고 대사 | recon |
| FIN-14-064 | Straight-Through Processing | 일괄자동처리 | STP |
| FIN-14-065 | Trade Break | 거래불일치 | break |
| FIN-14-066 | Position Reconciliation | 포지션 대사 | position recon |
| FIN-14-067 | Cash Reconciliation | 현금 대사 | cash recon |
| FIN-14-068 | Netting | 상계 | netting |
| FIN-14-069 | Novation | 계약이전·경개 | novation |
| FIN-14-070 | Close-Out Netting | 종료상계 | close-out |

---

## 15. 채권·크레딧 분석

- Primary type: `METRIC / METHODOLOGY / RISK`
- 기본 레퍼런스: [S03] [S05] [S09] [S19]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-15-001 | Par Value | 액면가 | face value |
| FIN-15-002 | Principal | 원금 | principal |
| FIN-15-003 | Coupon Rate | 표면금리 | coupon |
| FIN-15-004 | Coupon Payment | 이표지급 | coupon cash flow |
| FIN-15-005 | Maturity Date | 만기일 | maturity |
| FIN-15-006 | Issue Price | 발행가격 | issue price |
| FIN-15-007 | Clean Price | 클린가격 | clean |
| FIN-15-008 | Dirty Price | 더티가격 | dirty |
| FIN-15-009 | Accrued Interest | 경과이자 | accrued |
| FIN-15-010 | Current Yield | 현재수익률 | current yield |
| FIN-15-011 | Yield to Maturity | 만기수익률 | YTM |
| FIN-15-012 | Yield to Call | 콜수익률 | YTC |
| FIN-15-013 | Yield to Worst | 최저수익률 | YTW |
| FIN-15-014 | Holding Period Return | 보유기간수익률 | HPR |
| FIN-15-015 | Spot Rate | 현물금리 | zero rate |
| FIN-15-016 | Forward Rate | 선도금리 | forward |
| FIN-15-017 | Par Curve | 파수익률곡선 | par curve |
| FIN-15-018 | Spot Curve | 현물수익률곡선 | zero curve |
| FIN-15-019 | Forward Curve | 선도곡선 | forward curve |
| FIN-15-020 | Yield Curve | 수익률곡선 | term structure |
| FIN-15-021 | Curve Bootstrapping | 수익률곡선 부트스트래핑 | bootstrap |
| FIN-15-022 | Duration | 듀레이션 | duration |
| FIN-15-023 | Macaulay Duration | 맥컬레이 듀레이션 | MacDur |
| FIN-15-024 | Modified Duration | 수정 듀레이션 | ModDur |
| FIN-15-025 | Effective Duration | 유효 듀레이션 | effective duration |
| FIN-15-026 | Key Rate Duration | 키레이트 듀레이션 | KRD |
| FIN-15-027 | Dollar Duration | 금액듀레이션 | dollar duration |
| FIN-15-028 | DV01 | 금리 1bp 가치변화 | PVBP / BPV |
| FIN-15-029 | Convexity | 볼록성 | convexity |
| FIN-15-030 | Effective Convexity | 유효볼록성 | effective convexity |
| FIN-15-031 | Spread Duration | 스프레드 듀레이션 | spread dur |
| FIN-15-032 | CS01 | 신용스프레드 1bp 가치변화 | credit DV01 |
| FIN-15-033 | Credit Spread | 신용스프레드 | spread |
| FIN-15-034 | G-Spread | 국채곡선 대비 스프레드 | G-spread |
| FIN-15-035 | I-Spread | 스왑곡선 대비 스프레드 | I-spread |
| FIN-15-036 | Z-Spread | 제로변동성 스프레드 | Z-spread |
| FIN-15-037 | Option-Adjusted Spread | 옵션조정스프레드 | OAS |
| FIN-15-038 | Asset Swap Spread | 자산스왑스프레드 | ASW spread |
| FIN-15-039 | Swap Spread | 스왑스프레드 | swap spread |
| FIN-15-040 | Credit Rating | 신용등급 | rating |
| FIN-15-041 | Investment Grade | 투자등급 | IG |
| FIN-15-042 | High Yield | 투기등급 / 하이일드 | HY |
| FIN-15-043 | Rating Outlook | 등급전망 | outlook |
| FIN-15-044 | Rating Watch | 등급감시 | watch |
| FIN-15-045 | Rating Upgrade | 등급상향 | upgrade |
| FIN-15-046 | Rating Downgrade | 등급하향 | downgrade |
| FIN-15-047 | Credit Migration | 신용등급전이 | migration |
| FIN-15-048 | Default | 부도 | default event |
| FIN-15-049 | Probability of Default | 부도확률 | PD |
| FIN-15-050 | Loss Given Default | 부도시손실률 | LGD |
| FIN-15-051 | Exposure at Default | 부도시익스포저 | EAD |
| FIN-15-052 | Recovery Rate | 회수율 | recovery |
| FIN-15-053 | Expected Loss | 기대손실 | EL |
| FIN-15-054 | Unexpected Loss | 비기대손실 | UL |
| FIN-15-055 | Credit VaR | 신용 VaR | credit value at risk |
| FIN-15-056 | Covenant | 채무약정 | covenant |
| FIN-15-057 | Affirmative Covenant | 적극적 약정 | affirmative covenant |
| FIN-15-058 | Negative Covenant | 소극적 약정 | negative covenant |
| FIN-15-059 | Financial Covenant | 재무약정 | financial covenant |
| FIN-15-060 | Maintenance Covenant | 유지형 약정 | maintenance covenant |
| FIN-15-061 | Incurrence Covenant | 발생형 약정 | incurrence covenant |
| FIN-15-062 | Covenant-Lite | 약정완화형 | cov-lite |
| FIN-15-063 | Seniority | 상환우선순위 | seniority |
| FIN-15-064 | Subordination | 후순위성 | subordination |
| FIN-15-065 | Security Interest | 담보권 | security |
| FIN-15-066 | Collateral Coverage | 담보커버리지 | collateral coverage |
| FIN-15-067 | Structural Subordination | 구조적 후순위 | structural subordination |
| FIN-15-068 | Cross-Default | 교차부도 | cross default |
| FIN-15-069 | Cross-Acceleration | 교차기한이익상실 | cross acceleration |
| FIN-15-070 | Event of Default | 기한이익상실 사유 | EOD |
| FIN-15-071 | Call Protection | 조기상환 보호 | call protection |
| FIN-15-072 | Make-Whole Provision | 메이크홀 조항 | make-whole |
| FIN-15-073 | Sinking Fund | 감채기금 | sinking fund |
| FIN-15-074 | Credit Curve | 신용곡선 | spread curve |
| FIN-15-075 | Carry and Roll-Down | 캐리와 롤다운 | carry/roll |

---

## 16. 파생상품·헤지·옵션 지표

- Primary type: `INSTRUMENT / METRIC / ACTIVITY`
- 기본 레퍼런스: [S03] [S20] [S23]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-16-001 | Underlying Asset | 기초자산 | underlying |
| FIN-16-002 | Notional Amount | 명목금액 | notional |
| FIN-16-003 | Effective Date | 효력발생일 | effective date |
| FIN-16-004 | Termination Date | 종료일 | maturity |
| FIN-16-005 | Settlement Amount | 결제금액 | settlement amount |
| FIN-16-006 | Physical Settlement | 실물인수도 | physical delivery |
| FIN-16-007 | Cash Settlement | 현금결제 | cash settled |
| FIN-16-008 | Strike Price | 행사가격 | strike / exercise price |
| FIN-16-009 | Option Premium | 옵션프리미엄 | premium |
| FIN-16-010 | Expiration Date | 만기일 | expiry |
| FIN-16-011 | Exercise Style | 권리행사 방식 | style |
| FIN-16-012 | European Option | 유럽형 옵션 | European |
| FIN-16-013 | American Option | 미국형 옵션 | American |
| FIN-16-014 | Bermudan Option | 버뮤다형 옵션 | Bermudan |
| FIN-16-015 | In the Money | 내가격 | ITM |
| FIN-16-016 | At the Money | 등가격 | ATM |
| FIN-16-017 | Out of the Money | 외가격 | OTM |
| FIN-16-018 | Intrinsic Value | 내재가치 | intrinsic |
| FIN-16-019 | Time Value | 시간가치 | time value |
| FIN-16-020 | Implied Volatility | 내재변동성 | IV |
| FIN-16-021 | Realized Volatility | 실현변동성 | RV |
| FIN-16-022 | Historical Volatility | 역사적변동성 | HV |
| FIN-16-023 | Volatility Smile | 변동성 스마일 | smile |
| FIN-16-024 | Volatility Skew | 변동성 스큐 | skew |
| FIN-16-025 | Volatility Surface | 변동성 표면 | vol surface |
| FIN-16-026 | Delta | 델타 | option delta |
| FIN-16-027 | Gamma | 감마 | gamma |
| FIN-16-028 | Vega | 베가 | vega |
| FIN-16-029 | Theta | 세타 | theta |
| FIN-16-030 | Rho | 로 | rho |
| FIN-16-031 | Charm | 참 | charm |
| FIN-16-032 | Vanna | 바나 | vanna |
| FIN-16-033 | Volga | 볼가 | vomma |
| FIN-16-034 | Delta Hedging | 델타헤지 | delta hedge |
| FIN-16-035 | Gamma Hedging | 감마헤지 | gamma hedge |
| FIN-16-036 | Vega Hedging | 베가헤지 | vega hedge |
| FIN-16-037 | Dynamic Hedging | 동적헤지 | dynamic hedge |
| FIN-16-038 | Static Hedging | 정적헤지 | static hedge |
| FIN-16-039 | Cross Hedge | 교차헤지 | cross hedge |
| FIN-16-040 | Proxy Hedge | 대용헤지 | proxy hedge |
| FIN-16-041 | Hedge Ratio | 헤지비율 | hedge ratio |
| FIN-16-042 | Minimum-Variance Hedge Ratio | 최소분산 헤지비율 | MVHR |
| FIN-16-043 | Basis | 베이시스 | basis |
| FIN-16-044 | Contango | 콘탱고 | contango |
| FIN-16-045 | Backwardation | 백워데이션 | backwardation |
| FIN-16-046 | Roll Yield | 롤수익률 | roll yield |
| FIN-16-047 | Forward Points | 선물환 포인트 | forward points |
| FIN-16-048 | Interest Rate Differential | 금리차 | carry differential |
| FIN-16-049 | Swap Fixed Leg | 스왑 고정금리부 | fixed leg |
| FIN-16-050 | Swap Floating Leg | 스왑 변동금리부 | floating leg |
| FIN-16-051 | Reference Rate | 참조금리 | benchmark rate |
| FIN-16-052 | Reset Date | 금리재설정일 | reset |
| FIN-16-053 | Payment Date | 지급일 | payment date |
| FIN-16-054 | Net Present Value of Swap | 스왑 순현재가치 | NPV |
| FIN-16-055 | Credit Event | 신용사건 | credit event |
| FIN-16-056 | Protection Buyer | 보장매수자 | CDS buyer |
| FIN-16-057 | Protection Seller | 보장매도자 | CDS seller |
| FIN-16-058 | CDS Premium Leg | CDS 프리미엄 레그 | fee leg |
| FIN-16-059 | CDS Protection Leg | CDS 보호 레그 | default leg |
| FIN-16-060 | ISDA Master Agreement | ISDA 기본계약 | ISDA Master |
| FIN-16-061 | Credit Support Annex | 담보부속계약 | CSA |
| FIN-16-062 | Close-Out Amount | 종료정산금액 | close-out amount |
| FIN-16-063 | Eligible Collateral | 적격담보 | eligible collateral |

---

## 17. 대체투자·사모시장

- Primary type: `STRATEGY / METRIC / PROCESS`
- 기본 레퍼런스: [S22] [S23] [S24] [S03]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-17-001 | Private Capital | 사모자본 | private markets |
| FIN-17-002 | Closed-End Private Fund Structure | 폐쇄형 사모펀드 | closed-end vehicle |
| FIN-17-003 | Open-End Fund Structure | 개방형 펀드구조 | open-ended vehicle |
| FIN-17-004 | Evergreen Fund | 에버그린 펀드 | evergreen |
| FIN-17-005 | Limited Partnership Agreement | 유한책임조합계약 | LPA |
| FIN-17-006 | Committed Capital | 약정총액 | commitment |
| FIN-17-007 | Called Capital | 납입요청 자본 | contributed capital |
| FIN-17-008 | Paid-In Capital | 납입자본 | PIC |
| FIN-17-009 | Uncalled Capital | 미납입 약정액 | unfunded commitment |
| FIN-17-010 | Dry Powder | 미투자 약정자금 | dry powder |
| FIN-17-011 | Capital Call | 출자금 납입요청 | drawdown |
| FIN-17-012 | Fund Distribution Payment | 분배금 | distribution |
| FIN-17-013 | Recallable Distribution | 재호출 가능 분배금 | recallable |
| FIN-17-014 | Fund Vintage Year | 펀드 빈티지 | vintage |
| FIN-17-015 | Investment Period | 투자기간 | commitment period |
| FIN-17-016 | Harvest Period | 회수기간 | harvest |
| FIN-17-017 | Fund Term | 펀드 존속기간 | term |
| FIN-17-018 | Extension Period | 연장기간 | extension |
| FIN-17-019 | Management Fee | 관리보수 | management fee |
| FIN-17-020 | Carried Interest | 성과보수 | carry |
| FIN-17-021 | Preferred Return | 우선수익률 | pref |
| FIN-17-022 | Performance Fee Hurdle Rate | 기준수익률 | hurdle |
| FIN-17-023 | Catch-Up | 캐치업 | GP catch-up |
| FIN-17-024 | Distribution Waterfall | 분배 워터폴 | waterfall |
| FIN-17-025 | European Waterfall | 유럽식 워터폴 | whole-fund waterfall |
| FIN-17-026 | American Waterfall | 미국식 워터폴 | deal-by-deal waterfall |
| FIN-17-027 | Clawback | 성과보수 환수 | GP clawback |
| FIN-17-028 | Key Person Clause | 핵심인력 조항 | key-man clause |
| FIN-17-029 | No-Fault Divorce | 무과실 GP 해임 | no-fault removal |
| FIN-17-030 | Most-Favored Nation Clause | 최혜대우 조항 | MFN |
| FIN-17-031 | Side Letter | 사이드레터 | side agreement |
| FIN-17-032 | Advisory Committee | LP 자문위원회 | LPAC |
| FIN-17-033 | Co-Investment | 공동투자 | co-invest |
| FIN-17-034 | Fund of Funds Vehicle | 재간접 사모펀드 | FoF |
| FIN-17-035 | Secondary Investment | 세컨더리 투자 | secondaries |
| FIN-17-036 | LP-Led Secondary | LP 주도 세컨더리 | LP-led |
| FIN-17-037 | GP-Led Secondary | GP 주도 세컨더리 | GP-led |
| FIN-17-038 | Continuation Fund | 컨티뉴에이션 펀드 | continuation vehicle |
| FIN-17-039 | Stapled Secondary | 스테이플드 세컨더리 | stapled deal |
| FIN-17-040 | Subscription Credit Facility | 출자약정 담보대출 | sub line |
| FIN-17-041 | NAV Financing | NAV 담보금융 | NAV facility |
| FIN-17-042 | Portfolio Company | 포트폴리오 기업 | portco |
| FIN-17-043 | Platform Company | 플랫폼 기업 | platform |
| FIN-17-044 | Add-On Acquisition | 추가 인수 | add-on |
| FIN-17-045 | Bolt-On Acquisition | 볼트온 인수 | bolt-on |
| FIN-17-046 | Buy-and-Build Strategy | 연속 인수 성장전략 | buy and build |
| FIN-17-047 | Roll-Up Strategy | 롤업 전략 | roll-up |
| FIN-17-048 | Value Creation Plan | 가치창출계획 | VCP |
| FIN-17-049 | Operational Improvement | 운영개선 | operational alpha |
| FIN-17-050 | Exit | 투자회수 | exit |
| FIN-17-051 | Trade Sale | 전략적 매각 | strategic sale |
| FIN-17-052 | Secondary Buyout | 다른 PE에 매각 | SBO |
| FIN-17-053 | Dividend Recapitalization | 배당 재자본화 | dividend recap |
| FIN-17-054 | Multiple on Invested Capital | 투자원금배수 | MOIC |
| FIN-17-055 | Total Value to Paid-In | 총가치배수 | TVPI |
| FIN-17-056 | Distributions to Paid-In | 분배배수 | DPI |
| FIN-17-057 | Residual Value to Paid-In | 잔존가치배수 | RVPI |
| FIN-17-058 | Gross IRR | 총수익률 IRR | gross IRR |
| FIN-17-059 | Net IRR | 순수익률 IRR | net IRR |
| FIN-17-060 | J-Curve | J커브 | J-curve |
| FIN-17-061 | Direct Lending Strategy | 직접대출 | direct lending |
| FIN-17-062 | Senior Direct Lending | 선순위 직접대출 | senior DL |
| FIN-17-063 | Mezzanine Financing | 메자닌 금융 | mezz |
| FIN-17-064 | Special Situations Credit | 특수상황 크레딧 | special sits credit |
| FIN-17-065 | Distressed Debt Strategy | 부실채권 | distressed |
| FIN-17-066 | Venture Debt | 벤처대출 | venture debt |
| FIN-17-067 | Infrastructure Equity | 인프라 지분투자 | infra equity |
| FIN-17-068 | Core Real Estate | 코어 부동산 | core RE |
| FIN-17-069 | Core-Plus Real Estate | 코어플러스 부동산 | core+ |
| FIN-17-070 | Value-Add Real Estate | 밸류애드 부동산 | value-add |
| FIN-17-071 | Opportunistic Real Estate | 오퍼튜니스틱 부동산 | opportunistic |

---

## 18. 산업별 핵심 KPI

- Primary type: `METRIC`
- 기본 레퍼런스: [S03] [S05] [S19] [S28]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-18-001 | Net Interest Margin | 순이자마진 | NIM |
| FIN-18-002 | Net Interest Income | 순이자이익 | NII |
| FIN-18-003 | Non-Interest Income | 비이자이익 | non-NII |
| FIN-18-004 | Loan Growth | 대출성장률 | loan growth |
| FIN-18-005 | Deposit Growth | 예금성장률 | deposit growth |
| FIN-18-006 | Loan-to-Deposit Ratio | 예대율 | LDR |
| FIN-18-007 | Common Equity Tier 1 Ratio | 보통주자본비율 | CET1 ratio |
| FIN-18-008 | Total Capital Ratio | 총자본비율 | total capital |
| FIN-18-009 | Leverage Ratio | 레버리지비율 | bank leverage ratio |
| FIN-18-010 | Liquidity Coverage Ratio | 유동성커버리지비율 | LCR |
| FIN-18-011 | Net Stable Funding Ratio | 순안정자금조달비율 | NSFR |
| FIN-18-012 | Non-Performing Loan Ratio | 부실채권비율 | NPL ratio |
| FIN-18-013 | Delinquency Ratio | 연체율 | delinquency |
| FIN-18-014 | Provision Coverage Ratio | 충당금커버리지비율 | coverage ratio |
| FIN-18-015 | Credit Cost | 대손비용률 | credit cost |
| FIN-18-016 | Cost-to-Income Ratio | 영업효율성비율 | CIR |
| FIN-18-017 | Deposit Beta | 예금금리 민감도 | deposit beta |
| FIN-18-018 | Current Account Savings Account Ratio | 저원가성예금 비중 | CASA ratio |
| FIN-18-019 | Gross Written Premium | 총수입보험료 | GWP |
| FIN-18-020 | Net Written Premium | 순수입보험료 | NWP |
| FIN-18-021 | Earned Premium | 경과보험료 | earned premium |
| FIN-18-022 | Loss Ratio | 손해율 | loss ratio |
| FIN-18-023 | Expense Ratio | 사업비율 | expense ratio |
| FIN-18-024 | Combined Ratio | 합산비율 | combined ratio |
| FIN-18-025 | Persistency Ratio | 계약유지율 | persistency |
| FIN-18-026 | New Business Value | 신계약가치 | VNB / NBV |
| FIN-18-027 | Embedded Value | 내재가치 | EV in insurance |
| FIN-18-028 | Contractual Service Margin | 계약서비스마진 | CSM |
| FIN-18-029 | New Business CSM | 신계약 CSM | NB CSM |
| FIN-18-030 | Risk-Based Capital Ratio | 위험기준자본비율 | RBC ratio |
| FIN-18-031 | Korean Insurance Capital Standard Ratio | K-ICS 비율 | K-ICS |
| FIN-18-032 | Net Operating Income | 순영업소득 | NOI |
| FIN-18-033 | Capitalization Rate | 자본환원율 | cap rate |
| FIN-18-034 | Occupancy Rate | 임대율 | occupancy |
| FIN-18-035 | Weighted Average Lease Expiry | 가중평균 잔여임대기간 | WALE |
| FIN-18-036 | Loan-to-Value Ratio | 담보인정비율 | LTV |
| FIN-18-037 | Debt Yield | 부채수익률 | debt yield |
| FIN-18-038 | Same-Store NOI Growth | 동일자산 NOI 성장률 | same-store NOI |
| FIN-18-039 | Rent Spread | 임대료 갱신 스프레드 | rent spread |
| FIN-18-040 | Average Daily Rate | 평균객실단가 | ADR |
| FIN-18-041 | Revenue per Available Room | 가용객실당매출 | RevPAR |
| FIN-18-042 | Net Revenue Retention | 순매출유지율 | NRR |
| FIN-18-043 | Gross Revenue Retention | 총매출유지율 | GRR |
| FIN-18-044 | Logo Churn | 고객수 기준 이탈률 | logo churn |
| FIN-18-045 | Revenue Churn | 매출 기준 이탈률 | revenue churn |
| FIN-18-046 | Customer Acquisition Cost | 고객획득비용 | CAC |
| FIN-18-047 | Lifetime Value | 고객생애가치 | LTV |
| FIN-18-048 | CAC Payback Period | CAC 회수기간 | CAC payback |
| FIN-18-049 | LTV-to-CAC Ratio | LTV/CAC 비율 | LTV/CAC |
| FIN-18-050 | Rule of 40 | 룰오브40 | Rule of 40 |
| FIN-18-051 | Remaining Performance Obligations | 잔여수행의무 | RPO |
| FIN-18-052 | Digital Platform Average Revenue per User | 사용자당 평균매출 | ARPU |
| FIN-18-053 | SaaS Average Revenue per Paying User | 유료사용자당 평균매출 | ARPPU |
| FIN-18-054 | Daily Active Users | 일간활성이용자 | DAU |
| FIN-18-055 | Digital Platform Monthly Active Users | 월간활성이용자 | MAU |
| FIN-18-056 | DAU-to-MAU Ratio | 이용자 몰입도 | stickiness |
| FIN-18-057 | Take Rate | 수수료율 | take rate |
| FIN-18-058 | Conversion Rate | 전환율 | conversion |
| FIN-18-059 | Average Order Value | 평균주문금액 | AOV |
| FIN-18-060 | Same-Store Sales | 기존점 성장률 | SSS |
| FIN-18-061 | Customer Traffic | 고객수 / 트래픽 | traffic |
| FIN-18-062 | Units per Transaction | 거래당 구매수량 | UPT |
| FIN-18-063 | Sell-Through Rate | 판매소진율 | sell-through |
| FIN-18-064 | Inventory Shrinkage | 재고손실률 | shrink |
| FIN-18-065 | Wafer Starts | 웨이퍼 투입량 | WSPM |
| FIN-18-066 | Wafer Capacity | 웨이퍼 생산능력 | wafer capacity |
| FIN-18-067 | Manufacturing Capacity Utilization | 설비가동률 | utilization |
| FIN-18-068 | Yield Rate | 수율 | yield |
| FIN-18-069 | Bit Shipment Growth | 비트 출하증가율 | bit growth |
| FIN-18-070 | Semiconductor Average Selling Price | 평균판매가격 | ASP |
| FIN-18-071 | Node Mix | 공정노드 믹스 | node mix |
| FIN-18-072 | High Bandwidth Memory Mix | HBM 비중 | HBM mix |
| FIN-18-073 | Foundry Market Share | 파운드리 점유율 | foundry share |
| FIN-18-074 | Semiconductor Capital Expenditure Intensity | 설비투자집약도 | capex/sales |
| FIN-18-075 | Telecom Average Revenue per User | 가입자당평균매출 | telecom ARPU |
| FIN-18-076 | Subscriber Churn | 가입자해지율 | churn |
| FIN-18-077 | Net Adds | 순증가입자 | net additions |
| FIN-18-078 | Postpaid Mix | 후불가입자 비중 | postpaid mix |
| FIN-18-079 | Data Usage per Subscriber | 가입자당 데이터 사용량 | data usage |
| FIN-18-080 | Telecom Capital Expenditure Intensity | CAPEX 집약도 | capex intensity |
| FIN-18-081 | Average Seat Kilometers | 공급좌석킬로미터 | ASK |
| FIN-18-082 | Available Seat Miles | 공급좌석마일 | ASM |
| FIN-18-083 | Revenue Passenger Kilometers | 유상여객킬로미터 | RPK |
| FIN-18-084 | Revenue Passenger Miles | 유상여객마일 | RPM |
| FIN-18-085 | Passenger Load Factor | 탑승률 | load factor |
| FIN-18-086 | Passenger Yield | 여객단위수익 | yield |
| FIN-18-087 | Revenue per Available Seat Kilometer | 가용좌석킬로미터당 매출 | RASK |
| FIN-18-088 | Cost per Available Seat Kilometer | 가용좌석킬로미터당 비용 | CASK |
| FIN-18-089 | CASK Ex-Fuel | 연료비 제외 CASK | ex-fuel CASK |
| FIN-18-090 | Oil and Gas Production | 석유가스 생산량 | production |
| FIN-18-091 | Proved Reserves | 확인매장량 | 1P reserves |
| FIN-18-092 | Reserve Replacement Ratio | 매장량대체율 | RRR |
| FIN-18-093 | Lifting Cost | 생산원가 | lifting cost |
| FIN-18-094 | Realized Price | 실현판매가격 | realized price |
| FIN-18-095 | Refining Margin | 정제마진 | refining margin |
| FIN-18-096 | Crack Spread | 크랙스프레드 | crack |
| FIN-18-097 | Refinery Utilization | 정유설비가동률 | refinery utilization |
| FIN-18-098 | Pipeline Throughput | 파이프라인 처리량 | throughput |
| FIN-18-099 | Time Charter Equivalent | 일일용선환산수익 | TCE |
| FIN-18-100 | Fleet Size | 선대규모 | fleet |
| FIN-18-101 | Fleet Utilization | 선대가동률 | fleet utilization |
| FIN-18-102 | Orderbook-to-Fleet Ratio | 발주잔고/선대 비율 | orderbook/fleet |
| FIN-18-103 | Freight Rate | 운임 | freight |
| FIN-18-104 | Unit Sales | 판매대수 | unit sales |
| FIN-18-105 | Vehicle Average Selling Price | 차량 평균판매가격 | vehicle ASP |
| FIN-18-106 | Incentive per Vehicle | 대당 인센티브 | incentive |
| FIN-18-107 | Dealer Inventory Days | 딜러재고일수 | inventory days |
| FIN-18-108 | Seasonally Adjusted Annual Rate | 미국 자동차 연환산판매 | SAAR |
| FIN-18-109 | Battery Electric Vehicle Mix | 전기차 비중 | BEV mix |
| FIN-18-110 | Order Intake | 신규수주 | order intake |
| FIN-18-111 | Order Backlog | 수주잔고 | backlog |
| FIN-18-112 | Service Revenue Mix | 서비스 매출 비중 | service mix |
| FIN-18-113 | Aftermarket Revenue | 애프터마켓 매출 | aftermarket |
| FIN-18-114 | Pipeline Asset | 임상 파이프라인 자산 | pipeline |
| FIN-18-115 | Clinical Phase | 임상단계 | Phase I/II/III |
| FIN-18-116 | Primary Endpoint | 1차 평가변수 | primary endpoint |
| FIN-18-117 | Secondary Endpoint | 2차 평가변수 | secondary endpoint |
| FIN-18-118 | Overall Response Rate | 객관적반응률 | ORR |
| FIN-18-119 | Progression-Free Survival | 무진행생존기간 | PFS |
| FIN-18-120 | Overall Survival | 전체생존기간 | OS |
| FIN-18-121 | Hazard Ratio | 위험비 | HR |
| FIN-18-122 | Patent Expiry | 특허만료 | LOE |
| FIN-18-123 | Peak Sales | 최대연매출 | peak sales |
| FIN-18-124 | Probability of Technical and Regulatory Success | 기술·허가 성공확률 | PTRS |
| FIN-18-125 | Research and Development Pipeline Value | 파이프라인 가치 | pipeline NPV |
| FIN-18-126 | Game Bookings | 게임 예약매출 | bookings |
| FIN-18-127 | Gaming Monthly Active Users | 월간활성이용자 | MAU |
| FIN-18-128 | Paying User Ratio | 결제이용자 비율 | payer conversion |
| FIN-18-129 | Gaming Average Revenue per Paying User | 결제유저당 매출 | ARPPU |
| FIN-18-130 | Engagement Hours | 이용시간 | engagement |
| FIN-18-131 | Content Spend | 콘텐츠 투자비 | content spend |
| FIN-18-132 | Subscriber Net Adds | 가입자 순증 | net adds |

---

## 19. 규제·공시·지배구조

- Primary type: `REGULATION / DISCLOSURE / EVENT`
- 기본 레퍼런스: [S08] [S09] [S19] [S25] [S26] [S27]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-19-001 | Capital Markets Regulation | 자본시장 규제 | securities law |
| FIN-19-002 | Financial Investment Services and Capital Markets Act | 자본시장과 금융투자업에 관한 법률 | FSCMA / 자본시장법 |
| FIN-19-003 | Securities Act | 증권 발행 규제법 | US Securities Act |
| FIN-19-004 | Securities Exchange Act | 증권거래 규제법 | US Exchange Act |
| FIN-19-005 | Listing Rules | 상장규정 | listing requirements |
| FIN-19-006 | Disclosure Regulation | 공시규정 | disclosure rules |
| FIN-19-007 | Market Abuse Regulation | 시장남용 규제 | MAR |
| FIN-19-008 | Insider Trading | 내부자거래 | insider dealing |
| FIN-19-009 | Material Nonpublic Information | 중요 미공개정보 | MNPI |
| FIN-19-010 | Market Manipulation | 시세조종 | manipulation |
| FIN-19-011 | Front Running | 선행매매 | front-running |
| FIN-19-012 | Churning | 과당매매 | churning |
| FIN-19-013 | Suitability | 적합성 원칙 | suitability |
| FIN-19-014 | Fiduciary Duty | 수탁자 의무 | fiduciary obligation |
| FIN-19-015 | Best Interest Duty | 최선이익 의무 | best interest |
| FIN-19-016 | Chinese Wall | 정보교류차단장치 | information barrier |
| FIN-19-017 | Restricted List | 거래제한 목록 | restricted list |
| FIN-19-018 | Watch List | 감시목록 | watch list |
| FIN-19-019 | Personal Account Dealing | 임직원 자기계좌거래 | PAD |
| FIN-19-020 | Anti-Money Laundering Framework | 자금세탁방지 | AML |
| FIN-19-021 | Customer Due Diligence | 고객확인·고객실사 | CDD |
| FIN-19-022 | Enhanced Due Diligence | 강화된 고객확인 | EDD |
| FIN-19-023 | Sanctions Screening | 제재대상 점검 | sanctions |
| FIN-19-024 | Beneficial Ownership | 실소유자 | UBO / beneficial owner |
| FIN-19-025 | Annual Report | 연차보고서 | annual filing |
| FIN-19-026 | Quarterly Report | 분기보고서 | quarterly filing |
| FIN-19-027 | Half-Year Report | 반기보고서 | semiannual report |
| FIN-19-028 | Business Report | 사업보고서 | KR annual business report |
| FIN-19-029 | Material Event Report | 주요사항보고서 | material disclosure |
| FIN-19-030 | Audit Report | 감사보고서 | auditor's report |
| FIN-19-031 | Registration Statement | 증권등록신고서 / 미국 등록신고서 | registration filing |
| FIN-19-032 | Securities Registration Statement | 증권신고서 | KR registration statement |
| FIN-19-033 | Prospectus | 투자설명서 | prospectus |
| FIN-19-034 | Preliminary Prospectus | 예비투자설명서 | red herring |
| FIN-19-035 | Earnings Release | 실적발표자료 | earnings announcement |
| FIN-19-036 | Public Investor Relations Presentation | IR 프레젠테이션 | IR deck |
| FIN-19-037 | Earnings Call Transcript | 실적발표 컨퍼런스콜 기록 | transcript |
| FIN-19-038 | Proxy Statement | 위임장 설명서 | proxy filing |
| FIN-19-039 | Beneficial Ownership Report | 대량보유보고 | Schedule 13D/13G concept |
| FIN-19-040 | Institutional Holdings Report | 기관보유내역 보고 | Form 13F concept |
| FIN-19-041 | Insider Transaction Report | 임원·주요주주 거래보고 | Form 4 concept |
| FIN-19-042 | Public Disclosure | 공정공시 / 공개공시 | public disclosure |
| FIN-19-043 | Selective Disclosure | 선택적 공시 | selective disclosure |
| FIN-19-044 | Continuous Disclosure | 수시공시 | continuous disclosure |
| FIN-19-045 | Periodic Disclosure | 정기공시 | periodic disclosure |
| FIN-19-046 | Corporate Governance Code | 기업지배구조 모범규준 | governance code |
| FIN-19-047 | Board of Directors | 이사회 | board |
| FIN-19-048 | Independent Director | 사외이사 | independent director |
| FIN-19-049 | Audit Committee | 감사위원회 | audit committee |
| FIN-19-050 | Remuneration Committee | 보상위원회 | compensation committee |
| FIN-19-051 | Nomination Committee | 후보추천위원회 | nomination committee |
| FIN-19-052 | Shareholder Meeting | 주주총회 | AGM / EGM |
| FIN-19-053 | Voting Right | 의결권 | vote |
| FIN-19-054 | Cumulative Voting | 집중투표 | cumulative voting |
| FIN-19-055 | Proxy Voting Activity | 의결권 대리행사 | proxy vote |
| FIN-19-056 | Shareholder Proposal | 주주제안 | shareholder resolution |
| FIN-19-057 | Stewardship Code | 스튜어드십 코드 | stewardship principles |
| FIN-19-058 | Related-Party Transaction Regulation | 특수관계자 거래 규제 | RPT rules |
| FIN-19-059 | Tender Offer Rule | 공개매수 규정 | tender regulation |
| FIN-19-060 | Short-Sale Regulation | 공매도 규제 | short-sale rules |
| FIN-19-061 | Large Shareholding Disclosure | 대량보유 공시 | 5% rule concept |
| FIN-19-062 | Lock-Up Requirement | 보호예수·의무보유확약 | lock-up |
| FIN-19-063 | Trading Halt | 매매거래정지 | halt |
| FIN-19-064 | Price Limit | 가격제한폭 | price band |
| FIN-19-065 | Investment Warning Designation | 투자경고 지정 | market alert |
| FIN-19-066 | Basel III | 바젤 III | Basel framework |
| FIN-19-067 | Common Equity Tier 1 | 보통주자본 | CET1 capital |
| FIN-19-068 | Global Investment Performance Standards | 글로벌투자성과기준 | GIPS |

---

## 20. 금융 데이터·기술·식별자

- Primary type: `DATA_SOURCE / IDENTIFIER / TOOL_SKILL`
- 기본 레퍼런스: [S01] [S02] [S12] [S16] [S25] [S27]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-20-001 | Market Data | 시장데이터 | price/quote data |
| FIN-20-002 | Reference Data | 기준정보 | reference data |
| FIN-20-003 | Fundamental Data | 기업 재무데이터 | fundamentals |
| FIN-20-004 | Consensus Estimates | 컨센서스 추정치 | estimates data |
| FIN-20-005 | Alternative Data | 대체데이터 | alt data |
| FIN-20-006 | Corporate Actions Data | 기업행사 데이터 | corporate actions |
| FIN-20-007 | Point-in-Time Data | 시점보존 데이터 | PIT data |
| FIN-20-008 | As-Reported Data | 공시원문 기준 데이터 | as reported |
| FIN-20-009 | Standardized Financial Data | 표준화 재무데이터 | standardized fundamentals |
| FIN-20-010 | Restated Data | 재작성 반영 데이터 | restated |
| FIN-20-011 | Real-Time Data | 실시간 데이터 | real time |
| FIN-20-012 | Delayed Data | 지연 데이터 | delayed |
| FIN-20-013 | End-of-Day Data | 일말 데이터 | EOD data |
| FIN-20-014 | Tick Data | 틱데이터 | tick |
| FIN-20-015 | Order Book Data | 호가장 데이터 | LOB data |
| FIN-20-016 | Transaction Data | 체결데이터 | trades |
| FIN-20-017 | News Feed | 뉴스피드 | newswire |
| FIN-20-018 | Earnings Transcript Data | 실적콜 데이터 | transcripts |
| FIN-20-019 | Regulatory Filing Data | 공시데이터 | filings |
| FIN-20-020 | Web-Scraped Data | 웹수집 데이터 | scraped data |
| FIN-20-021 | Satellite Data | 위성데이터 | satellite imagery |
| FIN-20-022 | Credit Card Data | 카드결제 데이터 | consumer transaction data |
| FIN-20-023 | Web Traffic Data | 웹트래픽 데이터 | traffic data |
| FIN-20-024 | App Usage Data | 앱사용 데이터 | mobile app data |
| FIN-20-025 | Natural Language Processing | 자연어처리 | NLP |
| FIN-20-026 | Named Entity Recognition | 개체명 인식 | NER |
| FIN-20-027 | Entity Resolution | 동일개체 식별 | entity matching |
| FIN-20-028 | Relation Extraction | 관계 추출 | RE |
| FIN-20-029 | Document Classification | 문서분류 | doc classification |
| FIN-20-030 | Information Extraction | 정보추출 | IE |
| FIN-20-031 | Optical Character Recognition | 광학문자인식 | OCR |
| FIN-20-032 | Retrieval-Augmented Generation | 검색증강생성 | RAG |
| FIN-20-033 | Vector Database | 벡터DB | vector store |
| FIN-20-034 | Embedding | 임베딩 | vector representation |
| FIN-20-035 | Knowledge Graph | 지식그래프 | KG |
| FIN-20-036 | Ontology | 온톨로지 | formal vocabulary |
| FIN-20-037 | Taxonomy | 분류체계 | taxonomy |
| FIN-20-038 | Data Dictionary | 데이터사전 | data dictionary |
| FIN-20-039 | Data Lineage | 데이터 계보 | lineage |
| FIN-20-040 | Data Provenance | 데이터 출처추적 | provenance |
| FIN-20-041 | Data Quality | 데이터 품질 | DQ |
| FIN-20-042 | Schema Matching | 스키마 매칭 | schema alignment |
| FIN-20-043 | Master Data Management | 마스터데이터관리 | MDM |
| FIN-20-044 | Extract Transform Load | 추출·변환·적재 | ETL |
| FIN-20-045 | Extract Load Transform | 추출·적재·변환 | ELT |
| FIN-20-046 | Application Programming Interface | 응용프로그램 인터페이스 | API |
| FIN-20-047 | XBRL | eXtensible Business Reporting Language | XBRL |
| FIN-20-048 | Inline XBRL | 인라인 XBRL | iXBRL |
| FIN-20-049 | DART Corporate Code | DART 고유번호 | corp_code |
| FIN-20-050 | Legal Entity Identifier | 법인식별기호 | LEI |
| FIN-20-051 | International Securities Identification Number | 국제증권식별번호 | ISIN |
| FIN-20-052 | Committee on Uniform Securities Identification Procedures Number | 미국 증권식별번호 | CUSIP |
| FIN-20-053 | Stock Exchange Daily Official List Code | 국제 증권식별코드 | SEDOL |
| FIN-20-054 | Ticker Symbol | 종목코드 / 티커 | ticker |
| FIN-20-055 | FIGI | 금융상품 글로벌식별자 | Financial Instrument Global Identifier |
| FIN-20-056 | Bloomberg Terminal | 블룸버그 터미널 | Bloomberg |
| FIN-20-057 | FactSet | 팩트셋 | FactSet workstation |
| FIN-20-058 | S&P Capital IQ | 캐피털아이큐 | CapIQ |
| FIN-20-059 | LSEG Workspace | LSEG 워크스페이스 | Refinitiv Workspace |
| FIN-20-060 | EDGAR | 미국 SEC 공시시스템 | EDGAR |
| FIN-20-061 | DART | 전자공시시스템 | DART |
| FIN-20-062 | OpenDART API | 오픈다트 API | OpenDART |
| FIN-20-063 | KRX Data System | 한국거래소 데이터시스템 | KRX data |
| FIN-20-064 | SQL | 구조화 질의어 | SQL |
| FIN-20-065 | Python | 파이썬 | Python |
| FIN-20-066 | R | R 통계언어 | R |
| FIN-20-067 | Excel Financial Modeling | 엑셀 재무모델링 | Excel modeling |
| FIN-20-068 | Version Control | 버전관리 | Git |
| FIN-20-069 | Look-Ahead Bias | 미래정보 편향 | look-ahead |
| FIN-20-070 | Survivorship Bias | 생존편향 | survivorship |
| FIN-20-071 | Selection Bias | 선택편향 | selection bias |
| FIN-20-072 | Backfill Bias | 백필편향 | backfill |
| FIN-20-073 | Data Snooping | 데이터 스누핑 | multiple testing |
| FIN-20-074 | Corporate Action Adjustment | 기업행사 조정 | adjustment |
| FIN-20-075 | Split-Adjusted Price | 액면분할 조정가격 | split adjusted |
| FIN-20-076 | Total Return Adjustment | 배당포함 조정 | total return adjusted |

---

## 21. 업무 산출물·문서

- Primary type: `ARTIFACT / DISCLOSURE`
- 기본 레퍼런스: [S07] [S10] [S14] [S18] [S22] [S25]

| ID | Canonical English | 한국어·국내 실무표현 | 약어·별칭 |
|---|---|---|---|
| FIN-21-001 | Pitch Book | 피치북 / 고객 제안서 | pitch deck |
| FIN-21-002 | Teaser | 티저 | one-page teaser |
| FIN-21-003 | Confidential Information Memorandum | 비밀투자설명서 | CIM |
| FIN-21-004 | Information Memorandum | 투자설명자료 | IM |
| FIN-21-005 | Offering Memorandum | 오퍼링 메모랜덤 | OM |
| FIN-21-006 | Private Placement Memorandum | 사모투자제안서 | PPM |
| FIN-21-007 | Management Presentation | 경영진 프레젠테이션 | MP |
| FIN-21-008 | Process Letter | 거래절차 안내문 | process letter |
| FIN-21-009 | Buyer List | 잠재매수자 목록 | buyer universe |
| FIN-21-010 | Investor List | 잠재투자자 목록 | investor target list |
| FIN-21-011 | Valuation Deck | 가치평가 자료 | valuation presentation |
| FIN-21-012 | Valuation Model | 가치평가 모델 | valuation spreadsheet |
| FIN-21-013 | DCF Model | DCF 모델 | DCF workbook |
| FIN-21-014 | Comparable Companies Table | 유사기업 비교표 | comps table |
| FIN-21-015 | Precedent Transactions Table | 유사거래 비교표 | precedents table |
| FIN-21-016 | Football Field Chart | 풋볼필드 차트 | valuation range chart |
| FIN-21-017 | Sources and Uses Table | 자금조달·사용표 | sources & uses |
| FIN-21-018 | Merger Model Workbook | 합병모델 | merger workbook |
| FIN-21-019 | LBO Model Workbook | LBO 모델 | LBO workbook |
| FIN-21-020 | Fairness Opinion | 거래가격 공정성 의견 | fairness opinion |
| FIN-21-021 | Board Presentation | 이사회 보고자료 | board deck |
| FIN-21-022 | Investment Committee Memo | 투자위원회 메모 | IC memo |
| FIN-21-023 | Investment Memo | 투자검토보고서 | investment memorandum |
| FIN-21-024 | Credit Memo | 신용검토보고서 | credit memorandum |
| FIN-21-025 | Underwriting Memo | 인수심사 메모 | underwriting memorandum |
| FIN-21-026 | Due Diligence Report | 실사보고서 | DD report |
| FIN-21-027 | Red Flag Report | 핵심위험 보고서 | red flag report |
| FIN-21-028 | Quality of Earnings Report | 이익의 질 보고서 | QoE report |
| FIN-21-029 | Term Sheet | 주요조건서 | term sheet |
| FIN-21-030 | Letter of Intent | 인수의향서 | LOI |
| FIN-21-031 | Non-Binding Offer Letter | 비구속적 제안서 | NBO letter |
| FIN-21-032 | Binding Offer Letter | 구속적 제안서 | final offer |
| FIN-21-033 | Sale and Purchase Agreement | 주식·자산매매계약서 | SPA |
| FIN-21-034 | Shareholders Agreement | 주주간계약서 | SHA |
| FIN-21-035 | Asset Purchase Agreement | 자산양수도계약서 | APA |
| FIN-21-036 | Merger Agreement | 합병계약서 | merger agreement |
| FIN-21-037 | Engagement Letter | 자문계약서 | engagement letter |
| FIN-21-038 | Commitment Letter | 금융확약서 | commitment letter |
| FIN-21-039 | Confidentiality Agreement | 비밀유지계약서 | NDA |
| FIN-21-040 | Roadshow Deck | 로드쇼 자료 | roadshow presentation |
| FIN-21-041 | Deal Investor Presentation | 투자자 프레젠테이션 | investor deck |
| FIN-21-042 | Rating Presentation | 신용평가 프레젠테이션 | rating deck |
| FIN-21-043 | Research Report | 리서치 보고서 | research note |
| FIN-21-044 | Initiation Report | 분석개시 보고서 | initiation |
| FIN-21-045 | Earnings Preview Report | 실적 프리뷰 보고서 | preview note |
| FIN-21-046 | Earnings Review Report | 실적 리뷰 보고서 | post-earnings note |
| FIN-21-047 | Industry Report | 산업 보고서 | sector report |
| FIN-21-048 | Strategy Report | 투자전략 보고서 | strategy note |
| FIN-21-049 | Morning Meeting Note | 모닝미팅 자료 | morning note |
| FIN-21-050 | Company Model | 기업 실적모델 | company model |
| FIN-21-051 | Estimate Sheet | 추정치표 | estimate sheet |
| FIN-21-052 | Watchlist | 관찰목록 | watch list |
| FIN-21-053 | Portfolio Report | 포트폴리오 보고서 | portfolio report |
| FIN-21-054 | Risk Report | 리스크 보고서 | risk report |
| FIN-21-055 | Performance Report | 성과보고서 | performance report |
| FIN-21-056 | Attribution Report | 성과요인 보고서 | attribution report |
| FIN-21-057 | Fund Factsheet | 펀드 팩트시트 | factsheet |
| FIN-21-058 | Client Report | 고객보고서 | client report |
| FIN-21-059 | Fund Prospectus | 펀드 투자설명서 | fund prospectus |
| FIN-21-060 | Key Investor Information Document | 핵심투자자정보문서 | KIID / KID |
| FIN-21-061 | Compliance Checklist | 준법 체크리스트 | compliance checklist |
| FIN-21-062 | Trade Blotter | 거래원장 | blotter |
| FIN-21-063 | Position Report | 포지션 보고서 | position report |
| FIN-21-064 | Cash Report | 현금현황표 | cash report |
| FIN-21-065 | NAV Pack | NAV 산출 패키지 | NAV pack |
| FIN-21-066 | Reconciliation Report | 대사보고서 | recon report |

---

## 22. 구축 우선순위 제안


### Tier A: 첫 300~500 concepts

- 기관·부서·직무: 01~03의 핵심
- 전략: 05의 fundamental, long/short, quant, event-driven, passive
- IB: 06~09 핵심
- 기업리서치·회계·가치평가: 10~12 핵심
- 포트폴리오·리스크: 13 핵심
- 산출물: 21 핵심

### Tier B: 직무별 확장

- S&T·오퍼레이션: 14~16
- 대체투자: 17
- 산업 KPI: 18
- 규제·공시·데이터: 19~20

### Tier C: 회사·국가·상품 특화

- 개별 증권사 조직명
- 국내 법정 용어와 미국·EU 대응 개념
- 산업·기업별 custom KPI
- 구조화상품 payoff·계약조항

## 23. 레퍼런스 활용 주의

- 공식 용어집의 정의를 장문으로 복사하지 말고 자체 요약과 출처 메타데이터를 저장한다.
- IFRS 자료는 이용 범위와 라이선스를 별도로 확인한다.
- MSCI, Preqin 등 상업 데이터 제공사의 분류는 용어 후보와 업계 관행 확인에 활용하고, 제품 DB에 원문을 복제하지 않는다.
- 법적·규제 용어는 반드시 해당 관할의 현행 원문으로 재검증한다.
- 직무명은 회사마다 다르므로 `Role`과 `Org Unit`을 분리한다.
