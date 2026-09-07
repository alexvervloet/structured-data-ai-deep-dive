"""Verdicts, and the arc the lessons claim.

The accuracy figures are asserted here so the prose in the READMEs and examples cannot
drift away from what the code does. If a canned query changes, this fails before a
reader finds a paragraph quoting a number that no longer happens.
"""

import unittest

from askdb.evaluate import (
    ABSTAINED,
    BLOCKED,
    CORRECT,
    ERROR,
    OVERREACHED,
    WRONG,
    evaluate,
    score_one,
    summarize,
)
from askdb.permissions import analyst_connection
from askdb.questions import BY_ID
from askdb.warehouse import connect


class TestVerdicts(unittest.TestCase):
    def setUp(self):
        self.conn = connect()

    def verdict(self, question_id, sql):
        return score_one(self.conn, BY_ID[question_id], sql).verdict

    def test_matching_rows_are_correct(self):
        self.assertEqual(
            self.verdict("total_revenue",
                         "SELECT SUM(total_cents) FROM orders WHERE status='completed'"),
            CORRECT)

    def test_different_rows_are_wrong(self):
        self.assertEqual(self.verdict("total_revenue", "SELECT SUM(total_cents) FROM orders"),
                         WRONG)

    def test_unparseable_sql_is_an_error_not_a_crash(self):
        self.assertEqual(self.verdict("total_revenue", "SELECT SUM(totl_cents) FROM ordrs"), ERROR)

    def test_declining_an_answerable_question_is_its_own_verdict(self):
        self.assertEqual(self.verdict("total_revenue", "CANNOT ANSWER: not sure"), ABSTAINED)

    def test_declining_an_unanswerable_question_is_correct(self):
        self.assertEqual(self.verdict("best_channel", "CANNOT ANSWER: no such table"), CORRECT)

    def test_answering_an_unanswerable_question_is_overreach(self):
        self.assertEqual(self.verdict("best_channel", "SELECT 1"), OVERREACHED)

    def test_overreach_is_judged_before_execution(self):
        """Even valid SQL is overreach if the question had no answer."""
        self.assertEqual(self.verdict("support_tickets", "SELECT COUNT(*) FROM orders"),
                         OVERREACHED)


class TestBlockedVerdict(unittest.TestCase):
    def test_a_refused_query_is_blocked_not_an_error(self):
        connect()
        analyst = analyst_connection()
        outcome = score_one(analyst, BY_ID["customer_emails"], "SELECT email FROM customers")
        self.assertEqual(outcome.verdict, BLOCKED)

    def test_a_broken_query_is_still_an_error_on_the_same_connection(self):
        connect()
        analyst = analyst_connection()
        outcome = score_one(analyst, BY_ID["total_revenue"], "SELECT nope FROM nowhere")
        self.assertEqual(outcome.verdict, ERROR)


class TestTheArc(unittest.TestCase):
    """The claim the whole course makes: more written down, better results."""

    def setUp(self):
        self.conn = connect()

    def accuracy(self, level):
        return summarize(evaluate(self.conn, level))["accuracy"]

    def test_accuracy_improves_with_each_level(self):
        bare, annotated, defined = (self.accuracy(x) for x in ("bare", "annotated", "defined"))
        self.assertLess(bare, annotated)
        self.assertLess(annotated, defined)
        self.assertEqual(defined, 1.0)

    def test_the_definition_questions_survive_the_annotated_prompt(self):
        """Lesson 4's argument: careful advice is not a decision."""
        outcomes = {o.question.id: o.verdict for o in evaluate(self.conn, "annotated")}
        self.assertEqual(outcomes["march_revenue"], WRONG)
        self.assertEqual(outcomes["net_revenue"], WRONG)

    def test_the_permission_question_is_never_fixed_by_a_prompt(self):
        """Lesson 5's argument: all three levels produce the same PII query."""
        for level in ("bare", "annotated", "defined"):
            outcomes = {o.question.id: o for o in evaluate(self.conn, level)}
            self.assertNotIn("CANNOT", outcomes["customer_emails"].sql.upper())

    def test_scoring_through_the_boundary_lowers_the_headline_number(self):
        """The capstone's point: an eval with more privilege than production lies."""
        analyst = analyst_connection()
        on_owner = summarize(evaluate(self.conn, "defined"))["accuracy"]
        on_analyst = summarize(evaluate(analyst, "defined"))
        self.assertEqual(on_owner, 1.0)
        self.assertLess(on_analyst["accuracy"], on_owner)
        self.assertEqual(on_analyst[BLOCKED], 1)


if __name__ == "__main__":
    unittest.main()
