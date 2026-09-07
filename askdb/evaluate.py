"""
askdb/evaluate.py: score a whole suite by executing it.

One accuracy number is not enough to act on, and this module exists to produce the
breakdown instead. A run that is 60% correct could be any of these systems, and they
need completely different work:

  * 40% of queries fail to parse            -> a formatting or schema-grounding problem
  * 40% run fine and return the wrong rows  -> the dangerous one, nobody notices
  * 40% abstained                           -> honest, cautious, possibly too cautious

The third case is why abstention is scored as its own outcome rather than folded into
"wrong". A system that says "I cannot answer that" has behaved correctly on a question
it could not answer and has behaved *safely* on one it could. Neither is the same as
confidently returning a number that is off by a quarter of a million dollars, and a
metric that cannot tell those apart will push you toward the confident system.

The verdicts:

    CORRECT      rows match the reference, or it abstained on the unanswerable question
    WRONG        it ran and returned different rows: the expensive failure
    ERROR        it did not run at all: cheap, loud, self-announcing
    ABSTAINED    it declined a question it could have answered: cautious, not wrong
    OVERREACHED  it answered the question the schema cannot answer: the worst outcome
    BLOCKED      the permission boundary refused it: correct SQL, refused anyway

BLOCKED only appears when you score through a restricted connection, which lesson 5
argues you should. It is deliberately not counted as correct: the system asked for
something it was not allowed to have, and the fact that a boundary stopped it is a
reason to sleep at night, not a reason to score a point. Watch the number. A rising
BLOCKED rate means the questions reaching your system are drifting toward data it
cannot show, and that is worth knowing before someone widens the permissions to make
the errors go away.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass

from .compare import equivalent, explain
from .execute import Result, run
from .generate import ABSTAIN, generate
from .permissions import is_permission_error
from .questions import QUESTIONS, Question

CORRECT = "CORRECT"
WRONG = "WRONG"
ERROR = "ERROR"
ABSTAINED = "ABSTAINED"
OVERREACHED = "OVERREACHED"
BLOCKED = "BLOCKED"

VERDICTS = (CORRECT, WRONG, ERROR, ABSTAINED, OVERREACHED, BLOCKED)


@dataclass
class Outcome:
    question: Question
    sql: str
    verdict: str
    detail: str = ""
    result: Result | None = None

    @property
    def abstained(self) -> bool:
        return self.sql.upper().startswith(ABSTAIN)


def score_one(conn: sqlite3.Connection, question: Question, sql: str) -> Outcome:
    """Score one generated query against one reference query."""
    abstained = sql.upper().startswith(ABSTAIN)

    if not question.answerable:
        if abstained:
            return Outcome(question, sql, CORRECT, "correctly refused an unanswerable question")
        return Outcome(question, sql, OVERREACHED, "answered a question this schema cannot answer")

    if abstained:
        return Outcome(question, sql, ABSTAINED, "declined a question it could have answered")

    candidate = run(conn, sql)
    if not candidate.ok and is_permission_error(candidate.error):
        return Outcome(question, sql, BLOCKED, candidate.error or "refused", candidate)

    # The reference query runs on the same connection the candidate did. If the
    # boundary blocks the gold query too, that is a benchmark you cannot score here,
    # and it should look broken rather than quietly marking everything wrong.
    gold = run(conn, question.gold_sql)
    if not candidate.ok:
        return Outcome(question, sql, ERROR, candidate.error or "failed", candidate)
    if equivalent(gold, candidate, ordered=question.ordered):
        return Outcome(question, sql, CORRECT, "rows match the reference", candidate)
    return Outcome(
        question, sql, WRONG, explain(gold, candidate, ordered=question.ordered), candidate
    )


def evaluate(
    conn: sqlite3.Connection, level: str = "bare", questions=QUESTIONS
) -> list[Outcome]:
    """Generate and score every question at one prompt level."""
    return [score_one(conn, q, generate(q, level)) for q in questions]


def summarize(outcomes: list[Outcome]) -> dict:
    counts = Counter(o.verdict for o in outcomes)
    total = len(outcomes) or 1
    return {
        "total": len(outcomes),
        "accuracy": counts[CORRECT] / total,
        **{verdict: counts[verdict] for verdict in VERDICTS},
    }


def report(outcomes: list[Outcome], title: str = "") -> None:
    """Print the breakdown. Wrong answers first, because those are the ones that ship."""
    summary = summarize(outcomes)
    if title:
        print(f"\n{title}")
        print("-" * len(title))
    print(
        f"  {summary['accuracy']:.0%} correct  "
        f"({summary[CORRECT]}/{summary['total']})   "
        f"wrong {summary[WRONG]} · error {summary[ERROR]} · "
        f"abstained {summary[ABSTAINED]} · overreached {summary[OVERREACHED]} · "
        f"blocked {summary[BLOCKED]}"
    )
    for outcome in outcomes:
        if outcome.verdict != CORRECT:
            print(f"    {outcome.verdict:12} {outcome.question.id:20} {outcome.detail}")
