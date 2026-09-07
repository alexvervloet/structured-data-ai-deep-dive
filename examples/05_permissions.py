"""
Lesson 5: the eval says 100% and the system is not safe.

Run lesson 1 to the end and the `defined` prompt scores 100% on the benchmark. Every
question answered, every number matching its reference. By the standard of the last
four lessons this system is finished.

It will also hand every customer's email address to anyone who asks, and delete your
orders table if a model ever decides that is what the user wanted. Accuracy cannot see
either of those, because both are things the system is *permitted* to do, and a
correctness metric only measures whether what it did was right.

So this lesson is about a different axis. Not "is the answer correct" but "what is
this query allowed to touch", and the answer has to be decided before the query
exists.

The usual approach is a line in the system prompt:

    READ-ONLY: SELECT statements only. Never write INSERT/UPDATE/DELETE/DROP.

Keep that line. It genuinely reduces how often the model reaches for a write, and
fewer failed queries is worth having. Just be exact about what it is: a request, in
text, addressed to the component you trust least, evaluated by that same component,
with nothing behind it. It fails through ordinary model error, and it fails on purpose
whenever untrusted text reaches the context, which is the entire subject of the
[prompt injection dive](https://github.com/alexvervloet/prompt-injection-deep-dive).

The control is a connection that cannot write. `askdb/permissions.py` builds one with
two mechanisms SQLite enforces itself:

  * `PRAGMA query_only = ON`, which refuses writes below the SQL parser, so there is
    no spelling of DELETE that gets through.
  * an authorizer callback that denies `customers.email` during statement preparation,
    which is column-level authorization. The query never runs and no row is read.

Neither mechanism looks at the query text. That is the property that matters, and it
is what separates a control from a filter: nothing about aliases, subqueries, views,
comments, or unusual whitespace changes the outcome, because the check happens after
the statement has been resolved to actual tables and columns.

In Postgres this is a role with `GRANT SELECT` on the columns it may read and no write
privileges anywhere, plus row-level security for the per-tenant case. Same idea, and
the one you would actually deploy.

Predict before running: the model produces `SELECT email FROM customers`, which is
valid SQL that answers the question exactly. What happens on each connection, and
which of the two results should show up in your eval?

Previous: lesson 4 was about undefined questions. Next: lesson 6, refusing to answer.
See README section 5 and TEXTBOOK section 20.6.

Run it:

    python examples/05_permissions.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import askdb
from askdb.permissions import analyst_connection, describe_boundary

ATTEMPTS = [
    ("an ordinary analytics question", "SELECT COUNT(*) FROM orders WHERE status = 'completed'"),
    ("a column the analyst may read", "SELECT name, country FROM customers LIMIT 2"),
    ("the PII the model was asked for", "SELECT email FROM customers"),
    ("PII behind an alias and a join", """
        SELECT c.email AS contact FROM customers AS c
        JOIN orders o ON o.customer_id = c.id WHERE o.status = 'completed'
    """),
    ("PII inside a subquery", "SELECT (SELECT email FROM customers WHERE id = 1)"),
    ("a destructive write", "DELETE FROM orders"),
    ("a write dressed up", "UPDATE orders SET total_cents = 0 WHERE 1 = 1"),
    ("dropping a table", "DROP TABLE refunds"),
]


def run_both_ways() -> None:
    owner = askdb.connect()
    analyst = analyst_connection()

    print(f"  {describe_boundary()}\n")
    print(f"  {'attempt':<34}{'owner connection':<22}{'analyst connection'}")
    print("  " + "-" * 74)
    for label, sql in ATTEMPTS:
        analyst_result = askdb.run(analyst, sql)
        owner_result = askdb.run(owner, sql)
        destructive = not sql.strip().upper().startswith("SELECT")
        if destructive:
            # Actually run it rather than claiming what would happen, then rebuild the
            # fixture. The owner connection really does delete your orders, and a
            # lesson about enforcement should not be asserting its central claim.
            owner_word = "ALLOWED" if owner_result.ok else "failed"
            owner.commit()
            owner.close()          # release the write lock before rebuilding
            owner = askdb.connect()
        else:
            owner_word = "allowed" if owner_result.ok else "failed"
        analyst_word = "allowed" if analyst_result.ok else "BLOCKED"
        print(f"  {label:<34}{owner_word:<22}{analyst_word}")

    print(
        "\n  Every row in the right-hand column is enforced by SQLite, not by anything\n"
        "  that read the SQL. Note rows four and five in particular: aliasing the column\n"
        "  and burying it in a subquery change the text completely and change the\n"
        "  outcome not at all. A regex over the query string would have missed both.\n"
    )


def what_the_prompt_promised() -> None:
    print("What the prompt says, and what the prompt does\n" + "=" * 70)
    prompt = askdb.build_prompt("annotated")
    print("  The annotated prompt contains this instruction:\n")
    print('    "If the schema cannot answer the question, output exactly: CANNOT ANSWER"')
    print(f"\n  It does not contain a read-only rule at all, and adding one would not\n"
          f"  change a single row of the table above. The prompt is {len(prompt)} characters of\n"
          f"  advice to a component that may or may not follow it.\n")

    question = askdb.BY_ID["customer_emails"]
    for level in askdb.LEVELS:
        sql = askdb.generate(question, level)
        print(f"  {level:<10} produced: {' '.join(sql.split())}")
    print(
        "\n  All three levels produce the same query, because it is the correct answer to\n"
        "  the question that was asked. There is no prompt that reliably prevents this,\n"
        "  and there should not need to be one. The model is not the place where this\n"
        "  decision belongs.\n"
    )


def scored_two_ways() -> None:
    print("The same question, scored two ways\n" + "=" * 70)
    conn = askdb.connect()
    analyst = analyst_connection()
    question = askdb.BY_ID["customer_emails"]
    sql = askdb.generate(question, "defined")

    print(f"  correctness eval (owner connection):  {askdb.score_one(conn, question, sql).verdict}")
    blocked = askdb.run(analyst, sql)
    print(f"  same query on the analyst connection: {'allowed' if blocked.ok else 'BLOCKED'}"
          f"  ({blocked.error})")
    print(
        "\n  Both of these are true at once, and that is the lesson. The query is correct.\n"
        "  The query is refused. A benchmark that only measures correctness reports a\n"
        "  perfect score on a system whose safety it never examined, so run your eval\n"
        "  through the restricted connection and let a blocked query count as a\n"
        "  distinct outcome. Then 'the model tried to read PII' becomes a number you\n"
        "  watch instead of an incident you discover.\n"
    )


if __name__ == "__main__":
    print(f"Provider: {askdb.describe()}\n")
    print("Two connections to the same database\n" + "=" * 70)
    run_both_ways()
    what_the_prompt_promised()
    scored_two_ways()
    print(
        "Takeaway: decide what a query may touch before you know what the query is.\n"
        "Every design where the answer depends on inspecting generated SQL is a\n"
        "blocklist, and blocklists lose to the next spelling. Give the thing that runs\n"
        "model-written queries a role that cannot write and cannot read what it should\n"
        "not, and the prompt's read-only line goes back to being what it always was: a\n"
        "useful hint sitting on top of a boundary that holds when the hint fails."
    )
