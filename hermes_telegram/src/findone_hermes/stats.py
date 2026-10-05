"""KST date-window statistics and evidence-backed review selection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .content import ContentRepository
from .state import StateStore, utc_time


KST = timezone(timedelta(hours=9), "Asia/Seoul")


@dataclass(frozen=True)
class StatisticsRow:
    key: str
    name: str
    first_wrong: int
    first_total: int
    review_wrong: int
    review_total: int

    @property
    def low_sample(self) -> bool:
        return self.first_total < 5


@dataclass(frozen=True)
class StatisticsSummary:
    days: int
    start_date: date
    end_date: date
    domain_id: str | None
    domains: tuple[StatisticsRow, ...]
    elements: tuple[StatisticsRow, ...]


class StatisticsService:
    def __init__(self, content: ContentRepository, state: StateStore):
        self.content = content
        self.state = state

    def _window_rows(self, user_id: int, days: int, now: datetime | None):
        if days not in (7,30):
            raise ValueError("Statistics window must be 7 or 30 days")
        end = utc_time(now).astimezone(KST).date()
        start = end-timedelta(days=days-1)
        # Calendar-day boundaries include every graded answer in the requested KST dates.
        cutoff = utc_time(now)
        rows = [row for row in self.state.answer_rows(user_id)
                if start <= datetime.fromisoformat(row["submitted_at"]).astimezone(KST).date() <= end
                and datetime.fromisoformat(row["submitted_at"]) <= cutoff]
        return start,end,rows

    def summary(self, user_id: int, days: int = 7, domain_id: str | None = None,
                now: datetime | None = None) -> StatisticsSummary:
        domain_id = domain_id.strip().upper() if domain_id else None
        domains = self.content.domains()
        if domain_id and domain_id not in {domain.domain_id for domain in domains}:
            raise ValueError("알 수 없는 분야 ID입니다.")
        start,end,rows = self._window_rows(user_id,days,now)
        grouped_domains: dict[str,list] = defaultdict(list)
        grouped_elements: dict[str,list] = defaultdict(list)
        for row in rows:
            if domain_id is None or row["domain_id"] == domain_id:
                grouped_domains[row["domain_id"]].append(row)
                grouped_elements[row["element_id"]].append(row)

        def calculate(key: str, name: str, selected: list) -> StatisticsRow:
            first = [row for row in selected if row["attempt_kind"] == "first"]
            review = [row for row in selected if row["attempt_kind"] == "review"]
            return StatisticsRow(key,name,sum(not row["correct"] for row in first),len(first),
                                 sum(not row["correct"] for row in review),len(review))

        domain_rows = tuple(calculate(domain.domain_id,domain.name,grouped_domains[domain.domain_id])
                            for domain in domains if domain_id is None or domain.domain_id == domain_id)
        element_rows = tuple(calculate(element.element_id,element.title,grouped_elements[element.element_id])
                             for element in self.content.elements(domain_id)) if domain_id else ()
        return StatisticsSummary(days,start,end,domain_id,domain_rows,element_rows)

    def review_question_ids(self, user_id: int, now: datetime | None = None) -> tuple[str,...]:
        _,_,rows = self._window_rows(user_id,7,now)
        grouped: dict[str,list] = defaultdict(list)
        for row in rows:
            grouped[row["question_id"]].append(row)
        eligible = []
        for question_id, attempts in grouped.items():
            wrong = sum(not row["correct"] for row in attempts)
            if wrong and self.content.question(question_id) is not None:
                eligible.append((question_id,attempts,wrong))
        eligible.sort(key=lambda item: (bool(item[1][-1]["correct"]),-item[2],
                                        -sum(row["attempt_kind"]=="first" and not row["correct"]
                                             for row in item[1]),item[0]))
        return tuple(item[0] for item in eligible)

    def weekly_report(self, user_id: int, now: datetime | None = None) -> str:
        summary = self.summary(user_id,7,now=now)
        _,_,rows = self._window_rows(user_id,7,now)
        lines = ["🗓️ FinDone | 주간 복습",
                 f"기간: {summary.start_date} ~ {summary.end_date} (KST)"]
        if not rows:
            return "\n".join(lines+["", "이번 주 채점 기록이 없습니다.",
                                    "판단할 표본이 아직 적습니다.", "", "ℹ️ 통계 안내",
                                    "미응답과 /skip은 오답률에 포함하지 않습니다."])
        lines.extend(["", "📊 분야별 기록"])
        for domain in summary.domains:
            if domain.first_total or domain.review_total:
                lines.extend(["", domain.name,
                              f"• {domain.key}: 첫 시도 {domain.first_total}문항 중 오답 {domain.first_wrong}개",
                              f"• 재도전 {domain.review_total}문항 중 오답 {domain.review_wrong}개"])
                if domain.low_sample:
                    lines.append("참고: 표본 부족")
        enough = {row.key for row in summary.domains if not row.low_sample}
        grouped: dict[str,list] = defaultdict(list)
        for row in rows:
            grouped[row["element_id"]].append(row)
        evidence = False
        lines.extend(["", "🔎 반복 오답"])
        for element_id, attempts in sorted(grouped.items()):
            wrong = sum(not row["correct"] for row in attempts)
            if attempts[0]["domain_id"] in enough and wrong >= 2:
                lines.append(f"• {element_id}: 채점 {len(attempts)}회 중 오답 {wrong}회로 반복 오답이 기록되었습니다.")
                evidence = True
        if not enough:
            lines.extend(["판단할 표본이 아직 적습니다.",
                          "위 수치는 실제 채점 기록이며 분야의 약점으로 단정하지 않습니다."])
        elif not evidence:
            lines.append("이번 주 기록에서 반복 오답 요소를 확정할 근거가 부족합니다.")
        by_question: dict[str,list] = defaultdict(list)
        for row in rows:
            by_question[row["question_id"]].append(row)
        improved: dict[str,int] = defaultdict(int)
        unresolved: dict[str,int] = defaultdict(int)
        for attempts in by_question.values():
            latest = attempts[-1]
            if latest["attempt_kind"] == "review" and any(not row["correct"] for row in attempts[:-1]):
                (improved if latest["correct"] else unresolved)[latest["element_id"]] += 1
        if improved or unresolved:
            lines.extend(["", "🔁 재도전 결과"])
        for element_id,count in sorted(improved.items()):
            lines.append(f"• {element_id}: 앞서 틀린 문항 {count}개를 최근 재도전에서 맞혔습니다.")
        for element_id,count in sorted(unresolved.items()):
            lines.append(f"• {element_id}: 최근 재도전에서도 문항 {count}개를 틀렸습니다.")
        ids = self.review_question_ids(user_id,now=now)
        seen_elements: set[str] = set()
        for question_id in ids:
            question = self.content.question(question_id)
            assert question is not None
            element = self.content.element(question.element_id)
            if element and element.element_id not in seen_elements and len(seen_elements) < 2:
                if not seen_elements:
                    lines.extend(["", "📖 짧은 복습"])
                lines.extend(["", f"{element.element_id} · {element.title}", element.definition])
                seen_elements.add(element.element_id)
        lines.extend(["", "ℹ️ 통계 안내",
                      "미응답과 /skip은 오답률에 포함하지 않습니다.",
                      "/stats로 7일·30일 통계를 볼 수 있습니다."])
        return "\n".join(lines)
