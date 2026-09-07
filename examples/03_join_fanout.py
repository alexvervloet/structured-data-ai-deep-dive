"""
Lesson 3: the join that multiplies your revenue.

If you take one specific bug away from this course, take this one. It is the most
common wrong answer in generated analytics SQL, it is invisible in review, and it
inflates numbers rather than breaking them, which means it reaches a slide.

The setup is completely ordinary. `orders` has one row per order with a `total_cents`.
`order_items` has one row per line item. They are related, obviously, so a query about
orders joins them. And the moment you join a parent to its children, the parent's row
is repeated once per child. Sum a parent column across that join and you have summed
it once per child.

    order 1002 costs $649.99 and has 3 line items
    after the join, order 1002 appears 3 times
    SUM(orders.total_cents) counts $649.99 three times

Nobody writes this bug on purpose, and nobody catches it by reading. The query is
short, the join condition is correct, the filter is correct, the column is the one
literally named `total_cents`. Everything about it looks right except the number, and
the number looks plausible because there is nothing to compare it to.

Three ways out, in the order you should reach for them:

  1. **Do not join what you do not need.** The best fix for the revenue question is to
     delete the join, because `orders` already has the total.
  2. **Aggregate the child first.** When you genuinely need both, collapse the many
     side to one row per parent in a subquery, then join that.
  3. **Aggregate the parent's column with DISTINCT on its key.** Works, reads badly,
     and future you will not trust it. Prefer 2.

Predict before running: with 7 completed orders and 11 line items among them, what is
the ratio between the fan-out sum and the true sum? It is not 11/7.

Previous: lesson 2 established execution scoring. Next: lesson 4, where the query is
right and the question was wrong.
See README section 3 and TEXTBOOK section 20.4.

Run it:

    python examples/03_join_fanout.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import askdb

TRUE_TOTAL = "SELECT SUM(total_cents) FROM orders WHERE status = 'completed'"

FANOUT = """
    SELECT SUM(o.total_cents) FROM orders o
    JOIN order_items i ON i.order_id = o.id
    WHERE o.status = 'completed'
"""

AGGREGATE_FIRST = """
    SELECT SUM(o.total_cents)
    FROM orders o
    JOIN (SELECT order_id, COUNT(*) AS lines FROM order_items GROUP BY order_id) i
      ON i.order_id = o.id
    WHERE o.status = 'completed'
"""

ITEM_SIDE = """
    SELECT SUM(i.qty * i.unit_cents)
    FROM order_items i JOIN orders o ON o.id = i.order_id
    WHERE o.status = 'completed'
"""


def show_the_duplication(conn) -> None:
    print("What the join actually produces\n" + "=" * 70)
    rows = askdb.run(conn, """
        SELECT o.id, o.total_cents, COUNT(i.id) AS line_items,
               o.total_cents * COUNT(i.id) AS counted_as
        FROM orders o JOIN order_items i ON i.order_id = o.id
        WHERE o.status = 'completed'
        GROUP BY o.id ORDER BY o.id
    """)
    print(f"  {'order':<8}{'total':>12}{'lines':>8}{'counted as':>14}")
    inflated = 0
    for row in rows.rows:
        order_id, total, lines, counted = row
        inflated += counted
        flag = "  <-- counted " + f"{lines}x" if lines > 1 else ""
        print(f"  {order_id:<8}{askdb.usd(total):>12}{lines:>8}{askdb.usd(counted):>14}{flag}")
    print(f"  {'':<8}{'':>12}{'':>8}{askdb.usd(inflated):>14}  total\n")


def compare(conn) -> None:
    truth = askdb.run(conn, TRUE_TOTAL).scalar
    fanout = askdb.run(conn, FANOUT).scalar
    agg = askdb.run(conn, AGGREGATE_FIRST).scalar
    items = askdb.run(conn, ITEM_SIDE).scalar

    print("Four queries about the same number\n" + "=" * 70)
    print(f"  no join at all (correct)        {askdb.usd(truth):>12}")
    print(f"  joined, aggregated first        {askdb.usd(agg):>12}")
    print(f"  summed the item side instead    {askdb.usd(items):>12}")
    print(f"  joined, summed the parent       {askdb.usd(fanout):>12}"
          f"   <-- {fanout / truth:.2f}x, off by {askdb.usd(fanout - truth)}")

    completed_orders = askdb.run(conn, "SELECT COUNT(*) FROM orders WHERE status='completed'").scalar
    lines = askdb.run(conn, """
        SELECT COUNT(*) FROM order_items i JOIN orders o ON o.id = i.order_id
        WHERE o.status = 'completed'
    """).scalar
    print(
        f"\n  {completed_orders} completed orders, {lines} line items between them, and the\n"
        f"  inflation is {fanout / truth:.2f}x rather than the {lines / completed_orders:.2f}x you get from dividing\n"
        f"  row counts. Each order is over-counted in proportion to its OWN line count,\n"
        f"  so the result is a weighted average, and here the weighting works against\n"
        f"  you: order 1002 has both the most line items and the largest total, which\n"
        f"  pushes the error above the row ratio. Reverse that (many small orders with\n"
        f"  many lines, one big order with one line) and the error lands below it.\n\n"
        f"  So the size of this bug depends on which rows happen to have many children.\n"
        f"  It moves month to month, there is no fudge factor that corrects it, and a\n"
        f"  number that was close enough last quarter can be badly wrong this one.\n"
    )


def sanity_check(conn) -> None:
    """The check that would have caught this in about four seconds."""
    print("The check that catches it\n" + "=" * 70)
    rows = askdb.run(conn, "SELECT COUNT(*) FROM orders WHERE status='completed'").scalar
    joined = askdb.run(conn, """
        SELECT COUNT(*) FROM orders o JOIN order_items i ON i.order_id = o.id
        WHERE o.status = 'completed'
    """).scalar
    print(f"  rows before the join: {rows}")
    print(f"  rows after the join:  {joined}")
    print(
        f"\n  The join changed the row count, so any aggregate over a column from the\n"
        f"  ORDERS side is now counting some orders more than once. That single\n"
        f"  comparison catches most of these, it costs one extra query, and it is the\n"
        f"  kind of assertion worth putting in the eval harness itself rather than\n"
        f"  trusting a reviewer to remember.\n"
    )


if __name__ == "__main__":
    print(f"Provider: {askdb.describe()}\n")
    conn = askdb.connect()
    show_the_duplication(conn)
    compare(conn)
    sanity_check(conn)
    print(
        "Takeaway: joining a parent to its children multiplies the parent's rows, and\n"
        "any SUM or AVG over a parent column is then wrong by an amount that depends on\n"
        "the data. The prompt fix is to tell the model that orders.total_cents must\n"
        "never be summed across a join to order_items, which is what the annotated level\n"
        "in lesson 1 does and it works. The durable fix is that your eval has a\n"
        "question whose gold answer this bug gets wrong, so it can never come back\n"
        "quietly."
    )
