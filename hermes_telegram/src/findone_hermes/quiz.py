"""Selection, shuffled snapshots, and idempotent all-or-nothing grading."""

from __future__ import annotations

from datetime import datetime
import random
import re
from uuid import uuid4

from .content import ContentRepository, Question
from .state import (ChoiceSnapshot, GradeResult, QuizBatch, QuizItem, StateStore,
                    timestamp)


class AnswerFormatError(ValueError):
    pass


class NoActiveQuizError(ValueError):
    pass


class QuizService:
    def __init__(self, content: ContentRepository, state: StateStore,
                 rng: random.Random | None = None):
        self.content = content
        self.state = state
        self.rng = rng or random.SystemRandom()

    def _snapshot(self, question: Question, ordinal: int) -> QuizItem:
        element = self.content.element(question.element_id)
        if element is None:
            raise ValueError("Question concept is missing")
        choices = list(question.choices)
        self.rng.shuffle(choices)
        displayed = tuple(ChoiceSnapshot(number,choice.key,choice.text,choice.explanation)
                          for number, choice in enumerate(choices, 1))
        correct = next(number for number, choice in enumerate(choices, 1) if choice.is_correct)
        return QuizItem(ordinal,question.domain_id,question.element_id,question.question_id,
                        element.title,element.definition,element.intuition,question.stem,
                        question.explanation,displayed,correct)

    def _activate(self, user_id: int, chat_id: int, kind: str, questions: list[Question],
                  now: datetime | None) -> QuizBatch:
        batch = QuizBatch(uuid4().hex,user_id,chat_id,kind,"active",timestamp(now),None,
                          "pending",self.content.manifest["contentDbVersion"],
                          tuple(self._snapshot(question,index) for index, question in enumerate(questions,1)))
        self.state.insert_batch(batch)
        return batch

    def _check_existing(self, user_id: int, chat_id: int) -> QuizBatch | None:
        batch = self.state.active_batch(user_id,chat_id)
        if batch is not None:
            return batch
        occupied = self.state.connection.execute("""SELECT 1 FROM quiz_batches
            WHERE status='active' AND (user_id=? OR chat_id=?) LIMIT 1""", (user_id,chat_id)).fetchone()
        if occupied:
            raise ValueError("Another chat already has an active quiz")
        return None

    def create_regular(self, user_id: int, chat_id: int, count: int = 2,
                       now: datetime | None = None) -> QuizBatch:
        if type(count) is not int or not 1 <= count <= 4:
            raise ValueError("Quiz count must be between 1 and 4")
        with self.state.transaction():
            existing = self._check_existing(user_id,chat_id)
            if existing:
                return existing
            seen = self.state.seen_question_ids(user_id)
            by_element: dict[str, list[Question]] = {}
            for question in self.content.questions():
                by_element.setdefault(question.element_id, []).append(question)
            if not by_element:
                raise ValueError("No eligible questions")
            domain_counts = dict(self.state.connection.execute("""SELECT i.domain_id,COUNT(DISTINCT b.batch_id)
                FROM quiz_items i JOIN quiz_batches b ON b.batch_id=i.batch_id
                WHERE b.user_id=? AND b.kind='regular' GROUP BY i.domain_id""", (user_id,)))
            # Prefer an unseen element in the least-used domain. Within it, use unseen questions first.
            candidates = [element_id for element_id,questions in by_element.items() if len(questions) >= count]
            if not candidates:
                candidates = list(by_element)
            self.rng.shuffle(candidates)
            candidates.sort(key=lambda element_id: (
                all(question.question_id in seen for question in by_element[element_id]),
                domain_counts.get(by_element[element_id][0].domain_id,0),
                -sum(question.question_id not in seen for question in by_element[element_id])))
            selected = list(by_element[candidates[0]])
            self.rng.shuffle(selected)
            selected.sort(key=lambda question: question.question_id in seen)
            selected = selected[:count]
            # v7 has three questions per concept; a configured count of four adds a nearby concept.
            if len(selected) < count:
                remainder = [question for question in self.content.questions() if question not in selected]
                self.rng.shuffle(remainder)
                remainder.sort(key=lambda question: (question.domain_id != selected[0].domain_id,
                                                     question.question_id in seen))
                selected.extend(remainder[:count-len(selected)])
            if len(selected) != count:
                raise ValueError("Not enough eligible questions for this quiz")
            return self._activate(user_id,chat_id,"regular",selected,now)

    def create_review(self, user_id: int, chat_id: int, count: int = 3,
                      now: datetime | None = None) -> QuizBatch | None:
        if type(count) is not int or not 2 <= count <= 3:
            raise ValueError("Review count must be 2 or 3")
        from .stats import StatisticsService
        with self.state.transaction():
            existing = self._check_existing(user_id,chat_id)
            if existing:
                return existing
            ids = StatisticsService(self.content,self.state).review_question_ids(user_id,now=now)
            selected = [self.content.question(question_id) for question_id in ids]
            selected = [question for question in selected if question is not None][:count]
            if not selected:
                return None
            if len(selected) < count:
                elements = {question.element_id for question in selected}
                related = [question for question in self.content.questions()
                           if question.element_id in elements and question not in selected]
                self.rng.shuffle(related)
                selected.extend(related[:count-len(selected)])
            if len(selected) < count:
                other = [question for question in self.content.questions() if question not in selected]
                self.rng.shuffle(other)
                selected.extend(other[:count-len(selected)])
            if len(selected) < 2:
                return None
            return self._activate(user_id,chat_id,"review",selected,now)

    @staticmethod
    def _parse(text: str, count: int) -> tuple[int, ...]:
        if not isinstance(text,str) or not re.fullmatch(r"\s*[1-5](?:\s*,\s*[1-5])*\s*",text):
            raise AnswerFormatError("답장은 1~5 숫자를 쉼표로 구분하세요. 예: 2,4")
        answers = tuple(int(token.strip()) for token in text.split(","))
        if len(answers) != count:
            raise AnswerFormatError(f"이 회차는 {count}문항입니다. 숫자 {count}개를 입력하세요.")
        return answers

    def submit(self, user_id: int, chat_id: int, text: str,
               now: datetime | None = None, batch_id: str | None = None,
               submission_id: str | None = None) -> GradeResult:
        with self.state.transaction() as c:
            if submission_id is not None:
                old = c.execute("""SELECT batch_id FROM submissions
                    WHERE user_id=? AND chat_id=? AND submission_id=?""",
                    (user_id,chat_id,str(submission_id))).fetchone()
                if old:
                    previous = self.state.batch(old[0])
                    assert previous is not None
                    return GradeResult(previous,self.state.graded_answers(previous.batch_id),True)
            batch = self.state.batch(batch_id) if batch_id else self.state.active_batch(user_id,chat_id)
            if batch is None and batch_id is None:
                batch = self.state.latest_graded(user_id,chat_id)
            if batch is None or batch.user_id != user_id or batch.chat_id != chat_id:
                raise NoActiveQuizError("진행 중인 퀴즈가 없습니다. 다음 예약 발송을 기다려 주세요.")
            chosen = self._parse(text,len(batch.items))
            if batch.status == "graded":
                return GradeResult(batch,self.state.graded_answers(batch.batch_id),True)
            if batch.status != "active":
                raise NoActiveQuizError("건너뛴 회차는 채점할 수 없습니다.")
            submitted_at = timestamp(now)
            for item, number in zip(batch.items,chosen):
                previous = c.execute("""SELECT 1 FROM answers a JOIN quiz_items i
                    ON i.batch_id=a.batch_id AND i.ordinal=a.ordinal
                    WHERE a.user_id=? AND i.question_id=? LIMIT 1""",
                    (user_id,item.question_id)).fetchone()
                c.execute("""INSERT INTO answers
                    (batch_id,ordinal,user_id,chosen_number,correct,submitted_at,attempt_kind)
                    VALUES (?,?,?,?,?,?,?)""", (batch.batch_id,item.ordinal,user_id,number,
                    int(number==item.correct_number),submitted_at,"review" if previous else "first"))
            c.execute("UPDATE quiz_batches SET status='graded' WHERE batch_id=?", (batch.batch_id,))
            if submission_id is not None:
                c.execute("INSERT INTO submissions VALUES (?,?,?,?)",
                          (user_id,chat_id,str(submission_id),batch.batch_id))
            graded = self.state.batch(batch.batch_id)
            assert graded is not None
            return GradeResult(graded,self.state.graded_answers(batch.batch_id))

    def skip(self, user_id: int, chat_id: int, now: datetime | None = None,
             batch_id: str | None = None, submission_id: str | None = None) -> QuizBatch | None:
        with self.state.transaction() as c:
            if submission_id is not None:
                old = c.execute("""SELECT batch_id FROM submissions
                    WHERE user_id=? AND chat_id=? AND submission_id=?""",
                    (user_id,chat_id,str(submission_id))).fetchone()
                if old:
                    previous = self.state.batch(old[0])
                    return previous if previous is not None and previous.status == "skipped" else None
            batch = self.state.batch(batch_id) if batch_id else self.state.active_batch(user_id,chat_id)
            if batch is None:
                return None
            if batch.user_id != user_id or batch.chat_id != chat_id:
                raise ValueError("This quiz belongs to another chat")
            if batch.status == "skipped":
                return batch
            if batch.status != "active":
                return None
            c.execute("UPDATE quiz_batches SET status='skipped' WHERE batch_id=?", (batch.batch_id,))
            if submission_id is not None:
                c.execute("INSERT INTO submissions VALUES (?,?,?,?)",
                          (user_id,chat_id,str(submission_id),batch.batch_id))
            return self.state.batch(batch.batch_id)

    def most_recent_graded(self, user_id: int, chat_id: int) -> QuizBatch | None:
        return self.state.latest_graded(user_id,chat_id)
