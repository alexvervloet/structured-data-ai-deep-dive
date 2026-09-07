"""
askdb/questions.py: the benchmark, which is the actual work.

A text-to-SQL eval is a set of questions paired with SQL somebody trusts. Writing
that set is most of the effort and all of the value, and it is the part teams skip
because it looks like typing rather than engineering.

Two things make the reference query "gold", and only one of them is technical. It has
to run and return the right rows, which you can check. It also has to encode a
*decision* about what the question means, which you cannot check, only make. "Revenue
in March" is not a well-formed question until someone rules on whether an order placed
on March 31st and shipped on April 1st is March revenue. The gold query is where that
ruling gets written down, and that is why the benchmark belongs to the analytics team
rather than to whoever is building the model layer.

Each question carries the failure it is designed to catch, because a suite that only
contains questions the system already answers correctly measures nothing. Roughly half
of these are traps.

`answerable=False` marks the question the schema cannot answer. Getting that one right
means producing no SQL at all, which lesson 6 argues is a skill worth more than one
more point of accuracy on the questions that are answerable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    gold_sql: str
    category: str
    ordered: bool = False      # does the question ask for a ranking?
    answerable: bool = True    # can this schema answer it at all?
    trap: str = ""             # the mistake this question exists to catch


QUESTIONS: tuple[Question, ...] = (
    Question(
        id="total_revenue",
        text="What is our total completed revenue?",
        gold_sql="SELECT SUM(total_cents) FROM orders WHERE status = 'completed'",
        category="aggregate",
        trap="joining order_items multiplies each order's total by its line-item count",
    ),
    Question(
        id="revenue_by_country",
        text="What is completed revenue by country?",
        gold_sql="""
            SELECT c.country, SUM(o.total_cents)
            FROM orders o JOIN customers c ON c.id = o.customer_id
            WHERE o.status = 'completed'
            GROUP BY c.country
        """,
        category="join",
        trap="grouping by a column from the wrong side of the join",
    ),
    Question(
        id="top_products",
        text="What are the top 3 products by units sold?",
        # "Sold" means an order that completed. A unit on a cancelled order was not
        # sold, and a gold query that leaves this implicit is not gold, it is a second
        # ambiguous question. Ties break on product name so the result is stable;
        # a ranking whose order depends on the planner cannot be scored on order.
        gold_sql="""
            SELECT i.product, SUM(i.qty) AS units
            FROM order_items i JOIN orders o ON o.id = i.order_id
            WHERE o.status = 'completed'
            GROUP BY i.product
            ORDER BY units DESC, i.product ASC
            LIMIT 3
        """,
        category="ranking",
        ordered=True,
        trap="counting units from cancelled orders, or ranking with no LIMIT",
    ),
    Question(
        id="march_revenue",
        text="How much revenue did we book in March 2025?",
        # The ruling: revenue is booked when the order is placed, not when it ships.
        # Order 1004 (placed 2025-03-31, shipped 2025-04-01) is March revenue. Change
        # this line and you have changed what the company means by the word, which is
        # a conversation with finance, not a prompt edit.
        gold_sql="""
            SELECT SUM(total_cents) FROM orders
            WHERE status = 'completed' AND ordered_at >= '2025-03-01' AND ordered_at < '2025-04-01'
        """,
        category="definition",
        trap="using shipped_at instead of ordered_at, a $450 difference nobody notices",
    ),
    Question(
        id="net_revenue",
        text="What is our completed revenue after refunds?",
        gold_sql="""
            SELECT (SELECT SUM(total_cents) FROM orders WHERE status = 'completed')
                 - (SELECT COALESCE(SUM(amount_cents), 0) FROM refunds)
        """,
        category="definition",
        trap="ignoring the refunds table entirely and reporting gross as net",
    ),
    Question(
        id="avg_order_value",
        text="What is the average value of a completed order?",
        gold_sql="SELECT AVG(total_cents) FROM orders WHERE status = 'completed'",
        category="aggregate",
        trap="averaging every order, including cancelled ones nobody paid for",
    ),
    Question(
        id="nigeria_customers",
        text="How many customers do we have in Nigeria?",
        gold_sql="SELECT COUNT(*) FROM customers WHERE country = 'Nigeria'",
        category="lookup",
        trap="none; a suite of only hard questions cannot show a regression on easy ones",
    ),
    Question(
        id="pending_orders",
        text="How many orders are currently pending?",
        gold_sql="SELECT COUNT(*) FROM orders WHERE status = 'pending'",
        category="lookup",
    ),
    Question(
        id="customer_emails",
        text="List every customer's email address.",
        gold_sql="SELECT email FROM customers",
        category="permissions",
        trap="answerable SQL that the analyst role must not be allowed to run",
    ),
    Question(
        id="best_channel",
        text="Which marketing channel drove the most revenue last quarter?",
        gold_sql="",          # there is no correct SQL; see answerable
        category="abstention",
        answerable=False,
        trap="inventing a channels table, or silently answering a different question",
    ),
    Question(
        id="satisfaction_by_country",
        text="What is the average customer satisfaction score by country?",
        gold_sql="",
        category="abstention",
        answerable=False,
        trap="country exists, so half the question is answerable and invites a guess",
    ),
    Question(
        id="support_tickets",
        text="How many support tickets did we close in March?",
        gold_sql="",
        category="abstention",
        answerable=False,
        trap="counting orders instead, which is a plausible-looking wrong answer",
    ),
)

BY_ID = {q.id: q for q in QUESTIONS}
