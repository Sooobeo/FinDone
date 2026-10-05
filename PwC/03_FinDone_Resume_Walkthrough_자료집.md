# FinDone 실무면접 Resume Walkthrough 자료집

작성·확인일: 2026-09-15  
대상 경험: Finance Learning App and Quiz Option Ranking Model, 2026년 7~8월  
대상 면접: PwC Risk & Cyber Platform 기업 시스템 기반 리스크 데이터 분석·설계 인턴 실무면접

이 자료집은 제출 이력서의 FinDone 네 문장을 이해하고 실제 근거로 설명하기 위한 교재다. 범위는 FinDone 한 경험이며, 질문은 준비용 예상 질문이다. PwC의 실제 면접 질문이나 평가표를 확보한 것은 아니다.

기준 실험은 `cmq-v2-20260816-014214-89cf4e66`이다. 현재 저장소의 코드·데이터와 이 실험의 저장 결과를 대조한다. v3 실험과 540문항 preview는 별도 산출물이며 405문항 경험과 섞지 않는다. 개인 동기·직접 작성 범위·AI 지원 범위는 코드만으로 확정할 수 없어 [본인 확인 항목](#personal)을 남겼다.

## 읽는 순서

- [0. 경험 한눈에 보기](#overview)
- [1. 이력서 주장과 근거 지도](#claims)
- [2. Bullet 1: 앱·데이터·개념 검색](#b1)
- [3. Bullet 2: 오답 후보·18개 특성·랭킹](#b2)
- [4. Bullet 3: 분할·실험·결과 해석](#b3)
- [5. Bullet 4: 문제은행·검사·재승인](#b4)
- [6. 본인의 판단과 문제 해결](#decisions)
- [7. PwC 업무와 연결하기](#pwc)
- [8. Walkthrough 답변과 복습](#practice)
- [부록 A. 주장별 근거표와 자료 목록](#evidence)
- [부록 B. 재현 기록과 실행 방법](#reproduction)
- [부록 C. 미확인 사항·공식 문서](#personal)

P0는 반드시 설명할 핵심, P1은 중요한 꼬리질문, P2는 추가 심화다. 준비 기한이나 출제 확률을 뜻하지 않는다. 처음에는 0~5장을 읽고, 다음에는 표와 실제 사례를 직접 설명한 뒤 8장의 답변으로 연습한다.

**근거 표시:** `이력서 기재`는 제출 문장의 주장, `원자료 확인`은 코드·데이터·기록을 읽어 확인한 범위, `재현 확인`은 이번에 다시 계산·조회한 범위다. `본인 설명`은 당사자 진술, `미확인`은 근거가 더 필요한 부분, `추가 학습·실습`은 면접 준비 과정에서 새로 만든 설명·실습이다. 아래 구어체 답변은 확인된 시스템과 이력서에 맞춘 연습 문안이며 직접 기여를 대신 증명하지 않는다.

<a id="overview"></a>
## 0. 경험 한눈에 보기

### 학습 목표 · P0

‘어떤 앱인가’와 ‘모델이 무엇을 하는가’를 구분하고 전체 입력·처리·출력을 설명한다.

### 필요한 개념

**콘텐츠**는 앱이 보여 줄 개념 설명과 문제다. **콘텐츠 제작 파이프라인**은 원문을 읽고 가공해 문제를 만들고 검토하는 과정이다. **추론**은 학습이 끝난 모델로 새 입력의 점수를 계산하는 일이다. 모델을 사용해 콘텐츠를 미리 만든 뒤 앱에 넣는 방식에서는 앱 사용 시마다 모델을 실행할 필요가 없다.

### 나의 실제 적용

| 항목 | 설명 | 근거 |
|---|---|---|
| 프로젝트 | 개인 Android 금융 학습 앱과 콘텐츠 관리 웹 | 이력서 기재, S01 |
| 역할 | 독립 프로젝트의 앱·모델 개발과 콘텐츠 검증 | 이력서 기재. 세부 직접 기여는 본인 확인 |
| 입력 | 135개 개념의 이름·정의·직관·핵심 관계·출처와 메타데이터 | S03·S04 |
| 처리 | 문제 유형별 사실 구성, 후보 필터링·검색·순위화, 검사·승인 | S04·S05 |
| 출력 | 개념형 5지선다 405문항과 관련 콘텐츠 | S06 |
| 앱 사용 | 개념 검색, 퀴즈·복습 기록에 연결 | S01·S08; 실제 사용자 효과는 미확인 |

```text
콘텐츠 제작
개념·출처 → 문제·정답 구성 → 다른 개념 후보 선별 → 순위화
          → 5개 선택지 조합 → 자동 검사·Owner 검토 → 문제은행 → 앱 DB

앱 사용
사용자 검색어 → SQLite FTS5/BM25 → 개념 카드
사용자 문제 풀이 → 저장된 문항 표시 → 풀이·복습 기록
```

검색과 모델 학습은 두 개의 다른 경로다. 앱에서 개념을 찾는 BM25 검색과 Python에서 오답 후보를 고르는 TF-IDF·임베딩·RRF·XGBoost 경로를 하나의 연속 단계로 말하면 실제 구현과 달라진다. [S04·S08·S09]

### 판단·검증

모델링 보고서는 `appRuntimeModelCalls=0`을 기록한다. 모델은 콘텐츠 제작 시 후보의 순서를 정한다. 이것은 사용자 학습 성과를 예측하는 모델도, 질문을 풀어 정답을 알아내는 모델도 아니다. 실제 배포 횟수·사용자 수·학습 효과는 현재 근거로 확인하지 않았다. [S07]

### 확인 문제

**Q. 사용자가 앱에서 ‘ROE’를 검색하면 XGBoost가 검색 순서를 정하나요?**  
**A.** 확인한 개념 검색 코드는 SQLite FTS5/BM25를 사용한다. XGBoost는 콘텐츠 제작 단계의 오답 후보 순위화에 쓰인다. [F02·F10]

<a id="claims"></a>
## 1. 이력서 주장과 근거 지도

### 학습 목표 · P0

숫자를 단순 암기하지 않고 ‘무엇을 센 수인가’를 설명한다.

### 필요한 개념

**개념 수**, **문항 수**, **후보 행 수**, **모델 입력 열 수**, **실험 구성 수**는 서로 다른 단위다. 한 개념에서 여러 문항이 생기고, 한 문항에 여러 후보 행이 붙는다. 후보 행이 많아도 독립적인 개념이 그만큼 많아진 것은 아니다.

### 나의 실제 적용

| 이력서 단위 | 정확한 의미 | 연결 장·검증 |
|---|---|---|
| B1: 135 | 고유 금융 개념. 모델 입력 카탈로그와 앱 DB의 개념 수를 구분해 대조 | 2장, F01·F02 |
| B2: 18 | 후보 한 건을 표현하는 숫자 특성 열 수. 도메인 one-hot 7열 포함 | 3장, F03 |
| B2: 198 | TF-IDF·사전학습 임베딩, 검색 결합 프로필, 랭커 설정을 조합한 실행 수 | 3~4장, F06 |
| B3: 95/20/20 | train/validation/test의 대상 개념 수. 문항은 285/60/60 | 4장, F05 |
| B4: 405 | 개념당 정의·직관·관계형 3문항을 구성한 문제은행. 상태별로 다시 구분 | 5장, F01·F09 |

### 판단·검증

문제은행을 직접 집계하면 고유 `questionId` 405개, `automated_pass` 402개, `owner_approved` 3개다. 따라서 ‘405개 모두 사람이 개별 검토했다’는 표현은 이 집계로 뒷받침되지 않는다. 저장된 실험의 사람 관련성 라벨 수는 0이다. **콘텐츠 승인과 모델 평가용 사람 라벨은 다른 자료**다. [S06·S07·S10, 재현 R01]

### 확인 문제

**Q. test가 60문항이면 서로 독립적인 60개 금융 개념을 평가했나요?**  
**A.** 아니다. 20개 대상 개념에서 각 3문항이 파생된다. 문항끼리 같은 개념 정보를 공유하므로 결과의 불확실성을 설명할 때 개념 단위를 함께 고려해야 한다.

<a id="b1"></a>
## 2. Bullet 1: 앱·데이터·개념 검색

> Built a personal Android app and content management website linking explanations, formulas and sources for 135 finance concepts with quizzes and review records; implemented concept search with SQLite FTS5/BM25.

한국어 의미: 135개 금융 개념의 설명·공식·출처를 퀴즈·복습 기록과 연결한 개인 앱 및 관리 웹을 만들고, 개념 검색에 SQLite FTS5/BM25를 적용했다.

### 학습 목표 · P0

실제 데이터의 연결 키, 검색 흐름, 모델 입력으로 쓰이는 개념 문서를 설명한다.

### 필요한 개념

**기본키**는 행을 식별하는 값이다. FinDone의 `elementId`는 개념을 식별한다. **조인**은 공통 키로 테이블을 연결하는 연산이다. 같은 개념 ID를 통해 개념·공식 카드를 함께 가져오면 데이터를 여러 곳에 중복 저장하는 부담을 줄일 수 있다. 단, 실제 일대일 관계가 깨지면 조인 결과가 중복될 수 있으므로 키의 유일성과 결과 행 수를 확인해야 한다.

**FTS5**는 SQLite의 전문 검색 기능이다. `MATCH`로 검색식을 적용하고 `bm25()`로 검색 결과의 관련도를 정렬한다. SQLite FTS5의 BM25는 작은 값이 더 좋은 일치를 나타내도록 구현되어 있어 오름차순 정렬을 사용한다. [SQLite 공식 문서](https://www.sqlite.org/fts5.html#the_bm25_function)

### 나의 실제 적용

실제 개념 `ACC-01`의 이름은 ‘회계등식과 차변·대변’이다. 모델 카탈로그는 `elementId`, `domainId`, `title`, `mode`, `definition`, `intuition`, `coreRelation`, `sourceLabel`, `sourceLocator`를 읽는다. 필수 텍스트 누락·중복 ID·지원하지 않는 도메인은 오류로 처리한다. 입력은 도메인 및 개념 ID 순서로 정렬된다. [S03·S04: `load_elements`]

| 객체 | 실제 예 | 의미 |
|---|---|---|
| 개념 | `ACC-01` | 설명·직관·관계·출처를 가진 원 단위 |
| 사실 | `ACC-01:definition:01` | 개념에서 가져온 정의형 정답 설명 |
| 문제 | `ACC-01-term_to_definition-01` | 이 정의를 묻는 하나의 문제 |
| 후보 | 문제 ID + `INV-07` | 다른 개념의 설명을 오답으로 쓸 가능성 |
| 특성 행 | 위 문제와 후보의 18개 숫자 | 모델 입력 X의 한 행 |
| 관련성 라벨 | 0~3 | 해당 후보의 자동 기준 등급 y |
| 질의 그룹 | 동일 문제 ID의 후보들 | 서로 순위를 비교하는 범위 |

아래는 앱 검색 코드의 핵심 구조를 읽기 쉽게 줄인 것이다. 새로 설계한 쿼리가 아니라 `ContentRepository.searchElements`의 발췌·축약이다. [S08]

```sql
SELECT /* 개념·공식 카드에 필요한 열 */
FROM knowledge_fts
JOIN elements e ON e.element_id = knowledge_fts.element_id
JOIN concept_cards c ON c.element_id = e.element_id
JOIN formula_cards f ON f.element_id = e.element_id
WHERE knowledge_fts MATCH ?
ORDER BY bm25(knowledge_fts), e.display_order;
```

`?`에는 검색식을 인자로 전달한다. 도메인 필터가 있으면 조건과 인자를 추가한다. 검색식이 비었거나 FTS 결과가 없으면 `LIKE` 검색으로 넘어가는 코드가 있다. 검색 지원 범위를 설명할 때 이 대체 경로까지 말하면 실제 구현을 더 정확히 설명할 수 있다.

모델에 쓰는 `semantic_text`는 개념 이름·정의·직관·핵심 관계를 묶은 문서다. 사용자에게 표시되는 선택지 한 문장과 동일하지 않다. 이후 `answer_word_similarity` 등의 이름을 보고 ‘정답 선택지 텍스트만 비교했다’고 말하지 않도록 주의한다. [S04]

풀이·복습은 `UserRepository`의 `element_progress`, `wrong_queue` 등에서 개념 ID와 연결된다. 코드의 통계 조회는 시도 수·정답 수를 합산하고 미해결 오답을 조회한다. 예를 들어 `COALESCE(SUM(attempts), 0)`는 데이터가 없을 때 합계 NULL을 0으로 바꾼다. 이것은 코드에서 확인한 기능이며 실제 사용자 로그를 열어 효과를 분석한 것은 아니다. [S13]

### 판단·검증 · P1

SQLite를 사용했다는 사실과 복잡한 분석 SQL을 직접 작성한 경험은 별개다. 면접에서는 실제 검색 쿼리의 조인·조건·정렬·인자 처리를 먼저 설명한다. ‘왜 이 방식을 선택했나’는 코드가 증명하는 동작과 당시 개인의 선택 이유를 나누어 답한다. 모바일 로컬 검색과 잘 맞는 구조라는 설명은 가능하지만, 당시 여러 DB를 벤치마크했다고 단정할 근거는 없다.

### 확인 문제와 짧은 답변

**Q1. 같은 개념이 두 행씩 검색되면 무엇부터 확인하나요?**  
**A.** 각 조인 테이블의 `element_id` 유일성, FTS의 동일 ID 중복, 조건 적용 전후 행 수를 확인한다. `DISTINCT`를 먼저 붙여 원인을 숨기지 않는다. 이 답은 추가 학습용 점검 방식이며 실제 발생한 오류라는 뜻은 아니다.

**Q2. 이 bullet을 짧게 설명해 보세요.**  
**A.** “금융 개념의 설명·공식·출처를 개념 ID로 연결하고, 앱에서 검색과 퀴즈에 활용하는 구조를 만들었습니다. 개념 검색은 SQLite FTS5와 BM25를 사용합니다. 문제 제작용 후보 검색은 별도의 Python 파이프라인입니다.”

<a id="b2"></a>
## 3. Bullet 2: 오답 후보·18개 특성·랭킹

> Trained an 18-feature XGBoost ranking model in Python to select plausible incorrect quiz choices from other concept descriptions; compared 198 keyword and pretrained embedding retrieval configurations.

한국어 의미: 다른 개념 설명 중 그럴듯한 오답 후보를 선택하기 위해 Python으로 18개 특성의 XGBoost 랭킹 모델을 학습하고, 키워드·사전학습 임베딩을 이용한 검색 설정을 비교했다.

### 학습 목표 · P0

후보·특성·라벨·그룹·예측 점수를 구분하고 검색부터 랭킹까지 실제 입력·출력을 설명한다.

### 필요한 개념

**검색(retrieval)**은 후보를 좁히는 단계, **랭킹(ranking)**은 후보의 우선순위를 정하는 단계다. 검색에서 빠진 후보는 그 뒤 랭커가 되살릴 수 없으므로 두 단계를 따로 평가한다.

**TF-IDF**는 문서의 단어 또는 문자열 조각을 가중치 벡터로 표현한다. 특정 문서에 자주 나오지만 전체 문서에서 흔하지 않은 표현이 비교에 기여한다. `fit`은 어휘·문서빈도 등의 기준을 만들고 `transform`은 그 기준으로 문서를 숫자로 바꾼다. 이 프로젝트의 word 설정은 1~2그램, char_wb 설정은 2~5그램이다. [S04; scikit-learn 1.7.2 공식 문서](https://scikit-learn.org/1.7/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html)

**임베딩**은 사전학습 모델이 텍스트를 숫자 벡터로 바꾼 표현이다. FinDone은 이를 후보 유사도 계산에 사용한다. BGE-M3 모델 카드에는 dense·sparse·multi-vector 기능이 있지만, 이 프로젝트 코드는 SentenceTransformer로 만든 정규화 벡터의 유사도를 사용한다. 모델이 지원하는 모든 기능을 프로젝트에서 썼다고 말하지 않는다. [S04; BGE-M3 공식 모델 카드](https://huggingface.co/BAAI/bge-m3)

**RRF(Reciprocal Rank Fusion, 순위 역수 결합)**는 여러 신호의 원점수를 직접 더하는 대신 순위를 결합한다. 실제 코드는 `Σ weight / (60 + rank)`를 사용한다. 단어 유사도·문자 유사도·같은 도메인 등의 점수 범위가 달라도 순위로 묶을 수 있다. 대신 원점수 사이의 간격은 반영하지 못한다. [S04·S05]

**Learning to Rank(순위 학습)**는 같은 질문 안에서 어떤 후보를 더 앞에 놓을지 학습한다. `qid`는 그 질문의 그룹 ID다. XGBoost의 `rank:ndcg`는 NDCG를 고려하는 순위 학습 목적함수이며, 예측값은 후보 정렬용 점수다. 점수 0.8을 ‘80% 확률로 좋은 오답’이라고 해석할 수 없다. [S04; XGBoost 공식 설명](https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html)

### 나의 실제 적용: 후보를 만드는 순서

1. 개념별 정의·직관·수식 없는 관계 설명으로 문제와 정답을 만든다.
2. 같은 정답 개념, 겹치는 이름 별칭, 대상 용어가 드러나는 후보 설명 등을 제외한다.
3. 정의형에서는 양쪽 정의에 명시적 역할 근거가 있고 그 역할이 불일치할 때 후보를 제외한다. 근거가 부족하면 추정으로 제외하지 않는다.
4. TF-IDF·메타데이터와 선택한 임베딩의 신호를 RRF로 결합해 최대 30개를 검색한다.
5. 문제와 후보 쌍마다 18개 특성을 만든다. 학습 시에는 관련성 라벨과 `qid`를 함께 제공한다.
6. 학습된 모델로 후보 점수를 계산해 내림차순 정렬하고 문항을 조합한다. 최종 선택지에는 정답 1개와 오답 4개가 들어간다. 선택지 A~E의 배열과 모델 순위는 동일하다고 가정하지 않는다. [S04·S05·S06]

**최종 문항 조합에는 추가 규칙이 있다.** 문항 조합 함수는 순위 목록을 읽되 관련성 등급 2 이상을 우선하고, 제목·문장 중복과 대상 용어 노출을 피한다. 네 개를 채우지 못하면 낮은 등급까지 후보 범위를 넓히는 코드도 있다. 따라서 랭커의 상위 4개와 최종 오답 4개가 항상 같지는 않다. `predict` 자체는 라벨을 입력받지 않지만, 최종 콘텐츠 조합은 약지도/사람 관련성 값을 다시 참조한다. 전체 파이프라인의 품질을 전부 모델만의 성과로 돌리면 안 된다. [S04: 1990행 이후 문항 조합]

### 18개 특성 전체표 · P0/P1

아래 이름은 코드의 값을 설명하기 위한 이름이며 순서는 `_candidate_features`의 배열 순서다. `target`은 문제의 정답 개념, `candidate`는 오답 후보 개념이다.

| 번호 | 특성 | 실제 비교·계산 |
|---:|---|---|
| 1 | 질문-후보 word 유사도 | 문제 stem과 후보의 개념 문서 |
| 2 | 질문-후보 char 유사도 | 같은 대상의 문자 n-gram 비교 |
| 3 | 정답 개념-후보 word 유사도 | 두 개념 문서의 word 벡터 비교 |
| 4 | 정답 개념-후보 char 유사도 | 두 개념 문서의 char 벡터 비교 |
| 5 | 질문-후보 임베딩 유사도 | 질문과 후보 문서의 dense 벡터 비교 |
| 6 | 정답 개념-후보 임베딩 유사도 | 두 개념 문서의 dense 벡터 비교 |
| 7 | 같은 도메인 | `target.domain_id == candidate.domain_id`의 0/1 |
| 8 | 같은 mode | 콘텐츠의 mode 메타데이터가 같은지 0/1 |
| 9 | 제목 길이 비율 | 정규화한 두 제목 길이의 `min/max` |
| 10 | 후보 제목 토큰 겹침 | `질문 토큰∩후보 제목 토큰 수 / 후보 제목 토큰 수` |
| 11 | 대문자 약어 패턴 공유 | 정규식으로 추출한 제목 패턴의 공통 값 유무 |
| 12 | ACC one-hot | 후보가 ACC 도메인이면 1 |
| 13 | CF one-hot | 후보가 CF 도메인이면 1 |
| 14 | INV one-hot | 후보가 INV 도메인이면 1 |
| 15 | FI one-hot | 후보가 FI 도메인이면 1 |
| 16 | DER one-hot | 후보가 DER 도메인이면 1 |
| 17 | EQV one-hot | 후보가 EQV 도메인이면 1 |
| 18 | IBT one-hot | 후보가 IBT 도메인이면 1 |

**One-hot**은 범주 하나를 여러 개의 0/1 열로 표시하는 방법이다. 7개 도메인을 숫자 1~7로 넣어 임의의 크기 순서를 만들지 않는다. 11번은 코드의 대문자 패턴 휴리스틱이다. 자연어의 모든 약어를 정확히 판별하는 언어 분석기라는 의미가 아니다.

특성은 ‘모델이 볼 정보’, 라벨은 ‘맞춰야 할 등급’, 예측 점수는 ‘학습 후 모델 출력’이다. 이 셋을 섞지 않는다. 콘텐츠 제작 때는 정답 개념을 알고 있으므로 정답 개념 문서를 특성 계산에 쓸 수 있다. 사용자가 정답을 모르는 문제풀이 상황과 데이터 가용성이 다르다.

### 실제 학습 설정 · P1

선택된 랭커는 `xgboost-shallow-medium`이다. 코드에서 목적함수 `rank:ndcg`, 검증 지표 `ndcg@4`, 최대 300개 트리, depth 3, learning rate 0.1, subsample 0.9, colsample_bytree 0.9, L2 계수 1.0, early stopping 25를 확인했다. ‘300개를 설정했다’와 ‘실제로 최적 단계에 300개를 모두 썼다’는 다르다. 최적 반복 수를 말하려면 모델 속성을 별도로 확인해야 한다. [S04·S07]

트리는 특성 조건에 따라 입력을 나누고 점수를 만든다. 부스팅은 여러 트리의 출력을 더하면서 목적함수를 개선하는 방식이다. 깊이는 한 트리가 표현하는 복잡도, 학습률은 각 트리의 기여 크기를 조절한다. 위 값은 FinDone의 실험 설정이며 모든 데이터에 최적인 보편값이 아니다.

비교 대상으로 pairwise logistic도 있다. 같은 질문의 후보 쌍에서 더 높은 라벨의 후보가 앞서도록 특성 차이를 학습한다. 모델명에 logistic이 들어가도 최종 후보 점수를 교육 품질 확률로 보정한 것은 아니다. [S04: `train_pairwise_logistic`]

### 198개는 무엇을 비교했나

| 표현 방식 | 검색 프로필 수 | 랭커 설정 수 | 실행 수 |
|---|---:|---:|---:|
| TF-IDF 기본 방식 1개 | lexical 3개 | logistic C 3개 + XGBoost 3개 | 18 |
| 사전학습 임베딩 5개 | lexical 3개 + semantic 3개 | 같은 6개 | 180 |
| 합계 | | | **198** |

다섯 dense 모델은 multilingual-e5-small, multilingual-MiniLM-L12, KURE-v1, BGE-M3, multilingual-e5-base다. 따라서 ‘6개의 사전학습 임베딩’이라고 말하면 TF-IDF까지 사전학습 모델로 세는 오류가 생긴다. 최신 보고서 JSON에서 198개 모두 completed이고 testEvaluated는 하나만 true임을 다시 집계했다. [S05·S07, R01]

또한 dense 모델을 사용하면서 lexical 검색 프로필을 택한 실행도 있다. 이 경우 검색 가중치에서 dense를 사용하지 않더라도 랭커의 5·6번 특성에는 임베딩 유사도가 들어갈 수 있다. 프로필 이름만 보고 전체 파이프라인이 lexical-only라고 단정하지 않는다. [S04]

### 판단·검증과 확인 문제

**Q1. 왜 XGBoost를 썼나요?**  
**A.** “동일 문제의 후보를 여러 특성으로 비교하는 순위 학습 문제로 구성했고, pairwise logistic과 XGBoost 설정들을 validation에서 비교했습니다. 최종 설정은 validation NDCG@4가 가장 높은 구성이었습니다.” 당시 최초 도입 동기는 본인 확인이 필요하다. [F03·F06·F07]

**Q2. 임베딩 모델도 직접 학습했나요?**  
**A.** “확인된 파이프라인은 사전학습 임베딩으로 유사도를 만들고 XGBoost 랭커를 학습합니다. 임베딩을 처음부터 학습했다는 경험은 아닙니다.” [S04]

**Q3. 후보 검색을 없애고 전체를 랭킹하면 안 되나요?**  
**A.** “가능한 대안입니다. 이 구현은 후보를 30개로 좁힌 후 랭킹하므로 검색 누락이 생길 수 있습니다. 전체 후보 랭킹과 비용·품질을 비교해야 필요성을 더 명확히 말할 수 있습니다.” 해당 대안을 실제로 실험했다고 말할 근거는 아직 없다.

<a id="b3"></a>
## 4. Bullet 3: 분할·실험·결과 해석

> Separated 95/20/20 concepts for training/validation/testing; selected configurations using validation data, evaluated on test data, and documented automatically generated relevance labels, experimental settings and comparative results.

한국어 의미: 개념을 학습·검증·테스트로 분리하고 검증 데이터로 설정을 선택한 뒤 테스트를 평가했으며, 자동 관련성 라벨과 설정·비교 결과를 기록했다.

### 학습 목표 · P0

test NDCG@4 0.922445가 무엇을 측정하는지, 무엇을 입증하지 못하는지 설명한다.

### 필요한 개념: 라벨과 지표

**약지도(weak supervision)**는 사람의 개별 정답 판정 대신 규칙 등으로 학습 신호를 만드는 방식이다. 이 코드의 canonical 라벨은 질문 word/char, 정답 개념 word/char, 같은 도메인, 같은 mode의 6개 신호를 동일 가중치 RRF로 결합해 만든다. 임베딩 점수는 canonical 약지도 신호에 직접 포함되지 않는다. [S04·S05]

| RRF 순위 | 관련성 라벨 | 평가에서의 취급 |
|---|---:|---|
| 1~4위 | 3 | 강한 관련 후보 |
| 5~8위 | 2 | 관련 후보 |
| 9~20위 | 1 | 약한 관련 후보 |
| 21위 이후 | 0 | 낮은 관련 후보 |

필터로 제외된 원소의 내부 값 -1은 정상 학습 라벨 종류가 아니다. 허용 후보를 만들고 그 안의 0~3 등급을 사용한다. 관련성은 ‘이 오답이 정답이다’라는 의미도 아니다.

**NDCG@4**는 상위 4개 후보의 등급과 순서를 이상적인 순서와 비교한다. 이 프로젝트의 DCG는 `Σ(2^label−1)/log2(position+1)`이고 position은 1부터 센다. 가능한 후보 전체의 라벨을 내림차순으로 정렬해 IDCG@4를 구하고 `DCG/IDCG`를 계산한다. 그런 다음 대상 split의 문항별 점수를 평균한다. [S04: `evaluate_ranking`]

**학습용 계산:** 라벨 `[3, 3, 2, 2]`의 DCG@4는 약 14.209이고, 이상적인 `[3, 3, 3, 3]`의 IDCG@4는 약 17.931이므로 NDCG는 약 0.7924다. 두 목록 모두 Precision@4는 1이지만 순위 품질은 같지 않다. 이 수치는 이해를 위해 만든 예시이며 저장된 특정 문항의 결과가 아니다.

| 지표 | 실제 코드의 의미 | 해석상 주의 |
|---|---|---|
| Recall@20 | 전체 허용 후보 중 라벨≥2인 후보가 검색 상위 20개에 얼마나 포함됐는가 | 검색 한도는 30이어도 평가 k는 20 |
| NDCG@4 | 랭킹 상위 4개의 등급과 순서를 이상적인 상위 4개와 비교 | 정확도 92.2%로 바꿔 말하지 않음 |
| Precision@4 | 상위 4개 중 라벨≥2의 비율 | 2와 3을 같은 ‘관련’으로 취급 |
| MRR | 처음 등장한 라벨≥2 후보 순위의 역수, 문항 평균 | 첫 후보만 좋아도 1이므로 오답 4개 전체 품질을 보장하지 않음 |

### 나의 실제 적용: 분할과 선택

도메인별 개수를 고려해 20개 test와 20개 validation을 배분하고, seed와 개념 ID를 이용한 해시 정렬로 소속을 정한다. 같은 개념에서 파생된 정의·직관·관계 문항은 같은 split에 들어간다. 현재 파일로 분할을 다시 만들었을 때 저장된 split JSON과 일치했다. [S04·S05·S11, R01]

| 분할 | 대상 개념 | 파생 문항 | 사용 |
|---|---:|---:|---|
| train | 95 | 285 | 랭커 학습 |
| validation | 20 | 60 | early stopping, 설정 선택, 검토 프로필 선택 |
| test | 20 | 60 | 선택된 구성의 평가 |

선택 규칙은 validation NDCG@4의 최고점이고, 허용 오차 0이다. 정확히 동률일 때 복잡도 등을 고려한다. 이 한 실행의 기록에는 197개 구성의 test가 없고 최종 구성 하나에 test가 있다. 다만 이전 날짜의 다른 실험에도 test 기록이 있으므로 ‘프로젝트 전체에서 test를 단 한 번도 다시 보지 않았다’고 확장할 수 없다. [S07]

### 결과표 · P0

아래 비교는 같은 기준 실험의 validation이며, 기본 구성 두 개와 최종 구성을 보여 준다. 전체 후보 검색·랭킹 구성이 달라지는 비교이므로 성능 차이를 특정 기능 하나의 인과 효과로 해석하지 않는다.

| 표현 / 검색 / 랭커 | validation NDCG@4 | validation P@4 |
|---|---:|---:|
| TF-IDF / lexical-balanced / logistic C=0.1 | 0.844506 | 0.908333 |
| TF-IDF / lexical-balanced / XGBoost shallow-medium | 0.965142 | 0.995833 |
| BGE-M3 / semantic-conservative / XGBoost shallow-medium | **0.969918** | **1.000000** |

최종 구성과 TF-IDF+동일 XGBoost 사이의 validation NDCG 차이는 **0.004776**이다. 작은 차이이며 검증 집합은 20개 개념이다. ‘임베딩으로 성능이 크게 개선됐다’고 과장하기보다, 이 검증 집합의 선택 기준에서 해당 구성이 가장 높았다고 말한다. 순수 검색-only 기준의 test 개선 폭은 이 표로 알 수 없다.

| 최종 구성 지표 | validation | test |
|---|---:|---:|
| Recall@20 | 0.987500 | 0.983333 |
| NDCG@4 | 0.969918 | 0.922445 |
| Precision@4 | 1.000000 | 0.991667 |
| MRR | 1.000000 | 1.000000 |

출처: S07. 저장 모델·캐시를 사용한 이번 재계산 범위와 결과는 [부록 B](#reproduction)에 별도로 기록한다.

### 판단·검증: 반드시 말할 네 가지 한계

**첫째, 라벨의 독립성이다.** 관련성 라벨과 모델 특성이 단어·문자 유사도와 메타데이터를 공유한다. 따라서 높은 점수는 설계한 기준을 얼마나 재현했는지에 가깝다. 사람 관련성 라벨 수와 human test coverage는 0으로 기록되어 있다. 실제로 헷갈리면서 교육적으로 적절한 오답인지 별도의 사람 평가가 필요하다.

**둘째, 분할의 경계다.** 대상 개념과 파생 문항은 분리하지만 후보 코퍼스는 전체 개념이다. TF-IDF도 `전체 개념 문서 + train 질문`으로 fit한다. 따라서 ‘test 개념의 텍스트를 전혀 보지 않은 완전 신규 개념 일반화’ 실험은 아니다. 기존 전체 사전을 후보로 사용하면서 보류한 대상 개념을 평가하는 조건에 가깝다. 후보 등장만으로 누수라고 단정하지 말고 사용 시점에 해당 사전이 가용한지와 평가 목표를 함께 설명한다. [S04: `build_feature_context`]

**셋째, 설정 선택의 불확실성이다.** 20개 validation 개념으로 198개 구성을 비교하면 그 집합에 우연히 잘 맞는 구성이 선택될 수 있다. 새 독립 개념·사람 라벨 평가나 개념 단위 반복 검증은 현재의 개선안이다. 이를 이미 수행한 것처럼 쓰지 않는다.

**넷째, 수동 검토와 모델 성능의 구분이다.** 문제은행에 Owner 승인 기록이 있어도 모든 test 후보에 독립적인 관련성 등급을 부여한 것은 아니다. `release_ready`는 운영 게이트 상태이며 교육 효과나 모델 일반화의 증거가 아니다.

약지도 가중치를 바꾼 저장 실험에서는 semantic-heavy가 303문항, domain-heavy가 184문항의 Top-4 집합을 바꿨다. 기준 대비 평균 Jaccard는 각각 0.627937, 0.786667이다. **Jaccard**는 두 집합의 교집합 크기를 합집합 크기로 나눈 값이다. 이는 가중치 변화에 대한 후보 안정성을 나타내며 정답률이 아니다. [S07]

### 확인 문제와 답변

**Q1. NDCG@4 0.922445면 문제의 92%가 맞았나요?**  
**A.** “아닙니다. 자동 관련성 라벨을 기준으로 상위 4개 후보의 순위 품질을 정규화한 평균입니다. 문제 정답률이나 학습 효과가 아닙니다.”

**Q2. 데이터 누수를 어떻게 막았나요?**  
**A.** “대상 개념 단위로 나눠 같은 개념의 파생 문항이 여러 split에 흩어지지 않게 했습니다. 다만 전체 개념 사전이 후보와 TF-IDF fit에 포함되므로 신규 개념을 전혀 보지 않은 평가라고 말할 수는 없습니다.”

**Q3. 자동 라벨인데 굳이 모델이 필요한가요?**  
**A.** “현재 실험은 여러 특성·검색 조합으로 자동 기준을 얼마나 재현하는지 비교한 단계입니다. 규칙만 적용하는 방법을 넘어서는 실질적 교육 품질 개선은 독립 사람 평가와 적절한 기본 방법 비교가 더 필요합니다.”

<a id="b4"></a>
## 5. Bullet 4: 문제은행·검사·재승인

> Assembled a 405-question bank and ranked candidates during content production; combined automated checks with manual review for answer leakage, duplicate choices and concept mismatches, and required renewed approval after content changes.

한국어 의미: 콘텐츠 제작 과정에 후보 순위화를 적용해 405문항을 만들고, 자동 검사·수동 검토와 변경 후 재승인을 연결했다.

### 학습 목표 · P0

한 문제의 생성 결과와 자동 통과·수동 승인·변경 후 승인 무효화의 차이를 설명한다.

### 필요한 개념

**하드 검사**는 반드시 충족해야 하는 조건을 확인한다. **검토 큐**는 사람이 판단할 예외 목록이다. **fingerprint(내용 지문)**는 검토 대상 내용을 해시로 식별하는 값이다. 같은 문제 ID라도 내용이 달라지면 이전 승인과 연결하지 않아야 한다.

### 나의 실제 적용: 405문항의 구성

각 개념에서 `term_to_definition`, `term_to_intuition`, `term_to_verbal_relation`의 3문항이 생성된다. `build_facts_and_questions`는 실제로 405개의 사실과 405개의 문제를 구성하고 개수를 검사한다. 관계형 사실은 코드에서 `derived_unreviewed`로 표시되므로 원문 정의를 가져오는 작업과 동일한 검토 상태로 취급하지 않는다. [S04]

| 문제은행 현재 상태 | 문항 수 | 의미 |
|---|---:|---|
| automated_pass | 402 | 자동 검토 기준을 통과한 문항 |
| owner_approved | 3 | 해당 내용 지문에 Owner 승인 기록이 연결된 문항 |
| needs_owner_review | 0 | 현재 승인 대기 문항 없음 |
| blocked | 0 | 현재 차단 문항 없음 |

수동 승인된 문제 ID는 `CF-07-term_to_definition-01`, `EQV-13-term_to_definition-01`, `EQV-15-term_to_definition-01`이다. 개별 기록 3건과 현재 검토 입력에 대한 배치 승인 기록이 있다. 기록의 존재와 일치를 확인한 것이며, 검토자가 실제로 무엇을 얼마나 읽었는지나 직접적인 기여 범위는 별도 확인 대상이다. [S06·S10]

### 실제 문제 한 건: ACC-01

질문은 “용어: 회계등식과 차변·대변 / 다음 중 이 용어의 정의로 가장 정확한 것은?”이다. 정답 설명은 “이 개념은 회사가 가진 자산의 재원이 채권자 몫인 부채와 주주 몫인 자본으로 나뉜다는 기본 구조다.”이다. 문제은행의 선택지는 다음과 같다. 문장 요약은 읽기 위한 축약이다. [S06]

| 키 | 출처 개념 | 선택지 요약 | 정답 여부 |
|---|---|---|---|
| A | INV-07 | 여러 공통 위험요인과 보상으로 기대수익률 설명 | 오답 |
| B | DER-06 | 콜·풋 가치를 주식·무위험채권 조합에 연결하는 무차익 관계 | 오답 |
| C | IBT-03 | 신용위험 보상 변화에 따른 회사채 가격 민감도 | 오답 |
| D | ACC-01 | 자산의 재원을 부채와 자본으로 나누는 구조 | 정답 |
| E | IBT-09 | 신주 발행 물량과 기존주주 매각 물량 구분 | 오답 |

이 문제는 `automated_pass`다. 사례를 보면 자동 통과가 ‘모든 오답이 사람에게 매우 헷갈린다’는 뜻이 아님을 알 수 있다. 주제가 다른 후보가 포함되어 있어 난이도·구별 가능성을 별도로 평가할 여지가 있다. 이는 현재 자료를 읽고 내린 해석이며 사용자의 실제 오답률을 측정한 결과가 아니다.

### 같은 문제의 검색·특성·순위 재현 · P1

ACC-01 정의형 문제는 validation 소속이다. 후보 필터 후 허용 후보는 23개이고 검색 한도 30보다 작아 23개가 검색됐다. 검색 상위 5개는 `IBT-09 → DER-06 → EQV-52 → INV-07 → IBT-03`이다. 저장 랭커로 재계산하면 다음 순서가 나온다. [R02]

| 랭킹 순위 | 후보 ID | 예측 점수 | 약지도 라벨 | 최종 선택지 |
|---:|---|---:|---:|---|
| 1 | IBT-09 | 0.046414 | 3 | E |
| 2 | DER-06 | 0.037123 | 3 | B |
| 3 | INV-07 | -1.755691 | 3 | A |
| 4 | IBT-03 | -1.761943 | 3 | C |
| 5 | EQV-52 | -2.084672 | 2 | 미포함 |
| 6 | EQV-62 | -2.715696 | 1 | 미포함 |

예측값은 음수여도 문제가 없다. 후보 사이에서 큰 점수를 앞에 놓는 데 사용한다. 이 사례에서는 상위 4개와 최종 오답 집합이 일치했고, 라벨이 모두 3이므로 해당 문항의 NDCG@4·P@4는 1이다. 그렇더라도 사람이 느끼는 오답의 설득력까지 1로 측정한 것은 아니다.

실제 후보 IBT-09의 대표 특성 3개를 재계산했다.

| 특성 | 실제 입력과 계산 | 결과 |
|---|---|---:|
| 같은 도메인 | ACC와 IBT 비교 | 0 |
| 같은 mode | calculation과 calculation 비교 | 1 |
| 제목 길이 비율 | 정규화 제목 `회계등식과차변대변` 9자, `ipoprimarysecondary` 19자 → 9/19 | 약 0.473684 |

같은 후보의 질문-후보 dense 유사도는 약 0.361866, 정답 개념-후보 dense 유사도는 약 0.577186이었다. 이는 해시가 일치하는 저장 행렬의 값이며 이번에 BGE-M3를 다시 다운로드·인코딩한 값은 아니다. 특성 18개와 라벨을 결합해 학습할 때 동일 문제의 23개 행은 하나의 그룹에 속한다. 이 문제 자체는 validation이므로 train 행에 들어가지 않는다.

### 검사와 상태 변화 · P1

| 검사·검토 | 구현·기록의 의미 | 잡지 못할 수 있는 것 |
|---|---|---|
| 용어 노출 | 선택지 문장에 대상·출처 용어가 드러나는지 확인 | 의미상 정답을 암시하는 모든 표현 |
| 중복 | 선택지 텍스트 중복 등 구조 점검 | 다른 문장으로 표현된 의미 중복 |
| 정의 역할 호환 | 양쪽 정의에 명시적 역할 근거가 있을 때 불일치 후보 제외 | 근거가 없거나 추출 규칙에 걸리지 않는 의미 불일치 |
| 약한 오답·불안정성 | 약지도 등급, 여러 구성의 지지, 순위 경계 등 확인 | 학습자에게 적절한 난이도인지 |
| Owner 승인 | 해당 문항 내용과 배치 입력의 승인 기록 연결 | 독립적인 전체 모델 성능 평가 |

검토 프로필은 validation 예외율과 목표 예외율의 거리로 선택한다. 저장 보고서의 `exception-only`는 validation 60문항 중 1문항, 1.67%의 예외율이다. 목표는 5%다. 예외율이 낮다는 사실만으로 오류 탐지의 재현율이 높다고 볼 수 없다. 잘못된 문항을 얼마나 놓쳤는지 알려면 별도의 사람 기준 표본이 필요하다. [S07]

개별 승인 키는 `(questionId, questionFingerprint)`다. fingerprint에는 stem·설명·난이도·출처 사실·각 선택지 텍스트·정답 여부 등이 들어간다. 내용 변경으로 지문이 달라지면 예전 승인 키가 일치하지 않는다. 자동 검사도 다시 거쳐야 하며, 새 내용에 대한 판단 없이 기존 승인을 이어 붙이면 안 된다. [S04: `load_owner_decisions`, `_question_review_fingerprint`]

```text
새 문항 → 자동 검사 → 자동 통과 / 검토 필요 / 차단
검토 필요 → 현재 내용에 대해 승인 또는 반려
검토 관련 내용 변경 → 새 fingerprint → 기존 승인과 불일치 → 재검사·필요한 재승인
```

앱 DB 빌더는 `automated_pass`, `owner_approved`를 앱 제공 가능 상태로 정의한다. 그러나 DB에 포함되었다는 사실과 실제 외부 사용자에게 배포했다는 사실은 구분한다. [S09]

### 확인 문제와 답변

**Q1. 승인된 문항의 선택지 한 글자를 수정해도 승인을 다시 받아야 하나요?**  
**A.** “검토 대상 내용의 지문이 바뀌므로 기존 개별 승인과 일치하지 않습니다. 변경 결과를 재검사하고 새 검토 상태에 맞는 승인을 받아야 합니다.” 모든 수정이 반드시 수동 큐로 간다고 단정하기보다 자동 재검사와 기존 수동 승인 무효화를 구분한다.

**Q2. 자동 검사가 있으니 수동 검토는 불필요하지 않나요?**  
**A.** “문자열·구조·규칙 기반 검사는 의미나 교육적 적절성을 모두 판단하지 못합니다. 자동 검사는 반복 가능한 조건을 확인하고 사람은 예외와 의미를 검토합니다. 다만 이 프로젝트의 독립 사람 평가 범위는 제한적입니다.”

<a id="decisions"></a>
## 6. 본인의 판단과 문제 해결

### 학습 목표 · P0

기능 목록을 넘어 판단·대안·검증으로 설명하되 당시 개인 행동을 만들어 내지 않는다.

### 필요한 개념

**시스템의 설계 이유**, **당시 본인이 실제로 생각한 이유**, **지금 돌아보며 제안하는 개선안**은 다르다. 코드의 장점을 설명할 수 있어도 당시 의사결정 과정을 그대로 복원한 것은 아니다.

### 나의 실제 적용: 말할 수 있는 결정 구조

| 결정 | 확인 가능한 구현·기록 | 본인에게 확인할 내용 |
|---|---|---|
| 대상 개념 단위 분할 | 같은 개념의 3문항을 같은 split에 배치 | 이 분할을 처음 선택한 이유·담당 범위 |
| 여러 검색·랭커 구성 비교 | 198개 validation 실행과 선택 결과 | 대안 목록 구성 과정에서 직접 내린 결정 |
| 후보 정의 역할 필터 | 정의문의 명시적 역할 근거와 불일치 제외 | 오류를 처음 발견한 경위·수정 기여 |
| 지문 기반 승인 | 문항 내용과 승인 키 연결 | 실제 검토·승인 참여 범위 |

### 판단·검증: 기록에 있는 실패·수정 사례

모델링 README는 초기 v3 실행에서 대상 개념명 노출 49건을 발견했고, 후속 실행에서 해당 문장을 후보 단계에서 제외해 대상·출처 개념명 노출을 0으로 만들었다고 기록한다. 이 사례는 **v3의 저장된 실패·수정 기록**이며, v2.2 405문항의 성능 변화와 합쳐 말하지 않는다. 이번 작업에서는 그 v3 전 과정을 재실행하지 않았다. [S12, 원자료 확인]

사례 설명 구조는 다음과 같다. “자동 생성 후보에서 용어가 드러나 답을 쉽게 추정할 수 있는 문제가 기록되었습니다. 문항을 만든 후에만 찾는 대신 후보 단계에서 제외하는 검사를 추가한 흐름이 확인됩니다. 후속 기록의 해당 노출 지표는 0입니다. 다만 이 수정의 제안·구현·검토 중 제가 직접 맡은 범위는 [본인 확인]입니다.”

최신 v2.2 이전 실행에서는 임베딩 의존성 누락으로 6개 후보 중 1개와 18개 구성만 실행된 기록도 있다. 후속 198개 completed 실행으로 대체되었다. 이 사례는 ‘성공한 부분만 전체 실험 성공으로 보고하지 않고 실행 상태를 구분해야 한다’는 설명에 사용할 수 있다. 특정 개발자가 무엇을 고쳤는지는 별도 근거가 필요하다. [S12]

### 현재의 개선안 · 추가 학습

우선 독립 사람 라벨을 만드는 기준부터 정한다. 후보가 문법적으로 자연스러운지, 정답과 혼동 가능하지만 실제로 틀린지, 난이도가 적절한지를 분리해 평가할 수 있다. 다음으로 단순 규칙·검색-only와 최종 파이프라인을 동일 평가 조건에서 비교한다. 개념 단위로 결과 변동을 확인하고, 검토 예외율뿐 아니라 잘못된 문항을 얼마나 놓치는지도 측정한다. 이는 아직 수행 완료된 프로젝트 성과가 아니다.

### 확인 문제

**Q. “AI가 대부분 만든 것 아닌가요?”에 어떻게 답하나요?**  
**A.** “AI가 지원한 범위와 제가 직접 결정하고 확인한 범위를 구분해서 말씀드리겠습니다. [직접 설계한 기준], [직접 수정한 코드], [검증한 사례]는 각각 다음 근거가 있습니다.” 빈칸은 본인의 실제 경험으로 채워야 한다. 저장소에 코드가 있다는 이유로 이 답을 자동 완성하지 않는다.

<a id="pwc"></a>
## 7. PwC 업무와 연결하기

### 학습 목표 · P0

공고의 업무와 연결되는 실제 작업 방식을 구체적으로 말한다.

### 필요한 개념

**분석 기준 설계**는 ‘무엇을 이상하거나 관련 있다고 볼 것인가’를 재현 가능한 규칙으로 정하는 일이다. 기준을 정한 뒤 결과를 확인하고 예외·오류·한계를 설명하는 과정이 함께 필요하다. 금융 앱을 만들었다는 주제 유사성만으로 기업 리스크 분석 경험을 보유했다고 볼 수 없다.

### 나의 실제 적용과 판단·검증

| 공고의 업무 | 연결할 실제 경험 | 면접에서 말할 경계 |
|---|---|---|
| SQL·Python 데이터 추출·전처리·분석 | 개념 ID·필수 필드 확인, 문서 벡터화, 후보별 특성, SQL 조인 검색 | 직접 작성·수행 범위는 확인 필요 |
| 리스크·이상징후 분석 기준 설계 지원 | 관련성 등급·후보 제외·품질 검사 기준의 명시와 구현 | 기업 이상거래 탐지를 수행한 것은 아님 |
| 결과 해석·산출물 | split·설정·지표·한계·승인 상태를 기록 | 자동 라벨 성능을 실제 교육 효과로 표현하지 않음 |

연결 답변: “이 경험에서 데이터 단위를 정하고 판단 기준을 코드로 만들며, 비교 결과의 의미와 한계를 구분하는 과정을 다뤘습니다. 공고의 데이터 분석·기준 설계 지원에서도 먼저 업무 데이터의 단위와 관계를 이해하고, 기준의 근거와 예외를 확인하는 방식으로 기여하고 싶습니다. 기업 시스템의 업무 흐름과 리스크 기준은 추가로 배워야 할 영역입니다.”

### 확인 문제

**Q. FinDone에서 실제로 이상징후 탐지를 했다고 말해도 되나요?**  
**A.** 아니오. 오답 후보 순위화·콘텐츠 검사 경험이다. 공통되는 분석·검증 방식으로 연결하고 업무 도메인의 차이를 인정한다. BI·ERP 경험은 이 자료집의 근거로 확인하지 않았다.

<a id="practice"></a>
## 8. Walkthrough 답변과 복습

### 학습 목표 · P0

짧은 설명에서 시작해 질문받은 지점을 더 깊게 설명하고, 검증 범위를 넘는 질문에는 한계와 필요한 확인을 답한다.

### 필요한 개념과 실제 적용

답변은 ‘한 일 → 어떻게 → 결과 → 한계’의 흐름으로 연습한다. 모든 수치를 첫 답변에 넣을 필요는 없다. 질문받으면 해당 bullet의 데이터·표·근거로 이동한다. 아래 문안의 개인 동기·직접 기여는 [부록 C](#personal)의 확인이 필요하다.

### 30초 요약

“FinDone은 금융 개념 학습 앱과 콘텐츠 관리 웹을 만든 개인 프로젝트입니다. 135개 개념을 기반으로 문제를 구성하고, 다른 개념의 설명 중 오답 후보를 고르는 Python 랭킹 모델을 적용했습니다. 검색과 랭커 설정을 검증 데이터로 비교하고 405문항을 구성했습니다. 자동 검사와 승인 절차도 연결했으며, 모델 점수는 자동 라벨 기준이어서 실제 교육 품질과는 구분해 해석하고 있습니다.”

### 2분 설명

“FinDone에서는 금융 개념의 설명·공식·출처를 퀴즈와 연결하는 Android 앱과 관리 웹을 만들었습니다. 개념 검색은 SQLite FTS5/BM25를 사용하고, 오답 후보를 만드는 작업은 별도의 Python 파이프라인으로 구성했습니다.

모델은 문제의 정답을 찾는 것이 아니라, 정답 개념을 이미 아는 콘텐츠 제작 상황에서 다른 개념의 설명을 오답 후보로 순위화합니다. 단어·문자 유사도, 임베딩 유사도, 도메인 등의 18개 특성을 사용했고, TF-IDF와 사전학습 임베딩, 검색 결합 방식, 랭커 설정을 조합해 198개 구성을 비교했습니다.

분할은 대상 개념 기준으로 95개 학습, 20개 검증, 20개 테스트를 사용했습니다. 같은 개념에서 나온 세 문항은 같은 분할에 속합니다. 검증 NDCG@4로 선택한 최종 구성의 test NDCG@4는 약 0.922였습니다. 다만 자동 생성 관련성 라벨을 사용한 결과여서 실제로 교육적으로 좋은 오답이라는 독립 평가와 같지는 않습니다. 전체 사전이 후보와 TF-IDF에 포함된다는 평가 조건도 있습니다.

최종 문제은행은 405문항이며 현재 기록은 자동 통과 402문항과 Owner 승인 3문항으로 나뉩니다. 내용 지문으로 승인을 연결해 내용이 바뀌면 기존 승인을 그대로 적용하지 않도록 했습니다. 이 경험을 통해 설명할 수 있는 핵심은 모델 이름 자체보다 데이터 단위, 판단 기준, 검증 결과와 한계를 연결하는 과정입니다.”

### 판단·검증: 꼬리질문 지도

| 질문 · 중요도 | 답변의 핵심 | 근거 |
|---|---|---|
| 모델 입력 한 행은 무엇인가요? · P0 | 문제와 오답 후보 개념의 쌍, 18개 숫자. 같은 문제의 후보가 한 그룹 | F03 |
| 자동 라벨은 어떻게 만들었나요? · P0 | 6개 신호 RRF의 순위 구간을 0~3 등급으로 변환 | F04 |
| 정답 정보를 쓰면 누수 아닌가요? · P1 | 콘텐츠 제작 시 정답은 이미 가용. 평가 분할의 정보 경계는 별도로 점검 | F03·F05 |
| 198개를 전부 test로 비교했나요? · P0 | 해당 실행 기록은 validation 비교 후 하나만 test. 전체 실험 이력의 재사용 여부는 구분 | F06·F08 |
| 얼마나 좋아졌나요? · P0 | 같은 validation의 TF-IDF+동일 랭커 대비 NDCG 0.004776 차이. test 개선 폭 주장 안 함 | F07 |
| 사람이 검토했다면서 라벨이 0개인가요? · P1 | 문항 승인과 후보 관련성 평가 라벨은 서로 다른 기록 | F04·F09 |
| 자동 통과는 품질을 보장하나요? · P0 | 규칙 통과이며 학습 효과·의미 적절성의 완전 보장이 아님 | F09 |
| 지금 개선한다면요? · P1 | 독립 사람 라벨, 검색-only 비교, 개념 단위 안정성, 검사 누락 평가 | 현재 개선안 |
| 직접 한 일이 무엇인가요? · P0 | 설계·구현·분석·검토 각각의 실제 행동과 자료 제시 | 본인 확인 |

### 확인 문제와 답안

**문제 1 · P0:** 135개에서 정의·직관·관계형을 만들면 405문항이다. 학습 후보 행을 405개라고 해도 되는가?  
**답:** 안 된다. 학습은 train 285문항의 검색 후보마다 행이 생긴다. 한 문항에 후보가 30개라면 8,550행이지만 실제 후보 수를 확인해 계산해야 한다. 원 전체 후보 수와 검색 후 학습 행 수도 구분한다.

**문제 2 · P1:** 관련성 라벨 상위 4개가 `[3,2,2,2]`인 모델과 `[2,3,2,2]`인 모델의 P@4는 같은가? NDCG는 같은가?  
**답:** P@4는 둘 다 1이다. 첫 모델은 더 높은 등급을 앞에 두므로 같은 IDCG에서 NDCG가 더 높다.

**문제 3 · P1:** “test 개념은 전처리에서 한 번도 보지 않았다”는 설명을 코드와 대조하라.  
**답:** TF-IDF fit에 전체 개념 문서가 들어가므로 부정확하다. 대상 질문 분할과 후보 사전 사용을 나누어 설명한다.

**문제 4 · P0:** 402개 자동 통과와 3개 Owner 승인, humanLabelCount 0을 함께 설명하라.  
**답:** 콘텐츠 상태는 405문항을 분류한다. humanLabelCount는 모델 학습·평가용 후보 관련성 라벨의 수다. 문항 승인 3건이 그 라벨 데이터를 대신하지 않는다.

**문제 5 · P1:** 검토 예외율이 25%에서 1.67%로 낮아졌다면 검사 품질이 개선됐는가?  
**답:** 검토량은 줄었지만 놓친 오류가 늘었는지 알 수 없다. 같은 독립 사람 기준으로 오탐·미탐을 확인해야 한다.

**문제 6 · P1:** 왜 선택된 모델의 test 점수와 다른 모델의 validation 점수를 빼서 개선 폭을 말하면 안 되는가?  
**답:** 대상 데이터가 다르므로 모델 변경과 집합 차이가 섞인다. 같은 split과 평가 조건으로 비교해야 한다.

**문제 7 · P2:** 사람 라벨을 보완한다면 어떤 단위로 평가 세트를 만들 것인가?  
**답:** 먼저 사용 목표를 고정하고 대상 개념 단위로 독립 평가 범위를 만든다. 후보의 의미 적절성·오답 타당성·난이도 기준을 명시하고 서로 독립적인 평가와 불일치 처리를 설계한다. 정답/오답 선택지의 단순 형식 통과와 별도 평가다. 현재의 설계 제안이며 수행 기록은 아니다.

복습 완료 기준은 숫자 암기보다 각 답에 ‘어떤 자료가 근거인가’, ‘어디까지 확인했는가’를 붙여 말할 수 있는지다.

<a id="evidence"></a>
## 부록 A. 주장별 근거표와 자료 목록

아래 경로는 이 Markdown 파일을 기준으로 연결한다. 소스 행 번호는 확인일의 코드 위치이며 이후 변경될 수 있어 함수명도 함께 기록한다. 저장소 HEAD는 `d632b9ec14225b9286359b43d60ae6b4ea357ccc`였다. 이는 이번 확인 버전이며 8월 당시 개발자의 행동 전체를 증명하지 않는다.

| ID | 자료·위치 | 확인 범위 |
|---|---|---|
| S01 | `Kyuri_Moon_Resume_ (1).pdf` 1쪽 FinDone | 네 bullet 원문, 기간·역할. 앞선 설계 단계에서 전체 확인 |
| S02 | `PwC공고.pdf` 실제 파일 1~2쪽 | 주요 업무·지원 자격·전형. 앞선 설계 단계에서 전체 확인 |
| S03 | [개념 카탈로그](../admin/data/content-elements.generated.json) | 고유 ID·개념 텍스트·메타데이터 |
| S04 | [모델 파이프라인](../tools/train_concept_question_model.py) | 421행 load_elements, 483행 build_split, 539행 facts/questions, 1161행 후보 필터, 1252행 feature context, 1593행 특성, 1679행 검색, 1759행 행렬, 1839행 XGBoost, 1916행 평가, 2178행 문항 지문, 2716행 자동 검토 |
| S05 | [모델 설정](../content/model/concept-model-config.json) | 분할·검색·약지도·랭커 설정 |
| S06 | [문제은행](../content/model/concept-question-bank.generated.json) | 405문항·개별 상태·실제 선택지·지문 |
| S07 | [실험 JSON](../admin/data/concept-model-experiments.generated.json), [기준 실험 보고서](../docs/modeling/experiments/cmq-v2-20260816-014214-89cf4e66.md) | 최신 실행의 198개 구성·선택·평가·사람 라벨·검토 통계 |
| S08 | [앱 콘텐츠 저장소](../app/src/main/java/com/findone/app/data/ContentRepository.kt) 183행 searchElements | FTS 조인·정렬·대체 검색 경로 |
| S09 | [앱 DB 빌더](../tools/build_content_db.py) 33행·424행 및 DB schema | 앱 제공 가능 검토 상태·문제은행 읽기 |
| S10 | [Owner 결정 기록](../content/model/concept-owner-decisions.jsonl) | 3개 문항 승인·배치 승인. 불필요한 계정 식별자는 본문에 옮기지 않음 |
| S11 | [고정 split](../content/model/concept-split.json) | 대상 개념별 소속·콘텐츠 지문 |
| S12 | [모델링 이력](../docs/modeling/README.md) | v2.2/v3 구분·이전 실패 기록·한계 |
| S13 | [사용자 기록 저장소](../app/src/main/java/com/findone/app/data/UserRepository.kt) 160행·277행·304행 | 풀이 기록·개념별 진행·오답 큐 및 집계 코드 |

모든 S03~S13 확인일은 2026-09-15다. 공개 문서는 부록 C에 구분한다. 저장 모델·행렬 캐시는 `build/concept-model/`의 로컬 산출물이며 원본 저장소 배포본에 항상 포함된다고 가정하지 않는다.

| 주장 ID | 주장 | 근거 ID | 검증 방법 | 확인 결과 | 상태 | 답변에 사용할 표현 | 남은 확인 |
|---|---|---|---|---|---|---|---|
| F01 | 135개 개념·405개 문항 | S03·S06·S11, R01 | ID·상태·분할 집계 | 135개 대상, 405개 고유 문항, 자동 402·승인 3 | 재현 확인 | “405문항 문제은행을 구성했다” | 실제 이용·배포 규모 |
| F02 | 검색과 랭킹의 경로 | S04·S08·S09 | 함수·호출 목적 구분, SQL 조회 | 앱 FTS/BM25와 제작용 후보 검색 분리 | 원자료 확인·부분 재현 | “모델은 콘텐츠 제작에 사용했다” | 전체 앱 실행 추적 |
| F03 | 18개 특성·학습 그룹 | S04·S05, R02 | 배열 순서·qid·실제 특성 확인 | 11개 수치/일치 특성+7개 도메인 열 | 원자료 확인·부분 재현 | “문제-후보 쌍을 18개 값으로 표현했다” | 본인의 특성 설계 과정 |
| F04 | 자동 관련성 라벨 | S04·S07 | 라벨 생성 코드·라벨 통계 확인 | RRF 순위 0~3, 사람 라벨 0 | 원자료 확인 | “자동 기준에 대한 순위 평가다” | 독립 사람 품질 평가 |
| F05 | 95/20/20 분할·정보 경계 | S04·S11, R01 | split 재생성·fit 입력 확인 | split 일치, 전체 개념 문서 fit 포함 | 재현 확인·원자료 확인 | “대상 개념 기준으로 분리했다” | 완전 신규 개념 평가 |
| F06 | 198개와 선택 방식 | S05·S07, R01 | 조합·완료·test 플래그 집계 | 198 completed, 한 실행 내 test 1구성 | 재현 확인 | “validation 기준으로 선택했다” | 전체 실험 의사결정 타임라인 |
| F07 | 실제 성능과 비교 | S04·S07, R02 | 저장 모델·캐시 추론 및 지표 재계산 | 부록 B 참조 | 재현 범위 별도 표시 | “test NDCG@4 약 0.922, 자동 라벨 기준” | 독립 평가·검색-only test 비교 |
| F08 | 평가 불확실성 | S04·S07·S12 | 분할·여러 실행 기록 해석 | 작은 validation, 여러 날짜 test 기록 | 원자료 확인·해석 | “완전한 일반화 증거는 아니다” | test 확인 후 변경 여부의 본인 설명 |
| F09 | 자동 검사·승인·변경 | S04·S06·S10, R03 | 승인 지문 대조·메모리 변경 | 부록 B 참조 | 부분 재현·추가 학습 | “내용에 맞는 승인만 연결한다” | 실제 수정 사건의 담당·검토 내용 |
| F10 | 모델 기여·앱 운영 | S01·S04·S07·S09 | 제작 코드·산출물·보고서 확인 | 제작 시 랭킹, 보고서 runtime model calls 0 | 원자료 확인 | “오프라인 콘텐츠 제작의 후보 순위화” | 사용자 효과·직접 기여 |

<a id="reproduction"></a>
## 부록 B. 재현 기록과 실행 방법

이 절은 이번 자료집 작성 중 수행한 확인을 기록한다. 모델 재학습, 198개 전체 재실행, 독립 사람 평가와 구분한다.

### R01. 수량·분할·실험 기록 대조 — 재현 확인

개념 카탈로그로 `load_elements → build_split → build_facts_and_questions`를 실행했다. 원래 split JSON과 재생성 결과가 같고, content fingerprint도 문제은행과 일치했다. 학습/검증/test는 95/20/20개 개념 및 285/60/60문항이었다. JSON을 읽어 405개 고유 문제 ID, 자동 통과 402개·Owner 승인 3개를 집계했다.

최신 실험 JSON의 실행 수는 TF-IDF 18개, 다섯 임베딩별 36개, 합계 198개였고 모두 completed였다. test 플래그는 true 1개·false 197개다. 이 확인은 저장 기록의 내부 일관성 재계산이며 당시 198개 학습을 다시 실행한 것은 아니다.

### R02. 저장 모델 추론·지표 재계산 — 재현 확인

입력은 S03·S05·S11, canonical balanced 약지도, 선택 프로필 semantic-conservative, 검색 한도 30이다. 다음 두 로컬 파일의 SHA-256이 기준 실험 보고서와 일치함을 확인했다.

| 산출물 | SHA-256 |
|---|---|
| 선택 XGBoost joblib | `f4421a9cc33ec197b676224b1a5b412e52986cde1447e4da6477dbf07079eb83` |
| BGE-M3 유사도 npz | `7003771d9d81958f0f784dba05302816a946d1831c84cfe0d79fadc5bdfef780` |

TF-IDF·약지도·후보 검색을 다시 계산하고 저장된 모델로 추론한 뒤 프로젝트의 `evaluate_ranking`을 실행했다. 최종 구성의 validation/test 네 지표 모두 4장의 저장값과 소수점 6자리까지 일치했다. TF-IDF/lexical-balanced의 logistic C=0.1과 XGBoost shallow-medium도 validation NDCG@4가 각각 0.844506, 0.965142로 일치했다. 두 비교 모델의 test는 새로 평가하지 않았다.

ACC-01의 23개 검색 후보, 상위 6개 점수·등급, IBT-09의 특성도 확인했다. 이 재현은 **기존 모델·캐시를 이용한 추론·평가 재실행**이다. 평가 코드 자체의 개념적 타당성, BGE-M3의 새 인코딩, 모델 재학습 결과, 독립 사람 품질은 별도로 검증해야 한다.

### R03. 승인과 형식 검사 — 부분 재현·추가 학습

현재 Owner 승인 문항 3개의 `(questionId, 재계산 fingerprint)`가 승인 기록과 모두 일치했다. `CF-07-term_to_definition-01`을 메모리에서 복사해 stem에 학습용 문구를 붙였을 때 이전 승인 키는 일치하지 않았다. 실제 파일이나 승인 기록은 변경하지 않았다. 이 실습은 지문에 따른 연결 조건을 확인한 것이며, 실제 UI에서 수정·승인·배포 전 과정을 실행한 검증은 아니다.

405개 문항 모두 선택지 5개, 정답 1개, 정규화한 선택지 문자열의 문항 내 중복 없음도 다시 확인했다. 의미 중복이나 교육적 적절성을 전수 평가한 것은 아니다.

### R04. 앱 패키지 DB 조회 — 재현 확인

`app/src/main/assets/content.sqlite3`를 읽기 전용으로 열었다. elements는 135개, concept_questions는 자동 통과 402개·Owner 승인 3개였다. 로컬 Python SQLite에서 앱 검색 구조를 따른 `MATCH 'ROE'` 조회 상위 결과는 다음과 같았다.

| 순서 | 개념 | BM25 점수 |
|---:|---|---:|
| 1 | ACC-12 / ROA·ROE·DuPont 분해 | -4.851253 |
| 2 | EQV-09 / ROE | -4.710884 |
| 3 | EQV-44 / 5단계 DuPont | -4.429846 |

작은 BM25 값이 앞에 온다. 이 결과는 패키지 DB의 SQL 동작 확인이며 Android 화면이나 사용자 기기의 런타임 검증을 대신하지 않는다.

### 재실행용 코드

다음은 수행한 핵심 확인을 다시 실행할 수 있도록 정리한 코드다. 임시 위치에 `verify_walkthrough.py`로 저장한 뒤 `python <스크립트의 절대경로> C:/Users/Insun/FinDone`으로 실행한다. 저장소 경로는 인자로 받으므로 실행 위치에 의존하지 않는다. 기존 joblib와 npz가 필요하며 내려받기·재학습·원본 수정은 하지 않는다. joblib는 이 저장소에서 생성한 신뢰하는 파일만 읽는다.

```python
import copy
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "tools"))
import train_concept_question_model as m

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

cfg = read(m.DEFAULT_CONFIG)
bank = read(m.DEFAULT_BANK)
report = read(m.DEFAULT_ADMIN_REPORT)
exp = next(x for x in report["experiments"]
           if x["experimentId"] == "cmq-v2-20260816-014214-89cf4e66")
elements = m.load_elements()
assignments, split = m.build_split(elements, cfg)
facts, questions = m.build_facts_and_questions(elements, assignments)
assert split == read(m.DEFAULT_SPLIT)
assert m.content_fingerprint(elements) == bank["contentFingerprint"]
assert len({q["questionId"] for q in bank["questions"]}) == 405
print("states", Counter(q["reviewStatus"] for q in bank["questions"]))
print("runs", Counter(x["status"] for x in exp["rankerRuns"]))
print("test flags", Counter(x["testEvaluated"] for x in exp["rankerRuns"]))

weak = next(p for p in cfg["weakSupervisionProfiles"] if p["id"] == "balanced")
context = m.build_feature_context(elements, questions, weak, 60)
embedding = m.baseline_embedding_run(context)
embedding.candidate_id = "bge-m3"
expected = next(e["matrixCacheSha256"] for e in exp["embeddings"]
                if e["candidateId"] == "bge-m3")
cache = next(p for p in (root / "build/concept-model/embeddings/bge-m3").rglob("*.npz")
             if sha(p) == expected)
with np.load(cache, allow_pickle=False) as data:
    embedding.query_candidate_similarity = data["queryCandidate"]
    embedding.answer_candidate_similarity = data["answerCandidate"]

cases = [
    ("bge-m3", "semantic-conservative", "xgboost-shallow-medium"),
    ("tfidf-word-char", "lexical-balanced", "pairwise-logistic-c0p1"),
    ("tfidf-word-char", "lexical-balanced", "xgboost-shallow-medium"),
]
for eid, pid, rid in cases:
    run = next(x for x in exp["rankerRuns"]
               if (x["embeddingId"], x["retrievalProfileId"], x["rankerId"])
               == (eid, pid, rid))
    model_path = root / run["modelArtifact"]
    assert sha(model_path) == run["modelSha256"]
    emb = embedding if eid == "bge-m3" else m.baseline_embedding_run(context)
    profile = next(p for p in cfg["retrievalProfiles"] if p["id"] == pid)
    retrieved = m.retrieve_candidates(context, emb, 30, profile, 60)
    ranked = m.rank_candidates(context, emb, retrieved, joblib.load(model_path))
    names = ("validation", "test") if eid == "bge-m3" else ("validation",)
    for name in names:
        actual = m.evaluate_ranking(context, retrieved, ranked, {}, name)
        expected_metrics = exp["evaluation"][name] if eid == "bge-m3" else run[name]
        assert actual == expected_metrics
        print(eid, rid, actual)
    if eid == "bge-m3":
        qi = next(i for i, q in enumerate(questions)
                  if q.question_id == "ACC-01-term_to_definition-01")
        ci = next(i for i, e in enumerate(elements) if e.element_id == "IBT-09")
        print("example candidate count", len(retrieved[qi]))
        print("features", m._candidate_features(context, qi, ci, emb).tolist())
        print("top6", [(elements[i].element_id, score,
                        int(context.weak_relevance[qi, i]))
                       for i, score in ranked[qi][:6]])

decisions, batches = m.load_owner_decisions()
for q in bank["questions"]:
    assert len(q["choices"]) == 5
    assert sum(c["isCorrect"] for c in q["choices"]) == 1
    assert len({m.normalized_key(c["text"]) for c in q["choices"]}) == 5
    if q["reviewStatus"] == "owner_approved":
        assert (q["questionId"], m._question_review_fingerprint(q)) in decisions
q = next(q for q in bank["questions"] if q["reviewStatus"] == "owner_approved")
changed = copy.deepcopy(q)
changed["stem"] += " [추가 학습용 수정]"
assert (changed["questionId"], m._question_review_fingerprint(changed)) not in decisions

db_uri = (root / "app/src/main/assets/content.sqlite3").as_uri() + "?mode=ro"
with sqlite3.connect(db_uri, uri=True) as con:
    print("DB states", con.execute(
        "SELECT review_status, COUNT(*) FROM concept_questions GROUP BY review_status"
    ).fetchall())
    print("ROE", con.execute(
        "SELECT e.element_id, e.title, bm25(knowledge_fts) FROM knowledge_fts "
        "JOIN elements e ON e.element_id=knowledge_fts.element_id "
        "WHERE knowledge_fts MATCH ? "
        "ORDER BY bm25(knowledge_fts), e.display_order LIMIT 3", ("ROE",)
    ).fetchall())
print("walkthrough checks passed")
```

### 저장소 검증과 한계

자료집의 국소 재계산과 별개로 저장소 지정 preflight 검증을 실행한다. 실행 결과는 아래 검증 기록에 남긴다. 모델 검증의 상대경로 CLI 출력은 `build/concept-ci`에 작성되어 원래 선택 모델과 문제은행을 덮어쓰지 않는다.

2026-09-15 실행한 `python tools/repo_preflight.py verify --scope model --changes working`은 통과했다. 포함된 4개 명령은 다음과 같다.

1. `python -m unittest tools.test_local_content_model tools.test_build_content_db tools.test_train_concept_question_model tools.test_repo_preflight -v` — 51개 테스트 통과.
2. `python tools/validate_concept_question_reset.py` — v2 활성 계약·405문항 등 확인 통과.
3. `python tools/train_concept_question_model.py --ranker pairwise-logistic --quiet --split build/concept-ci/split.json --question-bank build/concept-ci/question-bank.json --build-dir build/concept-ci` — CI와 같은 상대경로 CLI 완료.
4. `python tools/compile_app_content.py --check --benchmark-rounds 3 --report build/local-content-model-report.json` — 결정론적 DB compile check 통과.

3번은 CI 확인용 TF-IDF·pairwise 실행이며 선택된 BGE-M3/XGBoost의 재학습이 아니다. 이 실행의 별도 test 수치를 8월 기준 실험의 결과표에 섞지 않았다. 이 확인에서는 release Gradle 작업이나 APK 게시를 수행하지 않았다. 앱 기능·학습 코드·생성 fixture는 수정하지 않았다.

<a id="personal"></a>
## 부록 C. 미확인 사항·추가 학습·공식 문서

### 본인 확인이 필요한 항목

| 항목 | 채워야 할 내용 | 도움이 되는 근거 |
|---|---|---|
| 시작 동기 | 처음 겪은 불편, 목표 사용자, 해결하려던 문제 | 당시 노트·대화·기획 기록 |
| 직접 기여 | 설계·코드·특성·실험·검토에서 직접 한 행동 | 커밋·수정 전후·분석 노트 |
| AI 지원 | 제안·코드 생성·검토 중 지원받은 범위와 직접 검증한 부분 | 작업 기록과 구체적 수정 사례 |
| 선택 이유 | 실제로 검토한 대안과 포기 이유 | 당시 비교 문서 |
| 실험 이력 | 이전 test 결과를 보고 후속 설정을 바꾸었는지 | 실행 시점·결정 기록 |
| 수동 검토 | 어떤 문제를 어떤 기준으로 직접 읽고 승인했는지 | 승인 사유·검토 메모 |
| 운영 성과 | 배포·사용자·학습 효과 중 실제 측정한 것 | 배포·사용 로그·평가 자료 |

현재 확인된 기록이 없어도 원리와 구현 설명은 사용할 수 있다. 위 항목은 자신의 실제 기억과 자료로 확인하기 전까지 완료한 경험으로 채우지 않는다. 문서에 있는 ‘현재 개선안’과 학습용 계산·승인 변경 실습은 2026년 7~8월의 성과에 넣지 않는다.

### 공식 문서와 버전

- [SQLite FTS5](https://www.sqlite.org/fts5.html): MATCH와 BM25 점수 방향 확인. 앱 빌드에는 `androidx.sqlite:sqlite-bundled:2.7.0`이 명시되어 있다. Python 로컬 조회는 별도 SQLite 런타임이므로 앱 런타임과 동일하다고 주장하지 않는다.
- [scikit-learn 1.7.2 TfidfVectorizer](https://scikit-learn.org/1.7/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html): 프로젝트 의존성과 같은 버전의 개념·파라미터 설명. 실제 fit 코퍼스는 S04가 근거다.
- [XGBoost Learning to Rank](https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html): qid와 순위 학습 개념 확인. 확인 당시 stable 페이지는 3.4.1이고 프로젝트 기록은 3.4.0이다. 프로젝트의 목적함수·파라미터는 저장 코드·모델을 기준으로 썼으며 최신 기본값을 과거 설정으로 대입하지 않았다.
- [BGE-M3 공식 모델 카드](https://huggingface.co/BAAI/bge-m3): 모델 개념 확인. 실제 실행은 보고서의 고정 revision `5617a9f61b028005a4858fdac845db406aefb181`과 캐시 해시로 식별한다.

공식 문서는 원리를 설명하는 근거이고 개인 프로젝트의 성과를 증명하는 자료는 아니다. 이력서 PDF와 공고는 PwC 폴더의 원본을 보존했으며 연락처·계정 등의 불필요한 정보는 본문에 옮기지 않았다.
