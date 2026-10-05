"""Authenticated deterministic reply handling, called by the Hermes hook."""
from __future__ import annotations

from .config import Settings, is_allowed
from .content import ContentRepository
from .messages import (
    format_explanation, format_grade, format_help, format_notice,
    format_quiz, format_stats, split_message,
)
from .quiz import QuizService
from .state import StateStore
from .stats import StatisticsService


def handle_message(platform: str, user_id: str, chat_id: str, chat_type: str,
                   text: str, *, submission_id: str | None = None,
                   batch_id: str | None = None) -> list[str]:
    if not is_allowed(platform, user_id, chat_id, chat_type):
        return []
    user_id, chat_id = int(user_id), int(chat_id)
    content = state = None
    try:
        settings = Settings.from_env()
        content = ContentRepository(settings.content_db, settings.content_manifest)
        state = StateStore(settings.state_db)
        quiz = QuizService(content, state)
        stats = StatisticsService(content, state)
        words = text.strip().split()
        command = words[0].split("@", 1)[0].lower() if words else ""
        if command in {"/help", "/start"}:
            response = format_help()
        elif command == "/skip" and len(words) == 1:
            skipped = quiz.skip(user_id, chat_id, submission_id=submission_id, batch_id=batch_id)
            response = (format_notice("⏭️ 활성 회차를 건너뛰었습니다.", "다음 예약 퀴즈를 받을 수 있습니다.")
                        if skipped else format_notice("ℹ️ 건너뛸 활성 회차가 없습니다.", "/help — 도움말"))
        elif command == "/stats" and len(words) <= 2:
            domain = words[1].upper() if len(words) == 2 else None
            if domain and domain not in {d.domain_id for d in content.domains()}:
                response = format_notice("🔎 분야 ID를 확인해 주세요.",
                                         "사용 가능한 분야: " + ", ".join(d.domain_id for d in content.domains()),
                                         "예시: /stats FI")
            else:
                response = "\n\n".join(format_stats(stats.summary(user_id, days=days, domain_id=domain)) for days in (7, 30))
        elif command == "/review" and len(words) == 1:
            active = state.active_batch(user_id, chat_id)
            if active:
                response = format_notice("⏳ 미완료 회차가 있습니다.",
                                         "아래 문제를 먼저 풀거나 /skip 후 /review를 입력해 주세요.",
                                         format_quiz(active))
            else:
                batch = quiz.create_review(user_id, chat_id)
                if batch:
                    state.mark_batch_delivery(batch.batch_id)
                response = format_quiz(batch) if batch else format_notice(
                    "🌱 아직 복습을 준비할 기록이 부족합니다.",
                    "판단할 표본이 아직 적습니다.\n채점 기록을 쌓은 뒤 /review를 이용해 주세요.")
        elif command == "/why" and len(words) == 2 and words[1].isdigit():
            recent = quiz.most_recent_graded(user_id, chat_id)
            ordinal = int(words[1])
            if recent is None or not 1 <= ordinal <= len(recent.items):
                response = format_notice("🔎 문항 번호를 확인해 주세요.",
                                         "가장 최근 채점 회차의 문항 번호를 입력해 주세요.",
                                         "예시: /why 2")
            else:
                item = recent.items[ordinal - 1]
                explanation = item.explanation
                try:
                    from .model import model_from_env
                    model = model_from_env()
                    if model:
                        explanation = model.explain(item.stem, [choice.text for choice in item.choices], item.correct_number, item.explanation)
                except Exception:
                    # Static snapshot explanation stays available if a model fails.
                    pass
                response = format_explanation(ordinal, explanation)
        elif command.startswith("/"):
            response = format_help()
        else:
            try:
                result = quiz.submit(user_id, chat_id, text, submission_id=submission_id, batch_id=batch_id)
                response = format_grade(result)
            except ValueError:
                active = state.active_batch(user_id, chat_id)
                response = (format_notice(
                    "✍️ 답장 형식을 확인해 주세요.",
                    f"이번 회차는 {len(active.items)}문항입니다.\n각 답을 1~5 사이 숫자로 쉼표로 구분해 주세요.",
                    "예시: " + ",".join("1" for _ in active.items))
                    if active else format_notice("ℹ️ 활성 퀴즈가 없습니다.",
                                                  "다음 예약 퀴즈를 기다려 주세요.", "/help — 도움말"))
        return split_message(response)
    except Exception:
        return [format_notice("⚠️ FinDone 처리 중 운영 오류가 발생했습니다.",
                              "답안은 다시 전송할 수 있습니다.",
                              "운영 로그와 콘텐츠·설정을 확인해 주세요.")]
    finally:
        if state is not None:
            state.close()
        if content is not None:
            content.close()
