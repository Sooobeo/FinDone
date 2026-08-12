# FinDone 개념형 모델 실험 기록

개념형 문항 모델은 2026-08-12에 v2 기준으로 초기화했다.

- 설계 기준: [개념형 5지선다 모델링 기준](CONCEPT_MCQ_MODELING_DESIGN.md)
- 문항 방향: `용어 → 설명 선택`
- 관계형 선지: 수식 기호 없이 증가·감소·비중·조건을 자연어로 설명
- 현재 상태: 새 실험 없음, 릴리스 불가

기존 `설명 → 용어 선택` 방식의 v1 실험 보고서, Admin 실험 이력, Owner 결정과 문항 수정 기록은 새 계약과 호환되지 않아 폐기했다. v1 지표와 승인 결과를 v2 기준선에 승계하지 않는다.

새 파이프라인이 구현되면 다음 명령으로 생성한 v2 실험만 이 디렉터리에 기록한다.

```bash
python tools/train_concept_question_model.py \
  --write-question-bank \
  --write-admin-report \
  --write-markdown-report
```

## 실험 이력

아직 등록된 v2 실험이 없다.

첫 실행은 `bootstrap_not_reviewed`에서 시작하며, 독립 사람 test와 Owner 배치 승인을 포함한 모든 게이트를 통과한 경우에만 `release_ready`로 전환한다.
