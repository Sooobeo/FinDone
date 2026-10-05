from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

from findone_hermes.content import ContentIntegrityError, ContentRepository
from findone_hermes.messages import format_grade, format_quiz, format_stats, split_message
from findone_hermes.quiz import AnswerFormatError, NoActiveQuizError, QuizService
from findone_hermes.state import StateStore
from findone_hermes.stats import KST, StatisticsService


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/"app"/"src"/"main"/"assets"
NOW = datetime(2026,10,3,12,30,tzinfo=KST)


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="findone-learning-")
        self.directory = Path(self.temporary.name)
        self.content = ContentRepository(ASSETS/"content.sqlite3",ASSETS/"content-manifest.json")
        self.state = StateStore(self.directory/"learning.sqlite3")
        self.quiz = QuizService(self.content,self.state,random.Random(8))
        self.stats = StatisticsService(self.content,self.state)

    def tearDown(self):
        self.state.close()
        self.content.close()
        self.temporary.cleanup()

    def answer_text(self,batch,correct=True):
        return ",".join(str(item.correct_number if correct else item.correct_number%5+1) for item in batch.items)

    def activate(self,questions,kind="regular",now=NOW):
        with self.state.transaction():
            return self.quiz._activate(101,101,kind,list(questions),now)

    def test_actual_content_matches_android_eligible_loader(self):
        self.assertEqual(7,len(self.content.domains()))
        self.assertEqual(135,len(self.content.elements()))
        self.assertEqual(405,len(self.content.questions()))
        c = self.content.connection
        self.assertEqual({row[0] for row in c.execute("""SELECT question_id FROM concept_questions
            WHERE review_status IN ('automated_pass','owner_approved')""")},
            {item.question_id for item in self.content.questions()})
        for question in self.content.questions():
            self.assertEqual(set("ABCDE"),{choice.key for choice in question.choices})
            self.assertEqual(1,sum(choice.is_correct for choice in question.choices))
            self.assertTrue(question.explanation)
        with self.assertRaises(sqlite3.OperationalError):
            c.execute("DELETE FROM concept_questions")

    def test_snapshot_shuffle_restart_and_duplicate_answer(self):
        batch = self.quiz.create_regular(101,101,now=NOW)
        self.assertEqual(2,len(batch.items))
        self.assertEqual(1,len({item.element_id for item in batch.items}))
        self.assertTrue(any(tuple(choice.key for choice in item.choices) != tuple("ABCDE") for item in batch.items))
        self.assertEqual(batch,self.quiz.create_regular(101,101,now=NOW+timedelta(hours=8)))
        self.state.close()
        self.state = StateStore(self.directory/"learning.sqlite3")
        self.quiz = QuizService(self.content,self.state)
        graded = self.quiz.submit(101,101,self.answer_text(batch),now=NOW,submission_id="11")
        self.assertTrue(all(answer.correct for answer in graded.answers))
        self.assertTrue(all(answer.attempt_kind == "first" for answer in graded.answers))
        self.assertEqual(batch.items,graded.batch.items)
        second = self.quiz.submit(101,101,self.answer_text(batch,False),now=NOW)
        self.assertTrue(second.duplicate)
        self.assertEqual(2,len(self.state.answer_rows(101)))

    def test_old_message_id_or_batch_id_never_grades_new_active(self):
        previous = self.quiz.create_regular(101,101,now=NOW)
        self.quiz.submit(101,101,self.answer_text(previous),now=NOW,submission_id="telegram-1")
        active = self.quiz.create_regular(101,101,now=NOW+timedelta(minutes=1))
        duplicate = self.quiz.submit(101,101,self.answer_text(previous),now=NOW+timedelta(minutes=2),submission_id="telegram-1")
        self.assertEqual(previous.batch_id,duplicate.batch.batch_id)
        duplicate = self.quiz.submit(101,101,self.answer_text(previous),batch_id=previous.batch_id)
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(active.batch_id,self.state.active_batch(101,101).batch_id)
        self.assertEqual(2,len(self.state.answer_rows(101)))

    def test_invalid_whole_answers_do_not_partial_grade(self):
        batch = self.quiz.create_regular(101,101,now=NOW)
        for text in ("1", "1,2,3", "0,2", "6,1", "1,2,", "1 2", "1,wrong", "１,2"):
            with self.subTest(text=text),self.assertRaises(AnswerFormatError):
                self.quiz.submit(101,101,text,now=NOW)
            self.assertEqual([],self.state.answer_rows(101))
            self.assertEqual("active",self.state.batch(batch.batch_id).status)

    def test_replayed_skip_cannot_skip_later_active_batch(self):
        previous = self.quiz.create_regular(101,101,now=NOW)
        skipped = self.quiz.skip(101,101,submission_id="skip-1")
        active = self.quiz.create_regular(101,101,now=NOW+timedelta(minutes=1))
        replay = self.quiz.skip(101,101,submission_id="skip-1")
        self.assertEqual(skipped,replay)
        replay = self.quiz.skip(101,101,batch_id=previous.batch_id)
        self.assertEqual(skipped,replay)
        self.assertEqual(active,self.state.active_batch(101,101))

    def test_grading_rolls_back_if_second_insert_fails(self):
        batch = self.quiz.create_regular(101,101,now=NOW)
        self.state.connection.execute("""CREATE TRIGGER interrupt_grading BEFORE INSERT ON answers
            WHEN NEW.ordinal=2 BEGIN SELECT RAISE(ABORT,'test interruption'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.quiz.submit(101,101,self.answer_text(batch),now=NOW)
        self.assertEqual([],self.state.answer_rows(101))
        self.assertEqual("active",self.state.batch(batch.batch_id).status)

    def test_repeated_question_classified_review_not_batch_kind(self):
        questions = self.content.questions("FI-01")[:2]
        first = self.activate(questions)
        self.quiz.submit(101,101,self.answer_text(first,False),now=NOW)
        review = self.activate([questions[0],self.content.questions("FI-01")[2]],kind="review")
        result = self.quiz.submit(101,101,self.answer_text(review),now=NOW+timedelta(minutes=1))
        self.assertEqual(["review","first"],[answer.attempt_kind for answer in result.answers])
        summary = self.stats.summary(101,domain_id="FI",now=NOW+timedelta(minutes=1))
        row = summary.domains[0]
        self.assertEqual((2,3,0,1),(row.first_wrong,row.first_total,row.review_wrong,row.review_total))

    def test_skipped_and_unanswered_excluded_no_auto_expiry(self):
        unanswered = self.quiz.create_regular(101,101,now=NOW-timedelta(days=45))
        self.assertEqual(unanswered,self.quiz.create_regular(101,101,now=NOW))
        self.assertEqual("skipped",self.quiz.skip(101,101,now=NOW).status)
        with self.assertRaises(NoActiveQuizError):
            self.quiz.submit(101,101,self.answer_text(unanswered),batch_id=unanswered.batch_id)
        self.quiz.create_regular(101,101,now=NOW)
        self.assertEqual(0,sum(row.first_total+row.review_total for row in self.stats.summary(101,now=NOW).domains))

    def test_kst_calendar_boundaries_and_low_sample(self):
        # UTC 09/26 15:00 is KST 09/27 00:00, the first included date of seven.
        before = NOW.replace(hour=0,minute=0)-timedelta(days=6,microseconds=1)
        inside = before+timedelta(microseconds=1)
        first = self.activate(self.content.questions("FI-01")[:1],now=before)
        self.quiz.submit(101,101,self.answer_text(first,False),now=before.astimezone(timezone.utc))
        second = self.activate(self.content.questions("FI-01")[1:2],now=inside)
        self.quiz.submit(101,101,self.answer_text(second),now=inside.astimezone(timezone.utc))
        summary = self.stats.summary(101,domain_id="FI",now=NOW)
        row = summary.domains[0]
        self.assertEqual((0,1),(row.first_wrong,row.first_total))
        self.assertTrue(row.low_sample)
        element = next(item for item in summary.elements if item.key=="FI-01")
        self.assertEqual((0,1),(element.first_wrong,element.first_total))
        self.assertEqual(2,self.stats.summary(101,30,domain_id="FI",now=NOW).domains[0].first_total)
        self.assertIn("표본 부족",format_stats(summary))

    def test_weekly_report_only_claims_evidence_and_review_recovers_errors(self):
        self.assertIsNone(self.quiz.create_review(101,101,now=NOW))
        self.assertIn("판단할 표본이 아직 적습니다",self.stats.weekly_report(101,now=NOW))
        first = self.activate(self.content.questions("FI-01")[:2])
        self.quiz.submit(101,101,self.answer_text(first,False),now=NOW)
        review = self.quiz.create_review(101,101,now=NOW+timedelta(minutes=1))
        self.assertGreaterEqual(len(review.items),2)
        self.assertTrue({item.question_id for item in first.items}.issubset({item.question_id for item in review.items}))
        self.quiz.submit(101,101,self.answer_text(review),now=NOW+timedelta(minutes=2))
        report = self.stats.weekly_report(101,now=NOW+timedelta(minutes=3))
        self.assertIn("FI: 첫 시도 3문항 중 오답 2개",report)
        self.assertIn("FI-01: 앞서 틀린 문항 2개를 최근 재도전에서 맞혔습니다",report)
        self.assertNotIn("반복 오답이 기록",report)

    def test_weekly_repeated_errors_require_actual_domain_sample(self):
        first = self.activate(self.content.questions("FI-01"))
        self.quiz.submit(101,101,self.answer_text(first,False),now=NOW)
        second = self.activate(self.content.questions("FI-02")[:2])
        self.quiz.submit(101,101,self.answer_text(second),now=NOW+timedelta(minutes=1))
        report = self.stats.weekly_report(101,now=NOW+timedelta(minutes=2))
        self.assertIn("FI: 첫 시도 5문항 중 오답 3개",report)
        self.assertIn("FI-01: 채점 3회 중 오답 3회",report)

    def test_domain_rotation_and_unseen_priority(self):
        domains = []
        question_ids = []
        for index in range(7):
            batch = self.quiz.create_regular(101,101,now=NOW+timedelta(minutes=index))
            domains.append(batch.items[0].domain_id)
            question_ids.extend(item.question_id for item in batch.items)
            self.quiz.skip(101,101)
        self.assertEqual(7,len(set(domains)))
        self.assertEqual(14,len(set(question_ids)))
        four = self.quiz.create_regular(101,101,count=4,now=NOW)
        self.assertEqual(4,len(four.items))
        self.assertEqual(4,len({item.question_id for item in four.items}))

    def test_concurrent_creation_uses_one_active_batch(self):
        other = StateStore(self.directory/"learning.sqlite3")
        try:
            other_quiz = QuizService(self.content,other)
            with ThreadPoolExecutor(max_workers=2) as pool:
                batches = list(pool.map(lambda service: service.create_regular(101,101,now=NOW),[self.quiz,other_quiz]))
            self.assertEqual(batches[0].batch_id,batches[1].batch_id)
            self.assertEqual(1,self.state.connection.execute("SELECT COUNT(*) FROM quiz_batches").fetchone()[0])
        finally:
            other.close()

    def test_job_news_dedup_and_ambiguous_delivery_survive_restart(self):
        self.assertTrue(self.state.claim_job(101,"regular","2026-10-03","12:30",now=NOW))
        self.state.finish_job(101,"regular","2026-10-03","12:30",status="uncertain",now=NOW)
        self.assertFalse(self.state.claim_job(101,"regular","2026-10-03","12:30",now=NOW))
        batch = self.quiz.create_regular(101,101,now=NOW)
        self.state.mark_batch_delivery(batch.batch_id,"uncertain",now=NOW)
        self.assertIsNone(self.state.batch(batch.batch_id).sent_at)
        self.assertTrue(self.state.record_news(101,"https://www.bis.org/news.htm",NOW,NOW))
        self.assertFalse(self.state.record_news(101,"https://www.bis.org/news.htm",NOW,NOW))
        self.assertEqual({"https://www.bis.org/news.htm"},self.state.seen_news_urls(101))
        self.state.close()
        self.state = StateStore(self.directory/"learning.sqlite3")
        self.assertFalse(self.state.claim_job(101,"regular","2026-10-03","12:30",now=NOW))
        self.assertEqual("uncertain",self.state.batch(batch.batch_id).delivery_status)

    def test_state_rejects_repository_path_and_delete_is_user_scoped(self):
        with self.assertRaises(ValueError):
            StateStore(ROOT/"hermes_telegram"/"must-not-create.sqlite3")
        first = self.quiz.create_regular(101,101,now=NOW)
        second = self.quiz.create_regular(202,202,now=NOW)
        self.state.delete_user(101)
        self.assertIsNone(self.state.batch(first.batch_id))
        self.assertIsNotNone(self.state.batch(second.batch_id))

    def test_state_rejects_unrelated_database_without_modifying_it(self):
        path = self.directory/"android-user.sqlite3"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE user_notes (note TEXT)")
        connection.execute("INSERT INTO user_notes VALUES ('preserve me')")
        connection.commit()
        connection.close()
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            StateStore(path)
        self.assertEqual(before,path.read_bytes())
        self.assertFalse(Path(str(path)+"-wal").exists())

    def test_telegram_split_keeps_batch_label_and_question_numbers(self):
        batch = self.quiz.create_regular(101,101,count=4,now=NOW)
        chunks = split_message(format_quiz(batch),limit=500)
        self.assertGreater(len(chunks),1)
        self.assertTrue(all(len(chunk.encode("utf-16-le"))//2 <= 500 for chunk in chunks))
        self.assertTrue(all(f"회차 ID: {batch.batch_id}" in chunk for chunk in chunks))
        joined = "".join(chunks)
        self.assertTrue(all(f"Q{index}." in joined for index in range(1,5)))
        emoji = split_message("😀"*5000,limit=4000)
        self.assertTrue(all(len(chunk.encode("utf-16-le"))//2 <= 4000 for chunk in emoji))

    def fixture(self,sql=None,manifest_updates=None):
        db = self.directory/"content.sqlite3"
        manifest_path = self.directory/"content-manifest.json"
        shutil.copyfile(ASSETS/"content.sqlite3",db)
        manifest = json.loads((ASSETS/"content-manifest.json").read_text(encoding="utf-8"))
        if sql:
            connection = sqlite3.connect(db)
            try:
                connection.executescript(sql)
                connection.commit()
            finally:
                connection.close()
        manifest.update(manifest_updates or {})
        manifest["byteSize"] = db.stat().st_size
        manifest["sha256"] = hashlib.sha256(db.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest),encoding="utf-8")
        return db,manifest_path

    def test_integrity_rejects_hash_schema_versions_counts_and_invalid_choices(self):
        cases = [(None,{"sha256":"f"*64}),
                 ("PRAGMA user_version=99;",None),
                 ("UPDATE metadata SET value='99' WHERE key='content_db_version';",None),
                 ("DELETE FROM concept_question_choices WHERE question_id='FI-01-term_to_definition-01' AND choice_key='A';",None),
                 ("UPDATE concept_question_choices SET is_correct=1 WHERE question_id='FI-01-term_to_definition-01';",None)]
        for sql,updates in cases:
            with self.subTest(sql=sql):
                db,manifest = self.fixture(sql,updates)
                if updates:
                    data = json.loads(manifest.read_text())
                    data.update(updates)
                    manifest.write_text(json.dumps(data))
                with self.assertRaises(ContentIntegrityError):
                    ContentRepository(db,manifest)

    def test_candidate_only_eligible_questions_are_selectable(self):
        db,manifest = self.fixture("""UPDATE metadata SET value='candidate' WHERE key='concept_question_release_status';
            UPDATE concept_questions SET review_status='blocked' WHERE question_id='FI-01-term_to_definition-01';""",
            {"conceptQuestionReleaseStatus":"candidate"})
        with ContentRepository(db,manifest) as content:
            self.assertEqual(404,len(content.questions()))
            self.assertIsNone(content.question("FI-01-term_to_definition-01"))


if __name__ == "__main__":
    unittest.main()
