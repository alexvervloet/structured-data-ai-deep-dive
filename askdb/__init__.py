"""
askdb: asking a database questions in English, and knowing whether the answer is right.

The modules, in the order the course uses them:

    warehouse.py    the tiny SQLite fixture every lesson queries
    generate.py     question -> SQL, at three prompt levels (mock by default)
    execute.py      run a query, record failures as outcomes rather than raising
    compare.py      decide whether two queries returned the same answer
    questions.py    the benchmark: questions, reference SQL, and the trap in each
    evaluate.py     score a suite, broken down by how it failed
    permissions.py  the read-only boundary that a prompt cannot provide

The one big idea: a generated query is a hypothesis, and the database is the only
thing that can settle it.
"""

from .compare import equivalent, explain
from .evaluate import evaluate, report, score_one, summarize
from .execute import Result, run
from .generate import LEVELS, build_prompt, describe, generate, provider_name
from .permissions import analyst_connection, describe_boundary
from .questions import BY_ID, QUESTIONS, Question
from .warehouse import connect, schema_ddl, usd

__all__ = [
    "BY_ID",
    "LEVELS",
    "QUESTIONS",
    "Question",
    "Result",
    "analyst_connection",
    "build_prompt",
    "connect",
    "describe",
    "describe_boundary",
    "equivalent",
    "evaluate",
    "explain",
    "generate",
    "provider_name",
    "report",
    "run",
    "schema_ddl",
    "score_one",
    "summarize",
    "usd",
]
