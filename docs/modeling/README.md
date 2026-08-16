# FinDone 개념형 모델 실험 기록

이 디렉터리는 오프라인 개념형 5지선다 모델링 실험의 사람이 읽을 수 있는 영구 기록이다.
Admin 시각화는 `admin/data/concept-model-experiments.generated.json`을 사용하고, 이 MD들은 감사·비교·의사결정 이력으로 유지한다.
v3.1 실험은 Admin에 바로 올리지 않고 이 디렉터리의 보고서와 선지 사전 검수본으로 먼저 확인한다.

- 설계 기준: [개념형 5지선다 오프라인 모델링 설계서](CONCEPT_MCQ_MODELING_DESIGN.md)
- v3.1 비율·랭커 실험 명령: `python tools/experiment_concept_question_model_v3.py --device cpu`
- v3.1 전체 preview·예외 검수 생성 명령: `python tools/generate_concept_question_preview_v3.py --device cpu`
- v2 생성 명령: `python tools/train_concept_question_model.py --all-embeddings --ranker all --write-question-bank --write-admin-report --write-markdown-report`
- 원칙: validation으로 조합을 선택하고 선택된 한 조합에만 test를 실행한다.

| 실험 | 시각 | 계약/상태 | 후보 임베딩 | 실행 조합 | 선택 구성 | val 지표 | test 지표 | 검수본 | 보고서 |
|---|---|---|---:|---:|---|---:|---:|---|---|
| `cmq-v2-20260816-014214-89cf4e66` | 2026-08-16T01:42:14.952565+00:00 | v2.2 / release_ready | 6 | 198 | `bge-m3/semantic-conservative/xgboost-shallow-medium` | NDCG@4 0.969918 | NDCG@4 0.922445 | Owner 승인 3/3 | [열기](experiments/cmq-v2-20260816-014214-89cf4e66.md) |
| `cmq-v3-20260813-075147-6a618c72` | 2026-08-13T07:51:47+00:00 | v3.1 / review_required | 6 | 263 | `multilingual-e5-base/ratio-s0.250-m0.350/xgboost-shallow-medium` | NDCG@2 0.936115 | NDCG@2 0.887592 | [810개 선지](experiments/cmq-v3-20260813-075147-6a618c72-choice-review.md) | [열기](experiments/cmq-v3-20260813-075147-6a618c72.md) |
| `cmq-v2-20260815-094223-89cf4e66` | 2026-08-15T09:42:23.542191+00:00 | v2.2 / candidate | 6 | 198 | `bge-m3/semantic-conservative/xgboost-shallow-medium` | NDCG@4 0.969918 | NDCG@4 0.922445 | — | [열기](experiments/cmq-v2-20260815-094223-89cf4e66.md) |
| `cmq-v2-20260815-091940-f5531553` | 2026-08-15T09:19:40.344686+00:00 | v2.1 / superseded | 1/6 성공 | 18 | `tfidf-word-char/lexical-balanced/xgboost-shallow-medium` | NDCG@4 0.965142 | NDCG@4 0.928408 | — | [열기](experiments/cmq-v2-20260815-091940-f5531553.md) |
| `cmq-v2-20260812-143000-cad29ebe` | 2026-08-12T14:30:00.172536+00:00 | v2 / candidate | 6 | 198 | `multilingual-minilm-l12/lexical-balanced/xgboost-shallow-medium` | NDCG@4 0.971748 | NDCG@4 0.938259 | — | [열기](experiments/cmq-v2-20260812-143000-cad29ebe.md) |

`cmq-v2-20260815-091940-f5531553`은 로컬 임베딩 의존성 누락을 발견한 중간 실행이며, 6개 후보와 198개 조합을 모두 완료한 v2.2 실행이 이를 대체한다.

## 최신 전체 문항 preview

`cmq-v3-preview-20260813-141717-6a618c72`는 선택 실험을 고정한 뒤 135개 요소에 4문항씩 총 540문항을 모두 조합한 Admin 미반영 preview다.

- 선택 비율: lexical 40% / metadata 35% / semantic 25%
- 하드 게이트 실패: 0건
- 자동 통과: 497문항
- 레퍼런스·코퍼스 기반 소프트 예외: 43문항
- 앵커 문서빈도 기준: 출현 앵커 76개, nearest-rank p75 순위 57, p75 22개 요소
- [전체 문항](previews/cmq-v3-preview-20260813-141717-6a618c72-all-questions.md)
- [예외 검수 43문항](previews/cmq-v3-preview-20260813-141717-6a618c72-review-exceptions.md)
- [기준 수치·결과 보고서](previews/cmq-v3-preview-20260813-141717-6a618c72-report.md)

`cmq-v3-20260813-072509-6a618c72`와 `cmq-v3-20260813-073512-6a618c72`는 대상 개념명 노출 49건을 발견한 사전 실행이다. 최신 실험은 해당 문장을 후보 단계에서 제외해 출처·대상 개념명 노출을 모두 0건으로 만들었으며 앞선 두 실행을 대체한다.

## 수치 해석 주의

자동 검수 전 test 수치는 약지도 규칙 재현도이므로 실제 교육 품질이나 일반화 성능으로 해석하면 안 된다. 810개 선지 문서는 랭커 선택 당시의 중간 산출물이고, 검수 대상 수가 아니다. 최신 전체 v3 preview는 540문항을 먼저 완성한 뒤 레퍼런스 하드 게이트를 모두 통과시키고 소프트 예외 43문항만 검수 큐에 남겼으며 아직 Admin 문항은행에 반영하지 않았다. Admin 최신 v2.2 문항은행은 402문항 자동 통과, Owner 승인 3문항, 미확인·자동 차단 0문항이며 Owner 배치 승인과 14개 릴리스 게이트를 모두 통과해 `release_ready`가 되었다.
