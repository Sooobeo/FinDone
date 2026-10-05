"""Plain-text Telegram messages and conservative length splitting."""

from __future__ import annotations

import re

from .state import GradeResult, QuizBatch
from .stats import StatisticsRow, StatisticsSummary


def format_notice(title: str, *paragraphs: str) -> str:
    return "\n\n".join((title, *paragraphs))


def format_explanation(ordinal: int, explanation: str) -> str:
    return format_notice(f"💡 {ordinal}번 · 추가 설명", explanation, "/stats — 최근 학습 통계")


def format_quiz(batch: QuizBatch) -> str:
    blocks = [f"📝 FinDone · {'복습 퀴즈' if batch.kind == 'review' else '오늘의 퀴즈'}\n"
              f"총 {len(batch.items)}문항"]
    shown = set()
    for item in batch.items:
        if item.element_id not in shown:
            blocks.append(f"📘 개념 · {item.element_id} {item.concept_title}\n{item.definition}")
            if item.intuition:
                blocks.append(f"💡 쉽게 이해하기\n{item.intuition}")
            shown.add(item.element_id)
        blocks.append(f"❓ Q{item.ordinal}.\n{item.stem}")
        blocks.append("\n\n".join(f"{choice.number}) {choice.text}" for choice in item.choices))
    example = ",".join("1" for _ in batch.items)
    blocks.extend([
        "✍️ 답장 방법\n문항 순서대로 선택지 번호(1~5)를 쉼표로 구분해 보내 주세요.\n"
        f"예시: {example}",
        "/skip — 이번 회차 건너뛰기\n/help — 도움말",
        f"회차 ID: {batch.batch_id}",
    ])
    return "\n\n".join(blocks)


def format_grade(result: GradeResult) -> str:
    if result.duplicate:
        return ("↩️ 이미 채점한 회차입니다.\n기록을 추가하지 않았습니다.\n\n"
                f"회차 ID: {result.batch.batch_id}")
    correct = sum(answer.correct for answer in result.answers)
    blocks = [f"📋 FinDone · 채점 결과\n정답 {correct}/{len(result.batch.items)}문항"]
    for item,answer in zip(result.batch.items,result.answers):
        verdict = "✅ 정답" if answer.correct else "❌ 오답"
        attempt = "첫 시도" if answer.attempt_kind == "first" else "재도전"
        blocks.append(f"{verdict} · {item.ordinal}번 · {attempt}\n"
                      f"내 답: {answer.chosen_number}번 · 정답: {item.correct_number}번\n\n"
                      f"📖 해설\n{item.explanation}")
        chosen = next(choice for choice in item.choices if choice.number == answer.chosen_number)
        if not answer.correct:
            blocks.append("💡 고른 선택지 해설\n" + chosen.explanation)
    ordinal = min(2, len(result.batch.items))
    blocks.extend([
        f"🔎 더 알아보기\n/why {ordinal} — {ordinal}번 문항 추가 설명\n/stats — 최근 학습 통계",
        f"회차 ID: {result.batch.batch_id}",
    ])
    return "\n\n".join(blocks)


def _counts(row: StatisticsRow) -> str:
    def rate(wrong: int, total: int) -> str:
        return f"채점 {total}문항 · 오답 {wrong}개" + (f" ({wrong/total:.0%})" if total else " · 기록 없음")
    return f"첫 시도: {rate(row.first_wrong,row.first_total)}\n재도전: {rate(row.review_wrong,row.review_total)}"


def format_stats(summary: StatisticsSummary) -> str:
    blocks = [f"📊 FinDone · 최근 {summary.days}일 통계\n"
              f"{summary.start_date} ~ {summary.end_date} (한국 시간)"]
    for row in summary.domains:
        blocks.append(f"{row.key} · {row.name}\n{_counts(row)}" + ("\n🔎 표본 부족" if row.low_sample else ""))
    if summary.elements:
        blocks.append("📌 요소별 기록\n적은 표본의 비율만으로 약점을 단정하지 않습니다.")
        blocks.extend(f"{row.key} · {row.name}\n{_counts(row)}" for row in summary.elements)
    blocks.append("ℹ️ 통계 안내\n미응답과 /skip은 제외합니다.\n"
                  "첫 시도 5문항 미만인 분야는 표본 부족으로 표시합니다.")
    return "\n\n".join(blocks)


def format_help() -> str:
    return ("📚 FinDone · 도움말\n\n"
            "✍️ 퀴즈 답장\n문항 순서대로 1~5 숫자를 쉼표로 구분해 보내 주세요.\n"
            "예시: 2,4 (2문항일 때)\n"
            "번호는 이번에 발송된 선택지 순서입니다.\n회차당 한 번만 채점합니다.\n\n"
            "📊 학습 통계\n/stats — 최근 7일·30일 분야별 통계\n/stats FI — FI 요소별 통계\n\n"
            "🔁 해설과 복습\n/why 2 — 가장 최근 채점 회차의 2번 해설\n"
            "/review — 최근 기록에 따른 복습\n\n"
            "⏭️ 건너뛰기\n/skip — 진행 중인 회차 건너뛰기\n\n"
            "ℹ️ 미응답 회차는 자동 만료되지 않습니다.\n먼저 답하거나 /skip을 입력해 주세요.")


def _units(text: str) -> int:
    return len(text.encode("utf-16-le"))//2


def split_message(text: str, limit: int = 4000) -> list[str]:
    if not isinstance(text,str) or not 64 <= limit <= 4096:
        raise ValueError("Message limit must be between 64 and 4096")
    if _units(text) <= limit:
        return [text] if text else []
    match = re.search(r"(?m)^회차 ID: ([0-9a-fA-F-]{32,36})\s*$",text)
    prefix = f"회차 ID: {match.group(1)}\n\n" if match else ""
    remaining = text
    chunks = []
    while remaining:
        budget = limit-_units(prefix)
        used = 0
        end = 0
        for character in remaining:
            width = _units(character)
            if used+width > budget:
                break
            used += width
            end += 1
        if end < len(remaining):
            paragraph = remaining.rfind("\n\n", 0, end)
            if paragraph > end//2:
                end = paragraph+2
            else:
                newline = remaining.rfind("\n",0,end)
                if newline > end//2:
                    end = newline+1
        piece,remaining = remaining[:end],remaining[end:]
        chunks.append(prefix+piece)
    return chunks
