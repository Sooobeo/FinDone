import re
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from tools import build_content_db as generator


ASSET_DATABASE = Path(__file__).parents[1] / "app" / "src" / "main" / "assets" / "content.sqlite3"


class FormulaMarkdownGeneratorTest(unittest.TestCase):
    def test_concept_question_bank_is_hash_valid_and_covers_every_element(self) -> None:
        _, elements, _, _ = generator.parse_spec(generator.DEFAULT_SPEC)
        bank = generator.load_concept_question_bank(
            expected_element_ids=(element.element_id for element in elements),
        )

        self.assertEqual(405, bank["questionCount"])
        self.assertIn(bank["releaseStatus"], {"candidate", "release_ready"})
        self.assertEqual(405, len(bank["questions"]))
        self.assertTrue(all(len(question["choices"]) == 5 for question in bank["questions"]))
        self.assertTrue(
            all(
                question["reviewStatus"] in generator.VALID_QUESTION_REVIEW_STATUSES
                for question in bank["questions"]
            )
        )
        if bank["releaseStatus"] == "release_ready":
            self.assertTrue(
                all(
                    question["reviewStatus"]
                    in generator.APP_ELIGIBLE_QUESTION_REVIEW_STATUSES
                    for question in bank["questions"]
                )
            )

    def test_parenthetical_concept_aliases_collide(self) -> None:
        self.assertFalse(
            generator.concept_title_alias_keys("계속가치(Terminal Value)").isdisjoint(
                generator.concept_title_alias_keys("계속가치")
            )
        )

    def test_explicit_formula_boundaries_keep_hangul_outside_math(self) -> None:
        source = "자산 `(A)` = 부채 `(L)` + 자본 `(E)`"
        relation = generator.clean_inline_markdown(source)
        rendered = generator.formula_items_markdown(
            relation,
            formula_segments=generator.markdown_formula_segments(source),
        )

        self.assertNotIn("`", rendered)
        self.assertIn("자산", rendered)
        self.assertIn("$$(A)$$", rendered)
        for body in re.findall(r"\$\$\n?(.*?)\n?\$\$", rendered, re.DOTALL):
            self.assertIsNone(generator.HANGUL_RE.search(body))

        self.assertEqual(
            "자산$$(A)$$ = 부채$$(L)$$ + 자본$$(E)$$",
            generator.formula_clause_markdown("자산(A) = 부채(L) + 자본(E)"),
        )
        self.assertEqual(
            "현금 = 부채 + 자본",
            generator.formula_clause_markdown("현금 = 부채 + 자본"),
        )

    def test_long_sum_stays_in_one_delimiter_only_block(self) -> None:
        source = "X=1+2+3+4+5+6+7+8+9+10+11+12+13+14+15+16+17+18+19"
        rendered = generator.formula_clause_markdown(source)

        self.assertEqual(1, rendered.count("$$\n"))
        self.assertTrue(rendered.startswith("$$\n"))
        self.assertTrue(rendered.endswith("\n$$"))
        for line in rendered.splitlines():
            if "$$" in line:
                self.assertEqual("$$", line)

    def test_reviewed_learning_copy_covers_every_element(self) -> None:
        _, elements, _, _ = generator.parse_spec(generator.DEFAULT_SPEC)
        copy = generator.load_learning_copy(
            expected_element_ids=(element.element_id for element in elements)
        )

        self.assertEqual(135, len(copy))
        self.assertTrue(all(len(item.uses) >= 2 for item in copy.values()))

    def test_repeated_same_base_scripts_are_rejected(self) -> None:
        self.assertIsNone(generator.latex_expression("NBV_at_sale"))
        self.assertEqual(
            r"\mathrm{NBV}_{\mathrm{sale}}",
            generator.latex_expression("NBV_sale"),
        )
        self.assertEqual(
            r"(V_P \times D_P)/(V_F \times D_F)",
            generator.latex_expression("(V_PD_P)/(V_FD_F)"),
        )

    def test_reviewed_implicit_products_keep_factor_boundaries(self) -> None:
        probes = {
            "S_u=u×S_0": r"S_u=u \times S_0",
            "q=(R-d)/(u-d)=(R×S_0-S_d)/(S_u-S_d)": (
                r"q=(R-d)/(u-d)=(R \times S_0-S_d)/(S_u-S_d)"
            ),
            "V_0=[q×V_u+(1-q)×V_d]/R": (
                r"V_0=[q \times V_u+(1-q) \times V_d]/R"
            ),
            "C=S_0×N(d_1)-K×e^(-r×T)×N(d_2)": (
                r"C=S_0 \times N(d_1)-K \times e^{(-r \times T)} \times N(d_2)"
            ),
            "PV(K)=Ke^(−rT)": r"\mathrm{PV}(K)=K \times e^{(-r \times T)}",
            "F_0=(S_0-I)(1+rT)": r"F_0=(S_0-I)(1+r \times T)",
            "E(R_p)=wR_A+(1−w)R_B": r"E(R_p)=w \times R_A+(1-w) \times R_B",
            "wD_1+(1−w)D_2=D_L": r"w \times D_1+(1-w) \times D_2=D_L",
            "WACC=wE×ke+wD×kd×(1-T)": (
                r"\mathrm{WACC}=w_E \times k_e+w_D \times k_d \times (1-T)"
            ),
        }
        for source, expected in probes.items():
            self.assertEqual(
                expected,
                generator.latex_expression(source, require_comparison=True),
            )

    def test_embedded_blocks_stay_nested_and_drop_orphan_period(self) -> None:
        _, elements, _, _ = generator.parse_spec(generator.DEFAULT_SPEC)
        for element_id in ("DER-09", "EQV-44"):
            element = next(item for item in elements if item.element_id == element_id)
            rendered = generator.element_formula_items_markdown(element, indent="  ")
            self.assertFalse(any(line == "$$" for line in rendered.splitlines()))
            self.assertFalse(
                any(line.strip() in {".", "。"} for line in rendered.splitlines())
            )

    def test_packaged_formula_cards_have_no_code_or_hangul_math_fallback(self) -> None:
        with closing(sqlite3.connect(ASSET_DATABASE)) as database:
            rows = database.execute("SELECT expression FROM formula_cards").fetchall()
            all_visible_rows = database.execute(
                """SELECT c.definition, c.intuition, c.scope_notes,
                          f.expression, f.assumptions, f.notes
                   FROM concept_cards c JOIN formula_cards f USING(element_id)"""
            ).fetchall()
            version = database.execute(
                "SELECT value FROM metadata WHERE key = 'content_db_version'"
            ).fetchone()
            schema_version = database.execute("PRAGMA user_version").fetchone()
            question_count = database.execute(
                "SELECT COUNT(*) FROM concept_questions"
            ).fetchone()
            choice_count = database.execute(
                "SELECT COUNT(*) FROM concept_question_choices"
            ).fetchone()
            malformed_questions = database.execute(
                """
                SELECT q.question_id FROM concept_questions q
                JOIN concept_question_choices c USING(question_id)
                GROUP BY q.question_id, q.element_id
                HAVING COUNT(*) != 5 OR SUM(c.is_correct) != 1
                   OR SUM(c.is_correct = 1 AND c.element_id = q.element_id) != 1
                """
            ).fetchall()
            app_eligible_question_count = database.execute(
                """
                SELECT COUNT(*) FROM concept_questions
                WHERE review_status IN ('automated_pass', 'owner_approved')
                """
            ).fetchone()
            question_release_status = database.execute(
                "SELECT value FROM metadata WHERE key = 'concept_question_release_status'"
            ).fetchone()
            uncovered_elements = database.execute(
                """
                SELECT e.element_id
                FROM elements e
                LEFT JOIN concept_questions q
                    ON q.element_id = e.element_id
                   AND q.review_status IN ('automated_pass', 'owner_approved')
                GROUP BY e.element_id
                HAVING COUNT(q.question_id) = 0
                """
            ).fetchall()

        self.assertEqual((str(generator.CONTENT_DB_VERSION),), version)
        self.assertEqual((generator.SCHEMA_VERSION,), schema_version)
        self.assertEqual((405,), question_count)
        self.assertEqual((2025,), choice_count)
        self.assertGreater(app_eligible_question_count[0], 0)
        self.assertLessEqual(app_eligible_question_count[0], question_count[0])
        if question_release_status == ("release_ready",):
            self.assertEqual([], uncovered_elements)
        else:
            self.assertIn(
                question_release_status,
                {("bootstrap_not_reviewed",), ("candidate",)},
            )
        self.assertEqual([], malformed_questions)
        self.assertEqual(135, len(rows))
        self.assertEqual(135, sum("$$" in expression for (expression,) in rows))
        self.assertFalse(any("`" in value for row in all_visible_rows for value in row))
        self.assertFalse(
            any(
                generator.FORBIDDEN_MERGED_PRODUCT_TEX_RE.search(value)
                for row in all_visible_rows
                for value in row
            )
        )
        self.assertFalse(
            any(
                generator.HANGUL_RE.search(body)
                for (expression,) in rows
                for body in re.findall(r"\$\$\n?(.*?)\n?\$\$", expression, re.DOTALL)
            )
        )


if __name__ == "__main__":
    unittest.main()
