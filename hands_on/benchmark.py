"""
benchmark.py: the capstone. Every idea in the course, in one runnable harness.

The six lessons each isolated one thing. This runs them together, which is the only
configuration that tells you the truth, because the interesting failures live in the
gaps between them: a system with perfect correctness and no permission boundary, or a
safe one that refuses half the questions it could answer.

What it does:

  * generates SQL for every benchmark question, at each prompt level
  * executes each query through the RESTRICTED connection, not the owner's
  * compares result sets against the reference queries
  * reports accuracy, the verdict breakdown, and a per-category split

The default connection is the analyst's. That is a deliberate choice and it is the
main argument of the capstone: if your eval runs with more privilege than production,
your eval is measuring a system you do not deploy. Pass `--connection owner` to see
the difference, which is a rise in the headline score and a safety problem going
invisible.

    python hands_on/benchmark.py                      # all levels, analyst connection
    python hands_on/benchmark.py --level defined      # one level
    python hands_on/benchmark.py --show-sql           # print every generated query
    python hands_on/benchmark.py --connection owner   # the flattering number
    PROVIDER=claude secrun python hands_on/benchmark.py --level defined   # a real model

Exit status is 0 when the chosen level meets the threshold and 1 otherwise, so this
works as a CI gate on a prompt or model change. That is the point of building it: a
text-to-SQL system without a gate like this drifts, and nobody finds out from the SQL.
"""

import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import askdb
from askdb.evaluate import BLOCKED, CORRECT, VERDICTS
from askdb.permissions import analyst_connection, describe_boundary

THRESHOLD = 0.90


def by_category(outcomes) -> None:
    groups = defaultdict(list)
    for outcome in outcomes:
        groups[outcome.question.category].append(outcome)

    print(f"\n  {'category':<14}{'correct':>10}{'total':>8}   notes")
    print("  " + "-" * 62)
    for category in sorted(groups):
        items = groups[category]
        correct = sum(1 for o in items if o.verdict == CORRECT)
        notes = ", ".join(sorted({o.verdict.lower() for o in items if o.verdict != CORRECT}))
        print(f"  {category:<14}{correct:>10}{len(items):>8}   {notes}")


def run_level(conn, level: str, show_sql: bool) -> dict:
    outcomes = askdb.evaluate(conn, level)
    summary = askdb.summarize(outcomes)

    print(f"\nlevel: {level}")
    print("=" * 70)
    print(
        f"  {summary['accuracy']:.0%} correct ({summary[CORRECT]}/{summary['total']})   "
        + " · ".join(f"{v.lower()} {summary[v]}" for v in VERDICTS if v != CORRECT and summary[v])
    )

    for outcome in outcomes:
        if outcome.verdict != CORRECT:
            print(f"    {outcome.verdict:<12}{outcome.question.id:<24}{outcome.detail}")
        if show_sql:
            print(f"      {outcome.question.id}: {' '.join(outcome.sql.split())[:90]}")

    by_category(outcomes)
    return summary


def interpret(summaries: dict) -> None:
    print("\n\nWhat this run says")
    print("=" * 70)

    levels = list(summaries)
    first, last = summaries[levels[0]], summaries[levels[-1]]
    print(
        f"  Accuracy went from {first['accuracy']:.0%} to {last['accuracy']:.0%} across "
        f"{len(levels)} prompt levels, and\n"
        f"  the entire improvement came from writing things down: what a join to\n"
        f"  order_items does to a total, which statuses count, and what finance means\n"
        f"  by revenue. None of it was a better model.\n"
    )

    blocked = last[BLOCKED]
    if blocked:
        print(
            f"  {blocked} query was refused by the permission boundary. It was correct SQL,\n"
            f"  and the boundary stopped it anyway, which is the system working. Score it\n"
            f"  as its own outcome rather than as an error, and watch the rate: if it\n"
            f"  climbs, the questions arriving at your system are drifting toward data it\n"
            f"  is not allowed to show, and somebody will eventually propose widening the\n"
            f"  permissions to make the errors stop.\n"
        )
    else:
        print(
            "  Nothing was blocked in this run. That is not the same as being safe, it\n"
            "  means nothing asked for restricted data. Keep a question in the suite that\n"
            "  does, so the boundary is exercised on every run rather than assumed.\n"
        )

    print(
        "  The number this harness cannot produce is the one about your warehouse. Four\n"
        "  tiny tables and a mock that answers from a lookup table will not tell you how\n"
        "  a model handles forty tables with inconsistent naming and three date columns\n"
        "  per fact. Point it at a copy of your own schema, write twenty questions your\n"
        "  analysts actually get asked, and rule on what each one means. That week of\n"
        "  work is the entire project."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Execution-based benchmark for generated SQL.")
    parser.add_argument("--level", choices=askdb.LEVELS, help="one prompt level (default: all)")
    parser.add_argument("--connection", choices=("analyst", "owner"), default="analyst",
                        help="which privileges to run the generated SQL with (default: analyst)")
    parser.add_argument("--show-sql", action="store_true", help="print every generated query")
    parser.add_argument("--threshold", type=float, default=THRESHOLD,
                        help=f"accuracy required to exit 0 (default: {THRESHOLD})")
    args = parser.parse_args()

    owner = askdb.connect()
    conn = owner if args.connection == "owner" else analyst_connection()

    print(f"Provider:   {askdb.describe()}")
    print(f"Connection: {args.connection}")
    if args.connection == "analyst":
        print(f"            {describe_boundary()}")
    else:
        print("            unrestricted: this run can read PII and will score it CORRECT")
    print(f"Questions:  {len(askdb.QUESTIONS)}")

    levels = [args.level] if args.level else list(askdb.LEVELS)
    summaries = {level: run_level(conn, level, args.show_sql) for level in levels}
    interpret(summaries)

    final = summaries[levels[-1]]["accuracy"]
    passed = final >= args.threshold
    print(
        f"\n{'PASS' if passed else 'FAIL'}: {levels[-1]} scored {final:.0%} "
        f"against a {args.threshold:.0%} threshold."
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
