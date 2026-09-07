"""
Lesson 4: the query is correct and the answer is still wrong.

Lessons 2 and 3 were about queries that make mistakes. This one is about a query that
makes no mistake at all and still produces a number you should not put on a slide,
because the question it answered was never fully asked.

"How much revenue did we book in March?" sounds precise. It contains at least three
unstated decisions:

  * Is revenue booked when an order is placed, or when it ships? One order in this
    warehouse was placed March 31st and shipped April 1st. $450 sits on that choice.
  * Is revenue gross, or net of refunds? Two orders here were refunded, one fully.
    $829.97 sits on that choice.
  * Do cancelled and pending orders count? Everyone says no, until someone builds a
    forecast where pending counts, and now the company has two revenue numbers.

Each of those has a defensible answer. Several have two. What none of them has is an
answer the model can derive, because the answer does not live in the schema, the data,
or the phrasing of the question. It lives in a decision somebody made in a meeting, or
worse, never made.

This is the ceiling on prompt engineering for analytics, and it is a hard ceiling.
The `annotated` prompt in lesson 1 is full of good advice and still gets March revenue
wrong, because "be careful about dates" is not a date column. What fixes it is the
`defined` level, and look at what that level actually contains: not technique, just
finance's ruling written down where the machine can read it.

The industry name for writing those rulings down is a **semantic layer** or a metric
store: revenue defined once, in one place, with an owner, and every query built from
that definition rather than re-deriving it. dbt metrics, Cube, LookML and Malloy are
all versions of this. The AI angle is small and worth stating plainly: a text-to-SQL
system on top of a warehouse with defined metrics works considerably better than one
without, and neither the model nor the prompt is what changed.

Predict before running: which of the two March numbers is bigger, and by how much?
Then decide which one you would report, and notice that you needed a reason.

Previous: lesson 3 was a mechanical bug. Next: lesson 5 leaves correctness entirely.
See README section 4 and TEXTBOOK section 20.5.

Run it:

    python examples/04_metric_definitions.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import askdb

MARCH_BY_ORDERED = """
    SELECT SUM(total_cents) FROM orders
    WHERE status = 'completed' AND ordered_at >= '2025-03-01' AND ordered_at < '2025-04-01'
"""

MARCH_BY_SHIPPED = """
    SELECT SUM(total_cents) FROM orders
    WHERE status = 'completed' AND shipped_at >= '2025-03-01' AND shipped_at < '2025-04-01'
"""

GROSS = "SELECT SUM(total_cents) FROM orders WHERE status = 'completed'"

NET = """
    SELECT (SELECT SUM(total_cents) FROM orders WHERE status = 'completed')
         - (SELECT COALESCE(SUM(amount_cents), 0) FROM refunds)
"""

WITH_PENDING = "SELECT SUM(total_cents) FROM orders WHERE status IN ('completed','pending')"


def three_ambiguities(conn) -> None:
    print("Three questions that sound like one question\n" + "=" * 70)

    ordered = askdb.run(conn, MARCH_BY_ORDERED).scalar
    shipped = askdb.run(conn, MARCH_BY_SHIPPED).scalar
    print('\n  "Revenue booked in March 2025"')
    print(f"    by ordered_at   {askdb.usd(ordered):>12}")
    print(f"    by shipped_at   {askdb.usd(shipped):>12}   difference {askdb.usd(ordered - shipped)}")
    straddler = askdb.run(conn, """
        SELECT id, ordered_at, shipped_at, total_cents FROM orders
        WHERE ordered_at < '2025-04-01' AND shipped_at >= '2025-04-01'
    """)
    for order_id, o_at, s_at, total in straddler.rows:
        print(f"    the whole difference is order {order_id}: placed {o_at}, shipped {s_at}, "
              f"{askdb.usd(total)}")

    gross, net = askdb.run(conn, GROSS).scalar, askdb.run(conn, NET).scalar
    print('\n  "Total revenue"')
    print(f"    gross           {askdb.usd(gross):>12}")
    print(f"    net of refunds  {askdb.usd(net):>12}   difference {askdb.usd(gross - net)}")

    pending = askdb.run(conn, WITH_PENDING).scalar
    print('\n  "Revenue"')
    print(f"    completed only  {askdb.usd(gross):>12}")
    print(f"    plus pending    {askdb.usd(pending):>12}   difference {askdb.usd(pending - gross)}")

    spread = pending - net
    print(
        f"\n  Five distinct numbers for one word. The widest gap between two of them is\n"
        f"  {askdb.usd(spread)}, which on this warehouse is {spread / net:.0%} of net revenue. Every\n"
        f"  one of those queries is correct SQL and would pass any review that checks\n"
        f"  syntax, joins, and filters.\n"
    )


def what_the_prompt_can_do(conn) -> None:
    print("What each prompt level does with it\n" + "=" * 70)
    question = askdb.BY_ID["march_revenue"]
    for level in askdb.LEVELS:
        sql = askdb.generate(question, level)
        outcome = askdb.score_one(conn, question, sql)
        column = "ordered_at" if "ordered_at" in sql else "shipped_at" if "shipped_at" in sql else "?"
        answer = outcome.result.scalar if outcome.result else None
        shown = askdb.usd(answer) if isinstance(answer, (int, float)) else "-"
        print(f"  {level:<10} {outcome.verdict:<8} used {column:<11} -> {shown}")

    print(
        "\n  The annotated prompt contains four careful warnings about joins, statuses,\n"
        "  units, and abstention, and it still picks the wrong date column, because\n"
        "  none of those warnings is a decision about when revenue is booked. The\n"
        "  defined prompt gets it right for one reason: somebody wrote the decision\n"
        "  down. That is not a better prompt in any interesting sense. It is a\n"
        "  different input.\n"
    )


if __name__ == "__main__":
    print(f"Provider: {askdb.describe()}\n")
    conn = askdb.connect()
    three_ambiguities(conn)
    what_the_prompt_can_do(conn)
    print(
        "Takeaway: a text-to-SQL system inherits every undefined metric in the business,\n"
        "and it inherits them silently, because it will always pick something. The\n"
        "failure looks like a model problem and is not one. Before blaming retrieval or\n"
        "the prompt for a wrong number, check whether two analysts asked the same\n"
        "question would have written the same query. If they would not, the system is\n"
        "working correctly and the specification is missing.\n\n"
        "The practical order of operations: define the metric, put the definition in\n"
        "the prompt (or better, behind a view or a metric layer the model queries), and\n"
        "add a benchmark question whose gold answer encodes the ruling. Then the next\n"
        "person to reinterpret it fails the eval instead of shipping a second number."
    )
