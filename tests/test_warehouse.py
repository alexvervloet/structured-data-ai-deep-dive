"""The fixture's planted facts, pinned.

Every lesson quotes numbers from this database. If a seed row changes, the prose goes
stale silently: the examples still run, still print a number, and the paragraph beside
it is now wrong. These tests are what make that a build failure instead.
"""

import unittest

from askdb.execute import run
from askdb.warehouse import connect


class TestSeedIntegrity(unittest.TestCase):
    def setUp(self):
        self.conn = connect()

    def scalar(self, sql):
        return run(self.conn, sql).scalar

    def test_line_items_sum_to_their_order_total(self):
        """If this drifts, the fan-out lesson's 'correct' alternatives disagree."""
        mismatched = run(self.conn, """
            SELECT o.id FROM orders o JOIN order_items i ON i.order_id = o.id
            GROUP BY o.id HAVING SUM(i.qty * i.unit_cents) != o.total_cents
        """)
        self.assertEqual(mismatched.rows, ())

    def test_completed_revenue(self):
        self.assertEqual(self.scalar("SELECT SUM(total_cents) FROM orders WHERE status='completed'"),
                         297994)

    def test_fanout_inflates_revenue(self):
        """Lesson 3's headline: $2,979.94 becomes $5,119.91."""
        self.assertEqual(self.scalar("""
            SELECT SUM(o.total_cents) FROM orders o
            JOIN order_items i ON i.order_id = o.id WHERE o.status='completed'
        """), 511991)

    def test_refunds_separate_gross_from_net(self):
        self.assertEqual(self.scalar("SELECT SUM(amount_cents) FROM refunds"), 82997)

    def test_one_order_straddles_the_month_boundary(self):
        """Lesson 4's $450 difference depends on exactly one order doing this."""
        straddlers = run(self.conn, """
            SELECT id, total_cents FROM orders
            WHERE ordered_at < '2025-04-01' AND shipped_at >= '2025-04-01'
        """)
        self.assertEqual(straddlers.rows, ((1004, 45000),))

    def test_non_paying_statuses_exist(self):
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders WHERE status='cancelled'"), 1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders WHERE status='pending'"), 1)

    def test_schema_has_no_marketing_or_satisfaction_or_tickets(self):
        """Lesson 6's unanswerable questions are only unanswerable if this holds."""
        schema = run(self.conn, "SELECT sql FROM sqlite_master").rows
        text = " ".join(str(row[0]) for row in schema).lower()
        for absent in ("channel", "satisfaction", "ticket", "campaign"):
            self.assertNotIn(absent, text)

    def test_connect_is_repeatable(self):
        """The examples reconnect mid-run; a second call must not fail or double-seed."""
        again = connect()
        self.assertEqual(run(again, "SELECT COUNT(*) FROM orders").scalar, 9)


if __name__ == "__main__":
    unittest.main()
