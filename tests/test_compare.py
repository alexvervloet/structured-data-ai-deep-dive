"""Result comparison, including the cases that make it worth having."""

import unittest

from askdb.compare import equivalent, explain
from askdb.execute import Result, run
from askdb.warehouse import connect


def result(rows, columns=("a",)):
    return Result(columns=columns, rows=tuple(rows))


class TestEquivalence(unittest.TestCase):
    def test_identical_rows_match(self):
        self.assertTrue(equivalent(result([(1,)]), result([(1,)])))

    def test_row_order_is_ignored_by_default(self):
        """GROUP BY returns rows in whatever order it likes; that is not a bug."""
        self.assertTrue(equivalent(result([(1,), (2,)]), result([(2,), (1,)])))

    def test_row_order_matters_when_the_question_asked_for_it(self):
        self.assertFalse(equivalent(result([(1,), (2,)]), result([(2,), (1,)]), ordered=True))

    def test_column_names_are_ignored(self):
        """SUM(total_cents), revenue, and total are the same column with three names."""
        self.assertTrue(equivalent(result([(1,)], ("revenue",)), result([(1,)], ("total",))))

    def test_int_and_float_of_equal_value_match(self):
        self.assertTrue(equivalent(result([(5,)]), result([(5.0,)])))

    def test_float_noise_is_tolerated(self):
        self.assertTrue(equivalent(result([(1234.56,)]), result([(1234.5600000000001,)])))

    def test_genuinely_different_values_do_not_match(self):
        self.assertFalse(equivalent(result([(1234.56,)]), result([(1234.57,)])))

    def test_duplicate_rows_are_counted_not_collapsed(self):
        """Set comparison must not lose multiplicity, or fan-out bugs pass."""
        self.assertFalse(equivalent(result([(1,), (1,)]), result([(1,)])))
        self.assertFalse(equivalent(result([(1,)]), result([(1,), (1,)])))

    def test_a_failed_candidate_is_never_equivalent(self):
        self.assertFalse(equivalent(result([(1,)]), Result(error="boom")))

    def test_two_failures_are_not_agreement(self):
        self.assertFalse(equivalent(Result(error="boom"), Result(error="boom")))


class TestExplain(unittest.TestCase):
    def test_names_the_ratio_for_a_single_number(self):
        self.assertIn("1.72x", explain(result([(297994,)]), result([(511991,)])))

    def test_names_the_row_count_difference(self):
        message = explain(result([(1,), (2,)]), result([(1,)]))
        self.assertIn("fewer rows", message)

    def test_reports_a_broken_benchmark_distinctly(self):
        self.assertIn("benchmark is broken", explain(Result(error="bad gold"), result([(1,)])))

    def test_calls_out_ordering_when_only_the_order_differs(self):
        message = explain(result([(1,), (2,)]), result([(2,), (1,)]), ordered=True)
        self.assertIn("wrong order", message)


class TestAgainstTheRealDatabase(unittest.TestCase):
    def test_differently_written_queries_with_the_same_meaning_match(self):
        """The case a string comparison gets wrong: lesson 2's whole argument."""
        conn = connect()
        gold = run(conn, "SELECT SUM(total_cents) FROM orders WHERE status = 'completed'")
        other = run(conn, "SELECT SUM(o.total_cents) FROM orders AS o "
                          "WHERE NOT (o.status = 'cancelled' OR o.status = 'pending')")
        self.assertTrue(equivalent(gold, other))


if __name__ == "__main__":
    unittest.main()
