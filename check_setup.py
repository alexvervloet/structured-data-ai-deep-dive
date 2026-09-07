"""
check_setup.py: confirm the course runs before you start it.

Run this first. It answers one question, "will the lessons work on this machine?",
and it is quick to satisfy on purpose: the six lessons and the capstone need Python
3.11 or newer and the standard library. No API key, no network, no service, no
third-party package.

The one combination it treats as an error is the interesting one: PROVIDER set to a
real model with no key on the environment. That means somebody meant to benchmark a
real model and would instead get canned answers from the mock, which would look like
a successful run and produce a number describing a lookup table.

Run it:

    python check_setup.py

Exit status is 0 when the course is ready, 1 otherwise, so it also works as a first
CI step.
"""

from __future__ import annotations

import os
import sqlite3
import sys

REQUIRED_PYTHON = (3, 11)
PROVIDER_KEYS = {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY"}


def main() -> int:
    errors: list[str] = []
    notes: list[str] = []

    print("Structured data + AI setup")
    print(f"  Python:  {sys.version.split()[0]}")
    if sys.version_info < REQUIRED_PYTHON:
        errors.append(f"Python {'.'.join(map(str, REQUIRED_PYTHON))} or newer is required")

    print(f"  SQLite:  {sqlite3.sqlite_version}")

    # The permission lesson needs both mechanisms. Neither is exotic, and both have
    # been in SQLite for many years, but a build without the authorizer would fail
    # halfway through lesson 5 rather than here.
    try:
        probe = sqlite3.connect("file:setupcheck?mode=memory&cache=shared", uri=True)
        probe.execute("PRAGMA query_only = ON")
        probe.set_authorizer(lambda *a: sqlite3.SQLITE_OK)
        probe.set_authorizer(None)
        probe.close()
        print("  Enforcement: query_only and authorizer callbacks available")
    except sqlite3.Error as exc:
        errors.append(f"this SQLite build cannot enforce the lesson 5 boundary: {exc}")

    try:
        import askdb

        conn = askdb.connect()
        orders = askdb.run(conn, "SELECT COUNT(*) FROM orders").scalar
        print(f"  Warehouse: seeded, {orders} orders, {len(askdb.QUESTIONS)} benchmark questions")
    except Exception as exc:                     # noqa: BLE001 - report anything here
        errors.append(f"could not build the fixture warehouse: {exc}")

    provider = os.getenv("PROVIDER", "mock").strip().lower()
    if provider in PROVIDER_KEYS:
        key = PROVIDER_KEYS[provider]
        if os.getenv(key):
            print(f"  Provider: {provider} (key present, runs will make real API calls)")
        else:
            errors.append(
                f"PROVIDER={provider} but {key} is not set. The run would silently use "
                f"canned answers. Provide the key, or unset PROVIDER to use the mock "
                f"deliberately."
            )
    else:
        print("  Provider: mock (offline, deterministic, no key needed)")
        notes.append("every lesson and the capstone run offline and free on the mock")

    for note in notes:
        print(f"  note: {note}")
    for error in errors:
        print(f"  ERROR: {error}")

    print("\nReady." if not errors else "\nNot ready.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
