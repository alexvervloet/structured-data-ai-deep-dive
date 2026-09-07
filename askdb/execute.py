"""
askdb/execute.py: run a generated query and come back with something you can score.

The one rule this module exists to enforce: a generated query is not a result until
it has run. Everything upstream (the schema in the prompt, the few-shot examples, how
confident the model sounded) is a hypothesis about what the database will say.

So `run()` never raises on bad SQL. A query that fails to parse, references a missing
column, or times out is not an exception to handle, it is an *outcome to record*. An
eval that crashes on the first malformed query cannot tell you what fraction of
queries are malformed, which is one of the two or three numbers you most want.

Note the connection this module does not open. `run()` takes a connection rather than
making one, because the security decision belongs to the caller and there is exactly
one correct answer for generated SQL: a connection that cannot write. Lesson 5 builds
that connection. Until then the lessons pass the owner's handle, and they say so.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

MAX_ROWS = 1000


@dataclass
class Result:
    """What came back, including the useful case where nothing did."""

    columns: tuple[str, ...] = ()
    rows: tuple[tuple, ...] = ()
    error: str | None = None
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def scalar(self):
        """The single value, for the many analytics questions that return one number."""
        if self.ok and len(self.rows) == 1 and len(self.rows[0]) == 1:
            return self.rows[0][0]
        return None

    def __str__(self) -> str:
        if not self.ok:
            return f"error: {self.error}"
        if not self.rows:
            return "(no rows)"
        head = " | ".join(self.columns)
        body = "\n".join(" | ".join("NULL" if v is None else str(v) for v in r) for r in self.rows[:10])
        more = f"\n... {len(self.rows) - 10} more rows" if len(self.rows) > 10 else ""
        return f"{head}\n{body}{more}"


def run(conn: sqlite3.Connection, sql: str, *, max_rows: int = MAX_ROWS) -> Result:
    """Execute one query and capture whatever happens, including the failures.

    The row cap is not politeness. A generated query with a missing join condition
    produces a cross join, and a cross join on two modest tables is how a reporting
    box runs out of memory at 3am. Cap it, and treat hitting the cap as a signal
    about the query rather than a display problem.
    """
    try:
        cursor = conn.execute(sql)
    except sqlite3.Error as exc:
        return Result(error=f"{type(exc).__name__}: {exc}")

    try:
        rows = cursor.fetchmany(max_rows + 1)
        columns = tuple(d[0] for d in cursor.description or ())
    except sqlite3.Error as exc:            # errors can surface during iteration too
        return Result(error=f"{type(exc).__name__}: {exc}")
    finally:
        # Close it. An open cursor holds a read lock on the tables it touched, and in
        # SQLite's shared-cache mode that lock blocks writers on OTHER connections.
        # Leaving them open is how a harness that only ever reads still manages to
        # deadlock the process that maintains the fixture.
        cursor.close()

    truncated = len(rows) > max_rows
    return Result(
        columns=columns,
        rows=tuple(tuple(r) for r in rows[:max_rows]),
        truncated=truncated,
    )


@dataclass
class ReadOnlyViolation(Exception):
    """Raised by the belt-and-braces check in `askdb.permissions`, never by `run()`."""

    statement: str
    reason: str = field(default="")

    def __str__(self) -> str:
        return f"{self.reason}: {self.statement.strip()[:80]}"
