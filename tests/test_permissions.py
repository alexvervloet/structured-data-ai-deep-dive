"""The boundary, tested the way a boundary should be: by trying to get around it.

Each of these is a spelling that defeats a naive regex over the query string. They
pass here because nothing in `askdb.permissions` reads the query string.
"""

import unittest

from askdb.execute import run
from askdb.permissions import analyst_connection, is_permission_error
from askdb.warehouse import connect

EVASIONS = [
    "SELECT email FROM customers",
    "SELECT c.email AS contact FROM customers AS c",
    "SELECT (SELECT email FROM customers WHERE id = 1)",
    "SELECT email FROM customers WHERE 1 = 0",          # returns nothing, still denied
    "SELECT /* comment */ email FROM  customers",
    "SELECT UPPER(email) FROM customers",
    "SELECT COUNT(email) FROM customers",
    "select EMAIL from CUSTOMERS",
]

WRITES = [
    "DELETE FROM orders",
    "UPDATE orders SET total_cents = 0",
    "DROP TABLE refunds",
    "INSERT INTO customers VALUES (99,'x','y','z@x.c','2025-01-01')",
    "CREATE TABLE sneaky (id INT)",
    "ALTER TABLE orders ADD COLUMN x INT",
]


class TestReadsAreRestricted(unittest.TestCase):
    def setUp(self):
        connect()
        self.analyst = analyst_connection()

    def test_permitted_columns_still_work(self):
        self.assertTrue(run(self.analyst, "SELECT name, country FROM customers").ok)
        self.assertTrue(run(self.analyst, "SELECT COUNT(*) FROM orders").ok)

    def test_every_spelling_of_the_pii_column_is_denied(self):
        for sql in EVASIONS:
            with self.subTest(sql=sql):
                outcome = run(self.analyst, sql)
                self.assertFalse(outcome.ok, f"not denied: {sql}")
                self.assertTrue(is_permission_error(outcome.error))

    def test_select_star_is_denied_because_it_touches_the_column(self):
        outcome = run(self.analyst, "SELECT * FROM customers")
        self.assertFalse(outcome.ok)


class TestWritesAreRefused(unittest.TestCase):
    def setUp(self):
        self.owner = connect()
        self.analyst = analyst_connection()

    def test_no_write_succeeds(self):
        for sql in WRITES:
            with self.subTest(sql=sql):
                outcome = run(self.analyst, sql)
                self.assertFalse(outcome.ok, f"write allowed: {sql}")
                self.assertTrue(is_permission_error(outcome.error))

    def test_the_data_is_untouched_afterwards(self):
        """Checked on the connection that already existed.

        Reconnecting here would rebuild the fixture and make this pass no matter what
        the writes did, which is the kind of test that guards nothing.
        """
        for sql in WRITES:
            run(self.analyst, sql)
        self.assertEqual(run(self.owner, "SELECT COUNT(*) FROM orders").scalar, 9)
        self.assertEqual(run(self.owner, "SELECT COUNT(*) FROM refunds").scalar, 2)
        self.assertEqual(run(self.owner, "SELECT COUNT(*) FROM customers").scalar, 5)
        self.assertEqual(
            run(self.owner, "SELECT SUM(total_cents) FROM orders WHERE status='completed'").scalar,
            297994)


class TestPermissionErrorDetection(unittest.TestCase):
    def test_recognizes_a_refusal(self):
        self.assertTrue(is_permission_error("access to customers.email is prohibited"))
        self.assertTrue(is_permission_error("attempt to write a readonly database"))

    def test_does_not_mistake_a_broken_query_for_a_refusal(self):
        self.assertFalse(is_permission_error("no such column: totl_cents"))
        self.assertFalse(is_permission_error(None))


if __name__ == "__main__":
    unittest.main()
