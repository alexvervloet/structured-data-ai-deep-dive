"""
askdb/permissions.py: the part a prompt cannot do.

Ask any team running text-to-SQL how they stop the model from writing to the database
and a majority will quote you a line from their system prompt. Something like:

    READ-ONLY: SELECT statements only. Never write INSERT/UPDATE/DELETE/DROP.

That line is worth having. It lowers how often the model reaches for a write, which
saves you failed queries. It is not a control. It is a request addressed to the least
trustworthy component in the system, evaluated by that component, with no mechanism
behind it. The model can ignore it through ordinary error, and anyone who can get text
into the model's context can talk it out of the instruction on purpose, which is what
the [prompt injection dive](https://github.com/alexvervloet/prompt-injection-deep-dive)
is about.

The control is a connection that cannot write. Then the instruction becomes what it
should have been all along: a hint that improves the success rate, sitting on top of a
boundary that holds when the hint fails.

This module builds that boundary with two mechanisms SQLite enforces itself, neither
of which reads the query text:

**`PRAGMA query_only = ON`** makes the connection refuse every write. The check lives
in the engine, below SQL parsing, so there is no clever spelling of DELETE that gets
past it. In Postgres this is `SET TRANSACTION READ ONLY`, and better, a role created
without write privileges in the first place.

**An authorizer callback** that denies specific columns. SQLite calls it during
statement preparation for every table and column a query touches, and a denial stops
the statement before it runs. This is column-level authorization, and it is the reason
`SELECT email FROM customers` fails here while `SELECT name FROM customers` succeeds.
In Postgres you get the same result with `GRANT SELECT (id, name, country) ON customers
TO analyst`, and row-level security for the per-tenant case.

The habit worth taking away is smaller than the machinery: decide what the query is
allowed to touch *before* you know what the query is. Every design where the answer
depends on inspecting the generated SQL is a blocklist, and blocklists lose.
"""

from __future__ import annotations

import sqlite3

from .warehouse import DB_URI

# Columns the analyst role may not read. Deliberately a short, boring list of the
# things that would hurt: contact details here, and in a real warehouse the salary
# column, the medical fields, the raw payment identifiers.
DENIED_COLUMNS = {("customers", "email")}


def _authorizer(action: int, arg1, arg2, db_name, trigger):
    """Called by SQLite for every table and column a statement touches.

    Returning SQLITE_DENY refuses the whole statement at preparation time, so the
    query never executes and no row is read. Note what this function does *not* do:
    look at the SQL. It is handed the objects the parsed statement resolved to, which
    is why aliases, subqueries, views, and creative whitespace do not get around it.
    """
    if action == sqlite3.SQLITE_READ and (arg1, arg2) in DENIED_COLUMNS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def analyst_connection(*, deny_columns: bool = True) -> sqlite3.Connection:
    """A connection with the privileges generated SQL should get: read, and less.

    This is the handle to hand anything that runs model-written queries. The owner's
    connection from `warehouse.connect()` is for building the fixture and for the
    reference queries in the benchmark, which are written by people and reviewed.
    """
    conn = sqlite3.connect(DB_URI, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    if deny_columns:
        conn.set_authorizer(_authorizer)
    return conn


def describe_boundary() -> str:
    denied = ", ".join(f"{t}.{c}" for t, c in sorted(DENIED_COLUMNS))
    return (
        f"analyst connection: writes refused by PRAGMA query_only; "
        f"reads denied on {denied} by authorizer callback"
    )
