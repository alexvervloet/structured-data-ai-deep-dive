"""
Lesson 2: you cannot score SQL by looking at it.

This is the lesson the rest of the course rests on, so it gets a demonstration rather
than an assertion.

The tempting way to evaluate generated SQL is to compare it against a reference query.
It is cheap, it needs no database, it runs in CI in milliseconds, and every part of
that appeal is real. It is also wrong in both directions at once, which is unusual and
worth seeing.

**It marks correct queries wrong.** SQL is expressive. The same question has dozens of
faithful spellings: aliases or not, a join or a subquery, `IN` or `OR`, `NOT (a OR b)`
instead of `= c`. All return identical rows. A text comparison sees strangers.

**It marks catastrophic queries right.** Delete nine characters from a correct query
and you can change the answer by 72%. `WHERE status = 'completed'` is a small piece of
text carrying most of the meaning. A text comparison sees a near-perfect match.

Both failures point the same way. The thing you care about is the rows, and the only
thing that knows the rows is the database. Run the query.

A note on the LLM-judge version of this idea, because it is the obvious next thought:
ask a strong model to read both queries and rule on whether they agree. It is better
than string matching and it fails in the same direction, because it is also reading the
text. A judge that reads the pair below and sees two nearly identical queries has no
way to know that one of them silently includes $900 of cancelled orders; the difference
is not in the SQL, it is in the data. This lesson runs offline so it cannot demonstrate
that claim with a real judge. Treat it as an argument, and if you disagree, the
[Evals dive](https://github.com/alexvervloet/evals-deep-dive) shows how to test it.

Predict before running: rank the three candidates by text similarity to the reference,
then rank them by whether they return the right answer. The two rankings are almost
reversed.

Previous: lesson 1 built the prompts. Next: lesson 3 dissects the first real bug.
See README section 2 and TEXTBOOK section 20.3.

Run it:

    python examples/02_execution_based_eval.py
"""

import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import askdb

GOLD = "SELECT SUM(total_cents) FROM orders WHERE status = 'completed'"

CANDIDATES = [
    (
        "forgot the status filter",
        "SELECT SUM(total_cents) FROM orders",
    ),
    (
        "same meaning, written by someone else",
        "SELECT SUM(o.total_cents) FROM orders AS o "
        "WHERE NOT (o.status = 'cancelled' OR o.status = 'pending')",
    ),
    (
        "joined the line items",
        "SELECT SUM(o.total_cents) FROM orders o JOIN order_items i "
        "ON i.order_id = o.id WHERE o.status = 'completed'",
    ),
]


def similarity(a: str, b: str) -> float:
    """Plain text similarity, the metric a string-matching eval would use."""
    return difflib.SequenceMatcher(None, a.split(), b.split()).ratio()


def main() -> None:
    conn = askdb.connect()
    gold = askdb.run(conn, GOLD)
    print(f"Reference query answer: {askdb.usd(gold.scalar)}\n")

    print(f"{'candidate':<40} {'text match':>10} {'answer':>12} {'correct?':>10}")
    print("-" * 76)
    for label, sql in CANDIDATES:
        result = askdb.run(conn, sql)
        same = askdb.equivalent(gold, result)
        print(
            f"{label:<40} {similarity(GOLD, sql):>9.0%} "
            f"{askdb.usd(result.scalar):>12} {'yes' if same else 'NO':>10}"
        )

    worst_sql = CANDIDATES[0][1]
    equal_sql = CANDIDATES[1][1]
    worst, equal = similarity(GOLD, worst_sql), similarity(GOLD, equal_sql)
    wrong_by = askdb.run(conn, worst_sql).scalar - gold.scalar
    print(
        f"\nRead the two columns against each other.\n\n"
        f"  The best text match, at {worst:.0%}, is the query that forgot the status\n"
        f"  filter. It is wrong by {askdb.usd(wrong_by)}, the entire value of every\n"
        f"  cancelled and pending order.\n\n"
        f"  The worst text match, at {equal:.0%}, is the query that means exactly the\n"
        f"  same thing and returns the identical number. A text-matching eval ranks it\n"
        f"  below the broken one and sends an engineer off to fix a bug that does not\n"
        f"  exist.\n\n"
        f"  So the ranking is not merely noisy, it is inverted on this set. There is no\n"
        f"  similarity threshold that accepts the correct query and rejects the wrong\n"
        f"  one, because the wrong one is more similar. The metric cannot be tuned into\n"
        f"  working; it is measuring the wrong thing.\n"
    )

    print("What the failure actually looks like when you execute it")
    print("-" * 76)
    for label, sql in CANDIDATES:
        result = askdb.run(conn, sql)
        print(f"  {label:<40} {askdb.explain(gold, result)}")

    print(
        "\nTakeaway: execution turns 'these queries look different' into 'this query\n"
        "returns 1.72x the reference', and the second sentence names the bug. The cost\n"
        "is that you now need a database in your eval, seeded with data that makes the\n"
        "failures visible. That is the real price of this method, and it is the reason\n"
        "teams skip it: writing the fixture is work, and a string comparison is free.\n"
        "It is also why their eval passes while their dashboard is wrong."
    )


if __name__ == "__main__":
    print(f"Provider: {askdb.describe()}\n")
    main()
