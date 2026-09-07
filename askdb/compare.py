"""
askdb/compare.py: decide whether two queries gave the same answer.

This is the module that makes the whole course possible, and the reason is worth
stating plainly: **you cannot score generated SQL by looking at it.**

Two queries that share almost no text can be identical in meaning.

    SELECT country, SUM(total_cents) FROM orders WHERE status='completed' GROUP BY country
    SELECT c.country, SUM(o.total_cents) FROM orders o JOIN customers c ON c.id=o.customer_id
      WHERE o.status='completed' GROUP BY c.country

And two queries that differ by nine characters can disagree about hundreds of
thousands of dollars: drop `WHERE status='completed'` and you have counted cancelled
orders as revenue. String similarity ranks that pair as nearly identical. So does an
LLM judge reading the SQL, most of the time, because the queries *look* alike.

Run both. Compare the rows. That is the whole idea, and it is why this dive keeps a
database around instead of a rubric.

Three judgment calls, each of which will bite you if you get it wrong:

**Order.** `GROUP BY country` returns the same facts in whatever order the planner
felt like. Comparing ordered lists marks a correct query wrong. So the default is
set comparison, and `ordered=True` is for questions that actually asked for a
ranking, where "top 5 by revenue" is wrong if the five are in the wrong order.

**Column names.** `SUM(total_cents)`, `revenue`, and `total` are the same column with
three names, and none of them is more correct. Compare values positionally and ignore
the headers. The cost is that a query returning the right numbers under misleading
names still passes, which is a real limitation and the reason a human reads the
queries that pass before anyone ships them.

**Numeric tolerance.** Integer cents compare exactly, which is one more argument for
storing money as integers. Floats do not, so `1234.56` and `1234.5600000000001` must
compare equal or you will spend an afternoon debugging a rounding difference that was
never a bug.
"""

from __future__ import annotations

from .execute import Result

TOLERANCE = 1e-6


def _normalize(value):
    """Collapse the differences that are formatting rather than meaning."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, str):
        return value.strip()
    return value


def _key(row: tuple) -> tuple:
    return tuple(str(_normalize(v)) for v in row)


def _rows_equal(a: tuple, b: tuple) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        nx, ny = _normalize(x), _normalize(y)
        if isinstance(nx, float) and isinstance(ny, float):
            if abs(nx - ny) > TOLERANCE:
                return False
        elif nx != ny:
            return False
    return True


def equivalent(gold: Result, candidate: Result, *, ordered: bool = False) -> bool:
    """Did the candidate query return the same answer as the reference query?

    A failed candidate is never equivalent, including when the gold query also
    failed. Two broken queries are not agreement; if the gold query errors, the
    benchmark is broken and you want that to look like a failure, loudly.
    """
    if not gold.ok or not candidate.ok:
        return False
    if len(gold.rows) != len(candidate.rows):
        return False
    if ordered:
        return all(_rows_equal(g, c) for g, c in zip(gold.rows, candidate.rows))

    remaining = list(candidate.rows)
    for g in gold.rows:
        for i, c in enumerate(remaining):
            if _rows_equal(g, c):
                del remaining[i]
                break
        else:
            return False
    return not remaining


def explain(gold: Result, candidate: Result, *, ordered: bool = False) -> str:
    """Why the comparison failed, in the words you would use to a colleague.

    "Not equivalent" is a useless eval output. The whole value of running the queries
    is that you can say *how* the answers differed, and the shape of the difference
    usually names the bug: more rows than expected is a missing filter or a fan-out
    join, fewer is an over-restrictive one, same rows with bigger numbers is almost
    always a join multiplying a total.
    """
    if not candidate.ok:
        return f"query failed: {candidate.error}"
    if not gold.ok:
        return f"reference query failed, the benchmark is broken: {gold.error}"
    if equivalent(gold, candidate, ordered=ordered):
        return "equivalent"

    if len(gold.rows) != len(candidate.rows):
        direction = "more" if len(candidate.rows) > len(gold.rows) else "fewer"
        return (
            f"{len(candidate.rows)} rows, expected {len(gold.rows)}: {direction} rows than "
            f"the reference, so look for a missing or extra filter, or a join that "
            f"multiplied them"
        )

    if len(gold.rows) == 1 and len(gold.rows[0]) == 1 and len(candidate.rows[0]) == 1:
        g, c = gold.rows[0][0], candidate.rows[0][0]
        if isinstance(g, (int, float)) and isinstance(c, (int, float)) and g:
            return f"same shape, different value: got {c}, expected {g} ({c / g:.2f}x)"
        return f"same shape, different value: got {c!r}, expected {g!r}"

    if ordered and sorted(map(_key, gold.rows)) == sorted(map(_key, candidate.rows)):
        return "right rows, wrong order, and this question asked for an order"

    return "same row count, different values"
