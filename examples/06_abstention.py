"""
Lesson 6: the answer that is worth more than a correct answer.

"Which marketing channel drove the most revenue last quarter?" is a reasonable
business question. This warehouse cannot answer it. There is no channels table, no
campaign identifier, no attribution of any kind, and no join path that reaches one.

There are exactly two things a system can do here. It can say so. Or it can produce
SQL, because producing SQL is what it does, and a plausible query against tables that
do not exist is well within reach.

The second behavior is worse than a wrong number, and it is worth being precise about
why. A query naming `marketing_channels` fails loudly, which is survivable. The real
danger is the near miss: a schema that contains a `campaigns` table meant for
something else entirely, or a `source` column populated for 3% of rows in 2023. Then
the query runs, returns rows, and answers a question nobody asked. Nothing in the
output says so. Someone reallocates a budget.

So abstention gets scored as its own outcome in `askdb/evaluate.py`, and the
benchmark carries a question that has no correct SQL. The verdicts that matter:

    CORRECT      refused the question it could not answer
    OVERREACHED  answered it anyway
    ABSTAINED    refused a question it could have answered

That last one is the cost, and pretending it is free would be dishonest. Push a system
toward caution and it starts declining questions it could have handled, which is
annoying in a way users notice immediately and metrics notice not at all. Abstention
is a dial with a real trade-off on both ends, not a free win, and the only way to set
it is to measure both sides. This lesson prints both.

One thing that makes abstention unusually workable here compared to open-ended chat:
the ground truth is checkable. Whether the schema can answer a question is a fact
about the schema. You can build the abstention half of the benchmark by writing
questions about columns you know are absent, which is a rare case of a safety property
you can test cheaply and exhaustively.

Predict before running: at which prompt level does the system start refusing, and what
in that level's text is doing the work?

Previous: lesson 5 added the boundary. Next: the capstone runs all of it at once.
See README section 6 and TEXTBOOK section 20.7.

Run it:

    python examples/06_abstention.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import askdb
from askdb.evaluate import ABSTAINED, CORRECT, OVERREACHED

# The word each unanswerable question turns on, so the check below is a real check
# against the schema rather than a claim in a print statement.
MISSING_CONCEPT = {
    "best_channel": "channel",
    "satisfaction_by_country": "satisfaction",
    "support_tickets": "ticket",
}


def the_unanswerable_question() -> None:
    conn = askdb.connect()
    question = askdb.BY_ID["best_channel"]
    print(f'Question: "{question.text}"\n' + "=" * 70)
    print("  This schema has customers, orders, order_items, and refunds. Nothing in\n"
          "  it records where a customer came from.\n")

    for level in askdb.LEVELS:
        sql = askdb.generate(question, level)
        outcome = askdb.score_one(conn, question, sql)
        print(f"  [{level}] -> {outcome.verdict}")
        print(f"      {' '.join(sql.split())[:96]}")

    print(
        "\n  The bare prompt invents `marketing_channels` and joins it on a `channel_id`\n"
        "  that orders does not have. Read that query without the schema in front of\n"
        "  you and it is completely convincing: sensible table name, sensible join,\n"
        "  sensible aggregate, correct ORDER BY and LIMIT for a 'which one is biggest'\n"
        "  question. It is confident, well-formed, and about a database that does not\n"
        "  exist.\n\n"
        "  What changed at the annotated level is one sentence in the prompt giving the\n"
        "  model a licensed way out, and the licence is the part that matters. A model\n"
        "  asked only to write SQL will write SQL. Tell it that 'CANNOT ANSWER: reason'\n"
        "  is an acceptable output and refusing stops being a failure to comply.\n"
    )


def the_cost_of_caution() -> None:
    """Abstention is a dial. Show both ends of it, not just the flattering one."""
    conn = askdb.connect()
    print("Both sides of the dial\n" + "=" * 70)

    outcomes = askdb.evaluate(conn, "defined")
    answerable = [o for o in outcomes if o.question.answerable]
    unanswerable = [o for o in outcomes if not o.question.answerable]

    refused_wrongly = sum(1 for o in answerable if o.verdict == ABSTAINED)
    answered_wrongly = sum(1 for o in unanswerable if o.verdict == OVERREACHED)
    print(f"  questions this schema can answer:    {len(answerable)}")
    print(f"    of those, wrongly refused:         {refused_wrongly}")
    print(f"  questions it cannot answer:          {len(unanswerable)}")
    print(f"    of those, wrongly answered:        {answered_wrongly}")
    print(
        "\n  Both numbers belong on the same dashboard. A system tuned only against the\n"
        "  second one drifts toward refusing everything, which scores beautifully on\n"
        "  safety and gets switched off by its users within a fortnight.\n"
    )


def more_absent_columns() -> None:
    """The cheap way to grow this half of a benchmark."""
    print("Building the abstention set\n" + "=" * 70)
    schema = askdb.schema_ddl().lower()
    print("  Questions written by naming things the schema does not contain:\n")
    for question_id, concept in MISSING_CONCEPT.items():
        question = askdb.BY_ID[question_id]
        verdict = "in schema" if concept in schema else "absent   "
        print(f"    {concept:<14} {verdict}  {question.text}")
    print(
        "\n  Each of these is checkable: grep the schema. That is what makes abstention\n"
        "  testable in a way most safety properties are not, and it means there is no\n"
        "  excuse for a text-to-SQL benchmark that contains only answerable questions.\n"
        "  A suite where every question has an answer cannot measure the failure mode\n"
        "  that costs the most to discover in production.\n"
    )


if __name__ == "__main__":
    print(f"Provider: {askdb.describe()}\n")
    the_unanswerable_question()
    the_cost_of_caution()
    more_absent_columns()
    print(
        "Takeaway: put questions with no answer in the benchmark and score refusing\n"
        "them as correct. Then measure the other direction too, because a system that\n"
        "refuses what it could have answered has failed differently, not less. The\n"
        "engineering that makes this real is unglamorous: give the model an explicit,\n"
        "named way to decline, and make sure the surrounding code passes that through\n"
        "as an abstention instead of trying to parse it as SQL."
    )
