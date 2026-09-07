"""
Lesson 1: what the model is allowed to know, and what that buys you.

A model asked to write SQL for a database it has never seen will invent table names.
Not because it is careless, but because "write SQL for our sales data" has no answer
without a schema, and the model answers anyway. So you put the schema in the prompt,
and this is the first thing every text-to-SQL tutorial tells you.

The tutorials usually stop there, and the sentence they stop on is wrong. Grounding
the prompt in the schema does not make invented names impossible. It makes them
*rarer*. The model still holds the schema as text it was asked to attend to, next to
everything else in the context, with no mechanism enforcing that its output refers to
anything real. Between "much rarer" and "impossible" sits every production incident.

What this lesson actually measures is the next question, the one worth asking: given
that the schema is in there, what else in the prompt changes the answer? Three levels:

    bare       the schema, nothing else
    annotated  plus the warnings a senior analyst gives a new hire on day one
    defined    plus the metric definitions, written down and owned

Predict before running: which of the ten benchmark questions does each level get
right? Specifically, decide whether "how much revenue did we book in March" is a
question a better prompt can fix.

Next: lesson 2 explains why we are scoring these by running them.
See README section 1 and TEXTBOOK section 20.2.

Run it:

    python examples/01_schema_grounding.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import askdb


def show_prompts() -> None:
    print("What the model sees\n" + "=" * 70)
    bare = askdb.build_prompt("bare")
    print(f"  bare       {len(bare):>5} characters   the schema and the output rule")
    for level in ("annotated", "defined"):
        text = askdb.build_prompt(level)
        print(f"  {level:<10} {len(text):>5} characters   +{len(text) - len(bare)} over bare")
    print(
        "\n  The schema is the same in all three. What changes is how much of the\n"
        "  analytics team's working knowledge is written down where the model can\n"
        "  read it, instead of living in the heads of people who review the query.\n"
    )


def one_question_three_ways() -> None:
    question = askdb.BY_ID["total_revenue"]
    conn = askdb.connect()
    print(f'Question: "{question.text}"\n' + "=" * 70)

    for level in askdb.LEVELS:
        sql = askdb.generate(question, level)
        outcome = askdb.score_one(conn, question, sql)
        answer = outcome.result.scalar if outcome.result else None
        shown = askdb.usd(answer) if isinstance(answer, (int, float)) else "-"
        print(f"\n  [{level}] -> {outcome.verdict}, answer {shown}")
        print("      " + " ".join(sql.split())[:100])

    reference = askdb.run(conn, question.gold_sql).scalar
    bare_answer = askdb.run(conn, askdb.generate(question, "bare")).scalar
    print(
        f"\n  The reference answer is {askdb.usd(reference)}. The bare prompt is off by "
        f"{bare_answer / reference - 1:.0%},\n"
        "  and the query that produced it is not obviously broken: it joins two tables\n"
        "  that are genuinely related, filters on the status everyone agrees about, and\n"
        "  sums the column literally named total_cents. Lesson 3 takes it apart.\n"
    )


def whole_suite() -> dict[str, float]:
    conn = askdb.connect()
    print("The whole benchmark, at each level\n" + "=" * 70)
    accuracy = {}
    for level in askdb.LEVELS:
        outcomes = askdb.evaluate(conn, level)
        askdb.report(outcomes, f"level: {level}")
        accuracy[level] = askdb.summarize(outcomes)["accuracy"]
    return accuracy


if __name__ == "__main__":
    print(f"Provider: {askdb.describe()}\n")
    show_prompts()
    one_question_three_ways()
    accuracy = whole_suite()
    print(
        f"\nTakeaway: prompt work is real work and it moved accuracy from "
        f"{accuracy['bare']:.0%} to {accuracy['defined']:.0%} on\n"
        "this suite. Two things about that number deserve suspicion, though, and the\n"
        "rest of the course is mostly about them.\n\n"
        "The jump from annotated to defined came from writing down what 'revenue' means.\n"
        "That was not a prompting insight. It was someone in finance making a decision\n"
        "and someone else recording it (lesson 4).\n\n"
        "And the suite now scores 100% on a system that will still hand every customer\n"
        "email address to anyone who asks for it, because accuracy cannot see that\n"
        "(lesson 5)."
    )
