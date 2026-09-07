"""
askdb/warehouse.py: the small, deliberately awkward database every lesson runs against.

SQLite, from the standard library, built fresh in memory each run. No service, no
container, no credentials. The whole course is `python examples/01_....py`.

The data is tiny and hand-written because every number on screen has to be checkable
by hand. When a lesson claims a query double-counts revenue by $1,299.98, you can add
up the four rows yourself and see it. Generated data would make the same point in a
way nobody can verify, which is the wrong kind of teaching.

Four tables, chosen so the classic enterprise failures are all reachable:

    customers    (a PII column, for the permissions lesson)
    orders       (a status column and TWO date columns, for the definition lesson)
    order_items  (a one-to-many child, for the fan-out lesson)
    refunds      (so gross revenue and net revenue disagree, on purpose)

Things planted in the seed data, each one load-bearing for a later lesson:

  * Order 1002 has three line items, and 1004 and 1005 have two each. Join `orders`
    to `order_items`, sum `orders.total_cents`, and every one of those orders is
    counted once per line item: completed revenue inflates from $2,979.94 to
    $5,119.91. This is the single most common wrong answer in generated analytics
    SQL, and lesson 3 is entirely about it.
  * Order 1004 was placed on 2025-03-31 and shipped on 2025-04-01, so "March
    revenue" has two defensible answers that differ by $450. Lesson 4.
  * Order 1007 is `cancelled` and order 1009 is `pending`. Any query that forgets a
    status filter quietly includes money nobody paid.
  * Order 1003 was refunded in full and order 1005 partially, so gross revenue and
    net revenue differ by $829.97. Neither is wrong; they answer different questions.
  * `customers.email` exists so lesson 5 has something the analyst role must not be
    able to read.
  * There is no table anywhere describing marketing channels or ad spend, which is
    what lesson 6 asks for. The right answer to that question is to refuse it.
"""

from __future__ import annotations

import sqlite3

# A shared-cache in-memory database rather than a plain ":memory:" one, so that a
# SECOND connection can be opened to the same data. That is not a detail: lesson 5
# hands generated SQL a different connection with fewer privileges, and "a different
# connection" is only meaningful if both see the same rows. The database lives as long
# as one connection to it stays open.
DB_URI = "file:askdb_warehouse?mode=memory&cache=shared"

# Dropped first so `connect()` can be called more than once in a process (the tests do)
# without tripping over tables that already exist.
_RESET = """
DROP TABLE IF EXISTS refunds;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
"""

TABLES = """
CREATE TABLE customers (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    country     TEXT    NOT NULL,
    email       TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE orders (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    status       TEXT    NOT NULL CHECK (status IN ('completed','pending','cancelled')),
    ordered_at   TEXT    NOT NULL,
    shipped_at   TEXT,
    total_cents  INTEGER NOT NULL
);

CREATE TABLE order_items (
    id          INTEGER PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(id),
    product     TEXT    NOT NULL,
    qty         INTEGER NOT NULL,
    unit_cents  INTEGER NOT NULL
);

CREATE TABLE refunds (
    id            INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(id),
    amount_cents  INTEGER NOT NULL,
    refunded_at   TEXT    NOT NULL
);
"""

SCHEMA = _RESET + TABLES

CUSTOMERS = [
    (1, "Ada Okafor",     "Nigeria",     "ada@example.com",    "2024-11-02"),
    (2, "Bruno Salgado",  "Brazil",      "bruno@example.com",  "2024-12-14"),
    (3, "Chen Wei",       "Singapore",   "chen@example.com",   "2025-01-08"),
    (4, "Dara Nilsson",   "Sweden",      "dara@example.com",   "2025-01-21"),
    (5, "Emeka Balogun",  "Nigeria",     "emeka@example.com",  "2025-02-03"),
]

# (id, customer_id, status, ordered_at, shipped_at, total_cents)
ORDERS = [
    (1001, 1, "completed", "2025-03-04", "2025-03-06",  49999),
    (1002, 2, "completed", "2025-03-11", "2025-03-13",  64999),   # 3 line items: fan-out
    (1003, 3, "completed", "2025-03-15", "2025-03-17",  52999),   # fully refunded
    (1004, 4, "completed", "2025-03-31", "2025-04-01",  45000),   # straddles the month
    (1005, 1, "completed", "2025-03-22", "2025-03-25",  38999),   # partially refunded
    (1006, 5, "completed", "2025-04-02", "2025-04-04",  29999),
    (1007, 2, "cancelled", "2025-03-19", None,          89999),   # never paid
    (1008, 3, "completed", "2025-04-09", "2025-04-11",  15999),
    (1009, 4, "pending",   "2025-04-28", None,          72999),   # not paid yet
]

# (id, order_id, product, qty, unit_cents)
ORDER_ITEMS = [
    (1, 1001, "Standing desk",      1, 49999),
    (2, 1002, "Mechanical keyboard", 1, 14999),
    (3, 1002, "27-inch monitor",     1, 39999),
    (4, 1002, "Monitor arm",         1, 10001),
    (5, 1003, "Ergonomic chair",     1, 52999),
    (6, 1004, "Desk lamp",           2,  9000),
    (7, 1004, "Cable tray",          1, 27000),
    (8, 1005, "Laptop stand",        1, 12999),
    (9, 1005, "Docking station",     1, 26000),
    (10, 1006, "Webcam",             1, 29999),
    (11, 1007, "Conference speaker", 1, 89999),
    (12, 1008, "USB-C hub",          1, 15999),
    (13, 1009, "Standing desk",      1, 72999),
]

# (id, order_id, amount_cents, refunded_at)
REFUNDS = [
    (1, 1003, 52999, "2025-03-24"),   # full refund
    (2, 1005, 29998, "2025-04-02"),   # partial refund
]


def connect() -> sqlite3.Connection:
    """A fresh in-memory warehouse, seeded identically every time.

    Returns a read-write connection: this is the owner's handle, used to build the
    database and by lessons that need to demonstrate what an unrestricted connection
    permits. Lesson 5 hands generated SQL a *different*, restricted connection, which
    is the entire point of that lesson.
    """
    conn = sqlite3.connect(DB_URI, uri=True)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", CUSTOMERS)
    conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?)", ORDERS)
    conn.executemany("INSERT INTO order_items VALUES (?,?,?,?,?)", ORDER_ITEMS)
    conn.executemany("INSERT INTO refunds VALUES (?,?,?,?)", REFUNDS)
    conn.commit()
    return conn


def schema_ddl() -> str:
    """The schema as the model should see it: structure, no rows.

    Lesson 1 is about what belongs in here. Note what is missing on purpose: no row
    counts, no sample values, no comments explaining that `total_cents` is in cents.
    Lesson 1 adds those and measures whether they helped.
    """
    return TABLES.strip()


def usd(cents: int | float) -> str:
    """Format cents as dollars. Every lesson prints money; none of them should
    reimplement this, and none of them should print bare cents at a reader."""
    return f"${cents / 100:,.2f}"
