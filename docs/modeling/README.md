# FinDone 개념형 모델 실험 기록

이 디렉터리는 오프라인 개념형 5지선다 모델링 실험의 사람이 읽을 수 있는 영구 기록이다.
Admin 시각화는 `admin/data/concept-model-experiments.generated.json`을 사용하고, 이 MD들은 감사·비교·의사결정 이력으로 유지한다.

- 설계 기준: [개념형 5지선다 오프라인 모델링 설계서](CONCEPT_MCQ_MODELING_DESIGN.md)
- 생성 명령: `python tools/train_concept_question_model.py --write-question-bank --write-admin-report --write-markdown-report`
- 원칙: validation으로 조합을 선택하고 선택된 한 조합에만 test를 실행한다.

| 실험 | 시각 | 상태 | 후보 임베딩 | 실행 조합 | 선택 구성 | val NDCG@4 | test NDCG@4 | 사람 test | 보고서 |
|---|---|---|---:|---:|---|---:|---:|---:|---|
| `cmq-20260812-121810-c1670dca` | 2026-08-12T12:18:10.690640+00:00 | candidate | 1 | 18 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.952131 | 0.946206 | 0.00% | [열기](experiments/cmq-20260812-121810-c1670dca.md) |
| `cmq-20260812-112232-c1670dca` | 2026-08-12T11:22:32.903484+00:00 | candidate | 1 | 18 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.952131 | 0.946206 | 0.00% | [열기](experiments/cmq-20260812-112232-c1670dca.md) |
| `cmq-20260812-105741-c1670dca` | 2026-08-12T10:57:41.716359+00:00 | candidate | 1 | 18 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.952131 | 0.946206 | 0.00% | [열기](experiments/cmq-20260812-105741-c1670dca.md) |
| `cmq-20260812-024142-c1670dca` | 2026-08-12T02:41:42.456509+00:00 | candidate | 1 | 18 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.952131 | 0.946206 | 0.00% | [열기](experiments/cmq-20260812-024142-c1670dca.md) |
| `cmq-20260812-023828-f5ddcfa8` | 2026-08-12T02:38:28.927639+00:00 | candidate | 1 | 18 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.952131 | 0.946206 | 0.00% | [열기](experiments/cmq-20260812-023828-f5ddcfa8.md) |
| `cmq-20260812-023650-deb21718` | 2026-08-12T02:36:50.539025+00:00 | candidate | 1 | 18 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.952131 | 0.946206 | 0.00% | [열기](experiments/cmq-20260812-023650-deb21718.md) |
| `cmq-20260812-023353-deb21718` | 2026-08-12T02:33:53.923396+00:00 | candidate | 1 | 18 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.954588 | 0.940171 | 0.00% | [열기](experiments/cmq-20260812-023353-deb21718.md) |
| `cmq-20260811-161640-1cbc8db8` | 2026-08-11T16:16:40.720779+00:00 | bootstrap | 1 | 18 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.954588 | 0.940171 | 0.00% | [열기](experiments/cmq-20260811-161640-1cbc8db8.md) |
| `cmq-20260811-160027-1cbc8db8` | 2026-08-11T16:00:27.901739+00:00 | bootstrap | 2 | 54 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.954588 | 0.940171 | 0.00% | [열기](experiments/cmq-20260811-160027-1cbc8db8.md) |
| `cmq-20260811-154900-1ffa4d0f` | 2026-08-11T15:49:00.783673+00:00 | bootstrap | 2 | 54 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.954588 | 0.940171 | 0.00% | [열기](experiments/cmq-20260811-154900-1ffa4d0f.md) |
| `cmq-20260811-143326-1ffa4d0f` | 2026-08-11T14:33:26.440647+00:00 | bootstrap | 2 | 54 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.954588 | 0.940171 | 0.00% | [열기](experiments/cmq-20260811-143326-1ffa4d0f.md) |
| `cmq-20260811-141533-1ffa4d0f` | 2026-08-11T14:15:33.215236+00:00 | bootstrap | 1 | 18 | `tfidf-word-char/lexical-char-heavy/xgboost-reference-default` | 0.954588 | 0.940171 | 0.00% | [열기](experiments/cmq-20260811-141533-1ffa4d0f.md) |
| `cmq-20260811-140731-1ffa4d0f` | 2026-08-11T14:07:31.113679+00:00 | bootstrap | 3 | 90 | `tfidf-word-char/lexical-balanced/xgboost-shallow-slow` | 0.947753 | 0.918011 | 0.00% | [열기](experiments/cmq-20260811-140731-1ffa4d0f.md) |
| `cmq-20260811-140618-1ffa4d0f` | 2026-08-11T14:06:18.441378+00:00 | bootstrap | 1 | 18 | `tfidf-word-char/lexical-balanced/xgboost-shallow-slow` | 0.947753 | 0.918011 | 0.00% | [열기](experiments/cmq-20260811-140618-1ffa4d0f.md) |
| `cmq-20260811-130548-423cc40f` | 2026-08-11T13:05:48.793839+00:00 | bootstrap | 3 | 90 | `tfidf-word-char/lexical-balanced/xgboost-shallow-medium` | 0.940005 | 0.942921 | 0.00% | [열기](experiments/cmq-20260811-130548-423cc40f.md) |
| `cmq-20260811-130417-423cc40f` | 2026-08-11T13:04:17.604115+00:00 | bootstrap | 1 | 18 | `tfidf-word-char/lexical-balanced/xgboost-shallow-medium` | 0.940005 | 0.942921 | 0.00% | [열기](experiments/cmq-20260811-130417-423cc40f.md) |

## 수치 해석 주의

자동 검수 전 test 수치는 약지도 규칙 재현도이므로 실제 교육 품질이나 일반화 성능으로 해석하면 안 된다. 자동 검수 차단 0건, 예외 확인 완료, Owner 배치 승인과 모든 릴리스 게이트를 통과한 실험만 `release_ready`가 될 수 있다.
