"""Script-only cron entrypoint. Stdout is reserved for Telegram delivery."""
from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta, timezone
import json
import sys

from .config import Settings, content_paths
from .content import ContentRepository
from .messages import format_notice, format_quiz, split_message
from .quiz import QuizService
from .presentation import hermes_markdown
from .state import StateStore
from .stats import StatisticsService

KST = timezone(timedelta(hours=9), "Asia/Seoul")


def slot_is_due(kind: str, slot: str, now: datetime) -> bool:
    """Permit only scheduled slots within a bounded 30 minute grace window."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Scheduled job clock must include a timezone")
    local = now.astimezone(KST)
    if kind == "news":
        valid = slot == "08:00"
    elif kind == "regular":
        valid = slot in {"12:30", "20:30"}
    else:
        valid = kind == "review" and slot == "20:30" and local.weekday() == 6
    if not valid:
        return False
    planned = datetime.combine(local.date(), time.fromisoformat(slot), KST)
    return timedelta(0) <= local - planned <= timedelta(minutes=30)


def run_job(kind: str, slot: str, settings: Settings, *, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(KST)
    if not slot_is_due(kind, slot, now):
        return []
    local = now.astimezone(KST)
    learner_id = int(settings.user_id)
    # Sunday evening is one replacement job even if two wrappers are configured.
    job_kind = "review" if kind == "regular" and slot == "20:30" and local.weekday() == 6 else kind
    content = ContentRepository(settings.content_db, settings.content_manifest)
    state = None
    try:
        state = StateStore(settings.state_db)
        date_key = local.date().isoformat()
        if not state.claim_job(learner_id, job_kind, date_key, slot, now=now):
            return []
        try:
            quiz = QuizService(content, state) if job_kind != "news" else None
            batch = None
            if job_kind == "news":
                from .model import model_from_env
                from .news import NewsService, render_news
                from .news_now import reserve_news_result
                result = NewsService(content, state, model=model_from_env()).prepare(learner_id, now=now)
                result = reserve_news_result(state, learner_id, result, now=now)
                response = render_news(result)
            elif job_kind == "review":
                response = StatisticsService(content, state).weekly_report(learner_id, now=now)
                active = state.active_batch(learner_id, learner_id)
                if active:
                    response += "\n\n" + format_notice(
                        "⏸️ 복습 퀴즈 대기",
                        "미완료 회차가 있어 복습 문제는 보류했습니다.\n"
                        "기존 회차를 마치거나 /skip 후 /review를 입력해 주세요.")
                else:
                    batch = quiz.create_review(learner_id, learner_id, now=now)
                    if batch:
                        response += "\n\n" + format_quiz(batch)
            else:
                active = state.active_batch(learner_id, learner_id)
                if active:
                    response = format_notice(
                        "⏳ 미완료 퀴즈가 있습니다.",
                        "기존 문제에 답장하거나 /skip을 입력해 주세요.",
                        "전송이 확인되지 않는 회차는 운영 기록을 확인해 주세요.",
                        f"회차 ID: {active.batch_id}")
                else:
                    batch = quiz.create_regular(learner_id, learner_id, count=settings.quiz_count, now=now)
                    response = format_quiz(batch)
            # Reserve before stdout. Hermes owns network dispatch and cannot atomically
            # acknowledge delivery to this DB; interrupted handoffs are never retried.
            if batch:
                state.mark_batch_delivery(batch.batch_id, status="emitted", now=now)
            state.finish_job(learner_id, job_kind, date_key, slot, status="emitted", now=now)
            return split_message(response)
        except Exception:
            state.finish_job(learner_id, job_kind, date_key, slot, status="failed", error_code="job_processing_failed", now=now)
            raise
    finally:
        if state is not None:
            state.close()
        content.close()


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-content", help="Read-only validation, no credentials or state")
    sub.add_parser("preview", help="Print two real questions and answer keys without recording")
    for kind in ("regular", "review", "news"):
        command = sub.add_parser(kind)
        command.add_argument("--slot", required=True, choices=("08:00", "12:30", "20:30"))
    args = parser.parse_args(argv)
    try:
        if args.command in {"validate-content", "preview"}:
            db, manifest = content_paths()
            content = ContentRepository(db, manifest)
            try:
                if args.command == "validate-content":
                    print(json.dumps({"valid": True, "contentDbVersion": content.manifest["contentDbVersion"], "eligibleQuestions": len(content.questions())}))
                else:
                    for question in content.questions()[:2]:
                        element = content.element(question.element_id)
                        print(f"\n{question.question_id} | {element.title}\n{question.stem}")
                        for choice in question.choices:
                            print(f"{choice.key}. {choice.text}")
                        print("정답: " + next(choice.key for choice in question.choices if choice.is_correct))
                        print("해설: " + question.explanation)
            finally:
                content.close()
            return 0
        for message in run_job(args.command, args.slot, Settings.from_env()):
            print(hermes_markdown(message))
        return 0
    except Exception:
        # Exception strings may include URLs, local paths, secrets or identifiers.
        print("FinDone job failed: check local configuration, content validation and job_runs; automatic replay is disabled.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
