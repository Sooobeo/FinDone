# FinDone 개념형 모델 실험 기록

이 디렉터리는 오프라인 개념형 5지선다 모델링 실험의 사람이 읽을 수 있는 영구 기록이다.
Admin 시각화는 `admin/data/concept-model-experiments.generated.json`을 사용하고, 이 MD들은 감사·비교·의사결정 이력으로 유지한다.

- 설계 기준: [개념형 5지선다 오프라인 모델링 설계서](CONCEPT_MCQ_MODELING_DESIGN.md)
- 생성 명령: `python tools/train_concept_question_model.py --all-embeddings --ranker all --write-question-bank --write-admin-report --write-markdown-report`
- 원칙: validation으로 조합을 선택하고 선택된 한 조합에만 test를 실행한다.

| 실험 | 시각 | 상태 | 후보 임베딩 | 실행 조합 | 선택 구성 | val NDCG@4 | test NDCG@4 | 사람 test | 보고서 |
|---|---|---|---:|---:|---|---:|---:|---:|---|
| `cmq-v2-20260812-143000-cad29ebe` | 2026-08-12T14:30:00.172536+00:00 | candidate | 6 | 198 | `multilingual-minilm-l12/lexical-balanced/xgboost-shallow-medium` | 0.971748 | 0.938259 | 0.00% | [열기](experiments/cmq-v2-20260812-143000-cad29ebe.md) |

## 수치 해석 주의

자동 검수 전 test 수치는 약지도 규칙 재현도이므로 실제 교육 품질이나 일반화 성능으로 해석하면 안 된다. 자동 검수 차단 0건, 예외 확인 완료, Owner 배치 승인과 모든 릴리스 게이트를 통과한 실험만 `release_ready`가 될 수 있다.
