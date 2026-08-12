# FinDone 개념형 5지선다 오프라인 모델링 설계서

- 문서 버전: 1.0
- 기준일: 2026-08-11
- 구현 상태: 승인된 구현 기준
- 적용 범위: 콘텐츠 데이터셋, 오답 랭커 학습·평가, 앱용 SQLite 생성, Admin 실험 이력

## 1. 결론

FinDone의 개념형 문제는 생성형 LLM을 앱이나 Admin에서 호출해 만드는 방식이 아니라, 저장소 안에서 실행되는 오프라인 빌드 파이프라인으로 만든다.

파이프라인은 기존 135개 금융 요소와 검토된 원문·학습 카드를 사실 데이터로 변환하고, 각 문항의 오답 후보를 생성한 뒤, 로컬 임베딩과 학습된 랭커로 좋은 오답 4개를 고른다. 최종 앱에는 모델이 아니라 검증을 통과한 문항·선택지만 SQLite로 들어간다. 앱 실행 중 API 호출과 모델 추론은 모두 0회다.

새 원본 DB가 추가되면 같은 코드가 사실 추출, 후보 생성, 랭킹, 자동 검증까지 반복한다. 사람은 마지막 검토에서 정답의 유일성, 오답의 타당성, 표현 품질을 승인한다. 승인되지 않은 실험이나 문항은 앱 DB에 릴리스할 수 없다.

## 2. 현재 상태와 바꿀 점

현재 구현에는 다음 한계가 있다.

- Android `QuizEngine`이 요소 제목을 이용해 4지선다 문제를 즉석 생성한다.
- 앱용 SQLite에는 `concept_cards`는 있지만 문항과 선택지 테이블은 없다.
- 기존 Admin 로컬 모델의 100% 지표는 콘텐츠 필드 충족률과 회귀 테스트 통과율이다. 학습된 ML 모델의 독립 테스트 정확도가 아니다.
- 현재 골든셋은 변환 규칙 회귀 테스트이며, 요소 단위로 격리한 ML 테스트셋이 아니다.
- 실제 사람 검토 오답 라벨은 아직 충분하지 않다.

따라서 구현을 다음처럼 변경한다.

1. 앱 문제를 5지선다로 통일한다.
2. 문항과 선택지를 빌드 시점에 생성해 앱용 SQLite에 넣는다.
3. 후보 검색 모델과 오답 랭커를 오프라인에서 학습·평가한다.
4. 학습·검증·테스트를 요소 ID 단위로 완전히 분리한다.
5. 약지도 라벨 성능과 사람 검토 독립 테스트 성능을 구분한다.
6. 모든 실행 이력과 릴리스 차단 사유를 Admin 로컬 모델 화면에 남긴다.

## 3. 목표와 비목표

### 목표

- 135개 기존 요소 전부에 최소 2개, 목표 3개의 개념형 5지선다 문항을 제공한다.
- 신규 원문 DB를 추가해도 같은 코드로 문항 후보를 자동 생성한다.
- 정답은 하나만 존재하고, 오답 4개는 그럴듯하지만 명백히 틀려야 한다.
- 결과는 동일 입력·설정·시드에서 완전히 재현되어야 한다.
- 독립 테스트 결과와 사람 검토 결과가 기준 미달이면 릴리스를 자동 차단한다.
- 앱에서는 모델 파일, Python, 네트워크 연결 없이 SQLite만 읽는다.

### 비목표

- 금융 전 영역을 자유롭게 서술하는 범용 생성 모델을 학습하지 않는다.
- 앱 안에서 실시간 문장 생성이나 임베딩 추론을 하지 않는다.
- 검토되지 않은 웹 문장을 자동으로 정답 사실로 확정하지 않는다.
- 약지도 데이터에서 얻은 점수를 실제 교육 품질 점수로 표시하지 않는다.
- 데이터 양만으로 “학습률”을 계산하지 않는다.

## 4. 용어

- **사실 레코드**: 요소의 정의, 핵심 관계, 직관, 활용 사례처럼 출처를 추적할 수 있는 최소 지식 단위다.
- **문항 그룹**: 하나의 질문과 정답 하나, 오답 후보 여러 개의 묶음이다.
- **검색 모델**: 전체 후보에서 관련 가능성이 있는 상위 후보를 찾는 임베딩 또는 TF-IDF 모델이다.
- **오답 랭커**: 검색된 후보 중 교육적으로 좋은 오답을 높은 순서로 배치하는 학습 모델이다.
- **약지도 라벨**: 동일 도메인, 텍스트 유사도, 금지 규칙 등을 이용해 코드가 만든 임시 라벨이다.
- **사람 라벨**: 검토자가 후보의 타당성과 모호성을 직접 판정한 라벨이다.
- **릴리스 문항**: 독립 테스트와 자동 검증을 통과하고 최종 승인된 문항이다.
- **준비도**: 데이터·라벨·평가·검토가 릴리스 조건을 얼마나 충족했는지 나타내는 운영 지표다. 모델 정확도와 다르다.

## 5. 전체 아키텍처

```text
검토된 원문/기존 DB/학습 카드
          │
          ▼
사실 정규화 + 출처/해시 고정
          │
          ▼
질문 템플릿 + 정답 + 오답 후보 생성
          │
          ├──────────────► 요소 단위 train/validation/test 분리
          │
          ▼
TF-IDF/임베딩 후보 검색
          │
          ▼
오답 랭커 학습 및 상위 4개 선택
          │
          ▼
중복·정답누출·모호성·출처 자동 검증
          │
          ▼
사람 최종 검토
          │
          ▼
concept_questions + concept_question_choices
          │
          ▼
앱용 content.sqlite3 패키징
```

Admin은 이 파이프라인을 실행하는 주체가 아니다. 저장소/CI에서 실행된 실험 보고서를 읽어 진행 상태와 결과를 기록·표시한다.

## 6. 파이프라인 단계와 진행률

실행 화면이나 CI 로그에는 로딩 원형 아이콘만 두지 않고, 현재 단계·전체 진행률·처리 건수·경과 시간을 함께 표시한다. 단계별 기본 가중치는 다음과 같다.

| 단계 | 작업 | 누적 진행률 |
|---|---|---:|
| 1 | 입력 스냅샷, 라이선스, SHA-256 확인 | 5% |
| 2 | 사실 레코드 정규화 | 15% |
| 3 | 질문과 오답 후보 생성 | 30% |
| 4 | 요소 단위 데이터 분할 확인 | 35% |
| 5 | 임베딩 후보 비교 및 검색 | 60% |
| 6 | 오답 랭커 학습 | 80% |
| 7 | 독립 평가와 자동 품질 검사 | 90% |
| 8 | 문항 은행 및 SQLite 생성 | 97% |
| 9 | 무결성·재현성 최종 검사 | 100% |

건수를 알 수 있는 단계는 확정형 진행 바를 사용한다. 모델 다운로드처럼 전체 크기를 즉시 알 수 없는 짧은 구간만 불확정형으로 표시하며, 다운로드가 시작되면 바이트 진행률로 전환한다. 실패 시 마지막 성공 단계, 오류 코드, 재시도 가능 여부를 보존한다.

## 7. 데이터 설계

### 7.1 사실 레코드

각 사실은 최소 다음 필드를 가진다.

```json
{
  "fact_id": "CF-01:definition:01",
  "element_id": "CF-01",
  "domain_id": "CF",
  "fact_type": "definition",
  "text": "...",
  "answer_text": "...",
  "source_ids": ["..."],
  "source_locator": "...",
  "review_status": "reviewed",
  "content_sha256": "..."
}
```

초기 `fact_type`은 `definition`, `core_relation`, `intuition`, `practical_use` 네 종류다. 출처가 없거나 검토 상태가 아닌 사실은 학습 후보로는 저장할 수 있지만 릴리스 문항의 정답 근거로 쓸 수 없다.

### 7.2 문항 그룹

초기 문항 형식은 설명을 보고 개념명을 고르는 방식으로 제한한다.

```json
{
  "question_id": "CF-01-definition-01",
  "element_id": "CF-01",
  "question_type": "definition_to_term",
  "stem": "다음 설명에 가장 부합하는 개념은 무엇인가?\n...",
  "correct_answer": "...",
  "fact_ids": ["CF-01:definition:01"],
  "candidate_ids": ["..."],
  "split": "train"
}
```

같은 요소에서 파생된 정의·직관·활용 문항은 반드시 같은 split에 둔다. 문장을 조금 바꾼 파생 문항이 train과 test에 동시에 들어가는 누수를 허용하지 않는다.

### 7.3 오답 후보와 라벨

후보 라벨은 다음 4단계다.

| 값 | 의미 |
|---:|---|
| 3 | 매우 좋은 오답: 같은 맥락에서 혼동하기 쉽지만 명백히 틀림 |
| 2 | 사용 가능한 오답 |
| 1 | 약한 오답: 너무 쉽거나 문맥 적합성이 낮음 |
| 0 | 사용 금지: 중복, 정답 가능, 모호함, 사실 오류, 표현 문제 |

각 판단에는 `label_source`를 반드시 기록한다.

- `weak_rule`: 코드가 만든 약지도
- `reviewer`: 한 명의 사람 검토
- `adjudicated`: 불일치를 조정한 확정 라벨

약지도만 있는 실험은 `bootstrap` 상태이며 실제 성능으로 릴리스할 수 없다.

### 7.4 데이터 규모 목표

기존 135개 요소 기준 목표는 다음과 같다.

- 사실 레코드: 최소 675개, 목표 1,000개 이상
- 문항 그룹: 초기 405개, 요소당 3개
- 원시 후보: 문항당 최대 134개, 약 54,000개
- 검색 후 랭킹 후보: 문항당 20개, 약 8,100개
- 사람 검토 라벨: train 2,000개 이상, validation 500개 이상
- 독립 test 라벨: 모든 test 요소, 문항당 상위 후보 8개 이상
- 앱 릴리스 문항: 최소 270개, 목표 405개

이는 시작 목표다. 데이터 수 자체는 성능이 아니므로 Admin에는 목표 대비 라벨 완료율로만 표시한다.

## 8. 데이터 분할

분할 단위는 행이 아니라 `element_id`다. 135개 요소를 도메인 비율을 유지해 다음처럼 고정한다.

- train: 95개 요소
- validation: 20개 요소
- test: 20개 요소

분할 파일에는 요소 목록, 생성 시드, 알고리즘 버전, 입력 콘텐츠 해시를 저장한다. 모델과 하이퍼파라미터 선택은 train과 validation만 사용한다. test는 후보와 설정을 고정한 뒤 한 번만 평가한다.

새 요소는 기본적으로 train 후보에 배정한다. test 구성을 바꿔야 할 때는 기존 결과와 직접 비교할 수 없으므로 split 버전을 올리고 새 기준선을 만든다.

## 9. 후보 생성 규칙

오답 후보는 전체 요소 제목에서 만들되 다음 순서로 필터링한다.

1. 정답 요소와 동일한 제목·별칭·정규화 문자열 제거
2. 정답 정의에 그대로 등장하는 후보 제거
3. 서로 같은 뜻인 별칭 후보 제거
4. 질문의 문법적 형태와 맞지 않는 후보 제거
5. 출처 또는 요소 ID가 없는 후보 제거
6. 같은 선택지 안에서 정규화 후 중복 제거
7. 자동 금지어와 저품질 문자열 제거

그다음 동일 도메인, 인접 도메인, 유사한 개념 구조의 후보를 충분히 남겨 검색 모델에 전달한다. 최종 4개는 가능한 경우 다음 구성을 우선한다.

- 동일 도메인의 강한 혼동 후보 2개
- 인접 도메인 또는 유사 관계 후보 1개
- 표현은 비슷하지만 핵심 차이가 있는 후보 1개

구성을 강제로 채우느라 품질 기준을 낮추지 않는다. 적합한 오답이 4개 미만이면 해당 문항은 `blocked_insufficient_distractors`로 차단한다.

## 10. 임베딩 모델 비교

특정 모델을 먼저 확정하지 않고 같은 validation 데이터로 후보를 비교한다.

| 후보 | 역할 | 장점 | 주의점 |
|---|---|---|---|
| word/char TF-IDF | 필수 기준선 | 작고 빠르며 완전 오프라인 | 의미 유사성 한계 |
| `multilingual-e5-small` | 경량 우선 후보 | 384차원, 비교적 작은 크기 | 입력 prefix 규칙 준수 필요 |
| `paraphrase-multilingual-MiniLM-L12-v2` | 속도 기준 후보 | 384차원, 검증된 다국어 계열 | 입력 길이 128 제한 |
| `KURE-v1` | 한국어 성능 후보 | 한국어 검색에 맞춘 BGE-M3 파생 | 모델 크기와 실제 도메인 성능 검증 필요 |
| `BAAI/bge-m3` | 대형 비교 후보 | 긴 문맥과 다국어 검색 지원 | 1024차원, 빌드 비용 큼 |
| `multilingual-e5-base` | 중간 크기 후보 | small보다 높은 표현력 기대 | 비용 대비 개선 폭 확인 필요 |

선정 순서는 다음과 같다.

1. 모든 후보에 같은 validation 문항과 후보 풀을 사용한다.
2. `Recall@20`, `NDCG@4`, 문항당 임베딩 시간, 모델 크기를 기록한다.
3. 최고 모델과 `NDCG@4` 차이가 1%p 이하이면 더 작고 빠른 모델을 선택한다.
4. 모델 ID뿐 아니라 정확한 revision, 라이선스, 파일 해시를 고정한다.
5. 모델을 받을 수 없거나 의존성이 없는 실행은 실패로 위장하지 않고 `skipped_unavailable`로 기록한다.

초기 구현의 필수 기준선은 TF-IDF다. 실제 임베딩 모델을 설치하지 않은 상태의 기준선 결과를 임베딩 모델 최종 성능으로 표시하지 않는다.

### 10.1 sparse/dense 결합 기준선

word sparse, char sparse, dense embedding은 원 점수 범위가 서로 다르므로 임의의 min-max 정규화 후 더하지 않는다. 기준선은 Cormack·Clarke·Büttcher의 Reciprocal Rank Fusion(RRF)을 사용한다.

$$
\mathrm{RRF}(d)=\sum_r \frac{w_r}{k+\mathrm{rank}_r(d)}
$$

- `k=60`: RRF 원 논문이 파일럿 조사 후 고정한 값
- 기준 가중치: 사용한 신호 모두 동일 가중치
- 비교 실험: dense 비중 0.2, 1/3, 0.5와 word/char 비중 변화
- 선택 기준: validation `NDCG@4`
- test 실행: validation에서 선택된 단 하나의 조합에만 수행

동일 가중치와 `k=60`만 reference baseline이다. 나머지 혼합비는 논문 기본값이 아니라 기준선 주변의 민감도 실험으로 보고서에 표시한다.

## 11. 오답 랭커

### 11.1 1차 모델

첫 모델은 RankNet의 pairwise logistic loss를 선형 모델로 구현한 scikit-learn 기반 pairwise ranker다. 동일 문항 안에서 높은 라벨 후보와 낮은 라벨 후보의 feature 차이를 학습한다. 이 방식은 설치 부담이 작고, 계수와 실패 원인을 확인하기 쉽다.

L2 정규화의 기준 `C=1.0`은 RankNet 논문의 값이 아니라 scikit-learn reference implementation의 기본값이다. `C={0.1, 1, 10}`을 로그 간격으로 validation에서 비교하며, 이 출처 구분을 실험 보고서에 그대로 남긴다.

초기 feature는 다음과 같다.

- 질문과 후보의 word TF-IDF cosine
- 질문과 후보의 char TF-IDF cosine
- 정답과 후보의 word/char cosine
- 선택한 임베딩 모델 cosine
- 동일 도메인 여부
- 도메인 쌍
- 제목 길이 비율
- 공통 토큰 비율
- 수식·숫자·약어 형태 일치 여부
- 후보의 과거 사람 승인율
- 중복·정답 누출·별칭 충돌 플래그

### 11.2 승격 후보

사람 라벨이 충분히 쌓이면 LambdaMART 계열인 XGBoost `XGBRanker`의 `rank:ndcg`를 비교한다. 첫 기준 조합은 XGBoost reference implementation의 `max_depth=6`, `eta=0.3`이며, 얕고 느린 학습 조합을 validation에서 비교한다. 이 숫자 역시 XGBoost 논문이 FinDone에 권한 최적값이 아니라 구현 기준값이라는 점을 명시한다. validation `NDCG@4`가 1%p 이상 개선되고 독립 test 및 안정성 게이트를 모두 통과할 때만 승격한다. 개선이 없다면 단순한 pairwise 모델을 유지한다.

### 11.3 모델이 학습하는 것

모델은 금융 지식을 새로 창작하는 것이 아니라, 이미 검토된 후보 중 어떤 오답 조합이 사람 기준에서 좋은지 순서를 학습한다. 정답 사실과 해설은 항상 검토된 콘텐츠 DB에서 가져온다. 이 경계 때문에 잘못된 모델 점수가 정답 사실을 바꾸지 못한다.

## 12. 평가 지표와 릴리스 게이트

모든 지표는 train이 아닌 고정 test에서 계산하고 표본 수와 95% 신뢰구간을 함께 기록한다.

### 검색 및 랭킹

- `Recall@20`: 좋은 오답 라벨 2 이상을 검색 단계가 얼마나 회수했는지
- `NDCG@4`: 상위 4개 순서가 사람 관련도와 얼마나 일치하는지
- `Precision@4`: 선택된 4개 중 라벨 2 이상 비율
- `MRR`: 가장 좋은 오답이 얼마나 앞에 배치되는지

### 문항 안전성

- 정답 유일성 위반률
- 정답 문자열/별칭 누출률
- 선택지 중복률
- 출처 누락률
- 모호 문항률
- 사람 최종 승인률

### 기본 릴리스 기준

| 게이트 | 기준 |
|---|---:|
| test 요소 라벨 커버리지 | 100% |
| Recall@20 | 95% 이상 |
| NDCG@4 | 0.80 이상 |
| Precision@4 | 0.90 이상 |
| 정답 유일성 위반 | 0건 |
| 중복·정답 누출 | 0건 |
| 출처 누락 | 0건 |
| 사람 최종 승인률 | 95% 이상 |
| 요소별 릴리스 문항 | 최소 2개 |
| 동일 입력 재빌드 SHA-256 | 일치 |

약지도 test에서 위 기준을 넘더라도 릴리스 상태는 `blocked_needs_human_test`다. 독립적인 사람 라벨 test가 준비돼야만 `release_ready`가 될 수 있다.

## 13. 앱용 SQLite 스키마

콘텐츠 스키마를 v2로 올리고 다음 테이블을 추가한다.

```sql
CREATE TABLE concept_questions (
    question_id TEXT PRIMARY KEY NOT NULL,
    element_id TEXT NOT NULL REFERENCES elements(element_id),
    question_type TEXT NOT NULL,
    stem TEXT NOT NULL,
    explanation TEXT NOT NULL,
    difficulty INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 3),
    model_version TEXT NOT NULL,
    review_status TEXT NOT NULL,
    source_fact_ids_json TEXT NOT NULL,
    display_order INTEGER NOT NULL UNIQUE
);

CREATE TABLE concept_question_choices (
    question_id TEXT NOT NULL REFERENCES concept_questions(question_id) ON DELETE CASCADE,
    choice_key TEXT NOT NULL CHECK (choice_key IN ('A','B','C','D','E')),
    choice_order INTEGER NOT NULL CHECK (choice_order BETWEEN 0 AND 4),
    element_id TEXT NOT NULL REFERENCES elements(element_id),
    text TEXT NOT NULL,
    explanation TEXT NOT NULL,
    is_correct INTEGER NOT NULL CHECK (is_correct IN (0,1)),
    PRIMARY KEY (question_id, choice_key),
    UNIQUE (question_id, choice_order)
);
```

DB 검증기는 각 문항에 선택지 5개와 정답 1개가 정확히 있는지 검사한다. Android는 `ContentRepository`에서 문항 은행을 읽고, seed에 따라 문항과 선택지 순서만 재현 가능하게 섞는다. A~E 키는 섞인 순서에서 다시 부여한다. DB 문항이 없는 비정상 상황의 fallback도 5지선다로 유지하되, 릴리스 빌드에서는 fallback 사용률이 0이어야 한다.

## 14. 실험과 산출물

### 추적 파일

- `content/model/concept-model-config.json`: 후보 모델, 시드, 게이트, feature 버전
- `content/model/concept-split.json`: 고정 요소 분할과 입력 해시
- `content/model/concept-review-labels.jsonl`: 사람 검토 라벨 원본
- `content/model/concept-question-bank.generated.json`: 검증된 앱 문항 은행
- `admin/data/concept-model-experiments.generated.json`: Admin 표시용 실행 이력

### 빌드 전용 파일

- `build/concept-model/facts.jsonl`
- `build/concept-model/candidates.jsonl`
- `build/concept-model/model.joblib`
- `build/concept-model/embeddings/`
- `build/concept-model/latest-report.json`

`build/` 산출물은 Git에 넣지 않는다. 앱 DB에는 최종 문항만 넣는다. 모델 바이너리를 역직렬화할 때는 저장소 빌드가 만든 해시 일치 파일만 허용한다.

### 실험 ID와 상태

실험 ID 형식은 `cmq-YYYYMMDD-HHMMSS-<config-hash8>`이다. 상태는 다음 중 하나다.

- `bootstrap`: 약지도 기반 초기 실행
- `training`: 실행 중
- `candidate`: 사람 test는 있으나 일부 게이트 미통과
- `release_ready`: 모든 게이트와 최종 검토 통과
- `rejected`: 성능 또는 안전성 게이트 실패
- `failed`: 실행 자체 실패

## 15. Admin 로컬 모델 대시보드

기존 규칙 기반 콘텐츠 변환 보고서와 개념형 ML 실험을 별도 섹션으로 표시한다. 둘의 100% 값을 합치거나 같은 “학습률”로 표현하지 않는다.

대시보드 필수 항목은 다음과 같다.

- 현재 단계와 전체 진행 바
- 실험 ID, 상태, 시작·종료 시각, 경과 시간
- 입력 DB/콘텐츠 해시와 데이터셋 버전
- train/validation/test 요소 수와 문항 수
- 약지도 라벨 수, 사람 라벨 수, 라벨 완료율
- 비교한 임베딩 후보와 선택·제외 사유
- 랭커 종류, feature 버전, 모델 해시
- validation/test `Recall@20`, `NDCG@4`, `Precision@4`, MRR
- 안전성 위반 건수와 사람 승인률
- 릴리스 게이트별 PASS/BLOCK
- 실패 단계, 오류 코드, 재실행 명령
- 과거 실험 목록과 직전 실험 대비 변화

실행 중에는 spinner와 진행 바를 동시에 표시한다. 완료된 기록은 정적 보고서로 남기며, 새 실행이 실패해도 직전 성공 기록을 덮어쓰지 않는다.

## 16. 자동화 명령

최종 명령 인터페이스는 다음처럼 통일한다.

```bash
python tools/train_concept_question_model.py \
  --write-question-bank \
  --write-admin-report

python -m unittest tools.test_train_concept_question_model -v
python tools/build_content_db.py
```

CI는 먼저 모델링 테스트를 실행하고, 질문 은행의 입력 해시가 현재 콘텐츠와 일치하는지 검사한 뒤 앱 SQLite를 만든다. 사람 라벨이 없는 초기 구현은 bootstrap 보고서와 미승인 문항 은행을 생성할 수 있지만, release 채널 패키징은 차단한다.

## 17. 재현성, 라이선스, 보안

- Python과 패키지 버전을 고정한다.
- 임베딩 모델은 model ID, revision, 라이선스, 파일 해시를 기록한다.
- 모든 split과 랜덤 동작은 명시된 seed를 사용한다.
- 원문마다 출처 locator와 콘텐츠 해시를 유지한다.
- 사용 조건이 확인되지 않은 원문은 학습·릴리스 대상에서 제외한다.
- 원문 추가 시 기존 test 정답이나 라벨을 자동 수정하지 않는다.
- 외부에서 받은 pickle/joblib 모델을 로드하지 않는다.
- Admin에는 비밀키, 로컬 절대 경로, 원문 전문을 실험 보고서로 노출하지 않는다.

## 18. 구현 순서와 완료 정의

### 1단계: 기반 파이프라인

- 사실·문항·후보 스키마 구현
- 95/20/20 고정 분할 구현
- TF-IDF 검색과 pairwise 랭커 구현
- 약지도 bootstrap 실행과 정직한 보고서 생성
- 단위 테스트 추가

완료 조건: 동일 입력에서 데이터셋, 보고서, 문항 은행 해시가 재현된다.

### 2단계: 앱 DB 연결

- SQLite 스키마 v2 추가
- 5지선다 문항/선택지 패키징
- Android repository와 `QuizEngine`을 DB 문항 우선으로 전환
- A~E 채점 및 fallback 테스트 추가

완료 조건: 앱의 모든 개념형 문항이 5개 선택지를 가지며 패키지 DB 무결성 검사를 통과한다.

### 3단계: 임베딩 bake-off

- E5-small, MiniLM, KURE-v1, BGE-M3 어댑터 구현
- 설치된 모델만 실행하되 skip 사유 기록
- validation 성능·속도·크기 비교

완료 조건: 동일 validation 집합의 비교표와 선택 근거가 자동 생성된다.

### 4단계: Admin 기록

- 실험 이력 타입과 generated JSON 연결
- 진행률, 데이터 분할, 지표, 게이트, 과거 실행 UI 구현
- bootstrap 점수를 실제 test 성능처럼 보이지 않게 표시

완료 조건: Admin에서 현재 실행 상태, 모델 선택 근거, 독립 test 유무, 릴리스 차단 사유를 한 화면에서 확인한다.

### 5단계: 사람 test와 최종 릴리스

- test 후보를 블라인드 검토
- 불일치 조정과 확정 라벨 저장
- test를 한 번 평가하고 기준 통과 여부 확정
- 승인 문항만 앱 DB로 재빌드

완료 조건: `release_ready` 실험, 0건의 안전성 위반, 최소 270개 승인 문항, 재현 가능한 SQLite SHA-256이 존재한다.

## 19. 구현 시 반드시 지킬 판단 기준

1. 현재 만들 수 있는 것은 먼저 bootstrap 모델이다. 사람 test가 생기기 전에는 “모델링 완료”나 “성능 100%”라고 쓰지 않는다.
2. 정답 사실 생성과 오답 순위 학습을 분리한다. 랭커가 정답을 쓰거나 고치게 하지 않는다.
3. 신규 DB는 자동으로 후보에 반영하되 자동 릴리스하지 않는다.
4. 더 큰 임베딩 모델이 근소하게 좋으면 작은 모델을 선택한다.
5. Admin 수치는 원본 보고서에서만 읽고 UI에 임의 상수를 넣지 않는다.
6. 테스트셋을 모델·feature 선택에 사용하지 않는다.
7. 로딩이 발생하는 모든 UI에는 단계 텍스트, spinner, 진행 바를 함께 제공한다.

## 20. 참고 구현 문서

- [Reciprocal Rank Fusion 원 논문](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf)
- [RankNet: Learning to Rank Using Gradient Descent](https://www.microsoft.com/en-us/research/wp-content/uploads/2005/08/icml_ranking.pdf)
- [From RankNet to LambdaRank to LambdaMART](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/MSR-TR-2010-82.pdf)
- [XGBoost: A Scalable Tree Boosting System](https://arxiv.org/abs/1603.02754)
- [BEIR 검색 기준선·평가 논문](https://arxiv.org/abs/2104.08663)
- [multilingual-e5-small 모델 카드](https://huggingface.co/intfloat/multilingual-e5-small)
- [multilingual-e5-base 모델 카드](https://huggingface.co/intfloat/multilingual-e5-base)
- [multilingual MiniLM 모델 카드](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)
- [KURE-v1 모델 카드](https://huggingface.co/nlpai-lab/KURE-v1)
- [BGE-M3 원 논문](https://arxiv.org/abs/2402.03216)
- [BGE-M3 공식 모델 카드](https://huggingface.co/BAAI/bge-m3)
- [XGBoost Learning to Rank](https://xgboost.readthedocs.io/en/release_3.0.0/tutorials/learning_to_rank.html)
- [scikit-learn GroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html)
