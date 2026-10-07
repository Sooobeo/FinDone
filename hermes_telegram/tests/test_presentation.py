from __future__ import annotations

import unittest

from findone_hermes.presentation import hermes_markdown, telegram_entities


def bold_text(text):
    encoded = text.encode("utf-16-le")
    return [encoded[item["offset"] * 2:(item["offset"] + item["length"]) * 2].decode("utf-16-le")
            for item in telegram_entities(text)]


class PresentationTests(unittest.TestCase):
    def test_news_utf16_entities_preserve_headline_terms_and_original_link(self):
        body = ("📰 FinDone | 금융 영어 뉴스\n\nBanks & markets <update> 🏦\n\n"
                "🏛 ECB · 🗓 2026-10-07\n\n🇬🇧 원문 발췌 요약\nMarkets improved.\n\n"
                "📚 금융 전문 어휘\n\n1. underwriting · 금융 전문\n   인수\n\n"
                "💼 중요한 비즈니스 구문\n\n1. back on track\n   정상 궤도로\n\n"
                "🔎 원문\nhttps://example.com/a?x=1&y=2")
        self.assertEqual(bold_text(body), [
            "📰 FinDone | 금융 영어 뉴스", "Banks & markets <update> 🏦",
            "🇬🇧 원문 발췌 요약", "📚 금융 전문 어휘", "underwriting",
            "💼 중요한 비즈니스 구문", "back on track", "🔎 원문",
        ])
        markdown = hermes_markdown(body)
        self.assertIn("**Banks & markets <update> 🏦**", markdown)
        self.assertIn("1. **underwriting** · 금융 전문", markdown)
        self.assertIn("🔎 원문**\nhttps://example.com/a?x=1&y=2", markdown)

    def test_learning_choices_and_batch_id_remain_plain_after_split(self):
        body = ("📝 FinDone · 오늘의 퀴즈\n총 2문항\n\n❓ Q1.\n질문입니다.\n\n"
                "1) 선택지\n\n2) 다른 선택지\n\n✍️ 답장 방법\n예시: 1,2\n\n회차 ID: abc")
        self.assertEqual(bold_text(body), ["📝 FinDone · 오늘의 퀴즈", "❓ Q1.", "✍️ 답장 방법"])
        self.assertIn("회차 ID: abc", hermes_markdown(body))
        self.assertIn("1) 선택지", hermes_markdown(body))
        self.assertEqual(hermes_markdown("1) 선택지\n\n❓ Q2.\n새 질문"),
                         "1) 선택지\n\n**❓ Q2.**\n새 질문")

    def test_source_asterisks_do_not_nest_generated_bold(self):
        self.assertEqual(hermes_markdown("💡 A * B"), "💡 A * B")
        self.assertEqual(hermes_markdown("ordinary response"), "ordinary response")


if __name__ == "__main__":
    unittest.main()
