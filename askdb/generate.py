"""
askdb/generate.py: turn a question into SQL, at three levels of prompt.

The course needs a model that writes SQL, and it needs to run on a laptop with no
key, deterministically, in CI. So the default is a mock, and the mock is the one
piece of this repository you should be suspicious of. Be clear about what it is:

**The mock is a library of canned queries, not a model.** Its answers were written by
hand to reproduce the mistakes real models actually make on real warehouses: fan-out
joins, forgotten status filters, the wrong date column, ignoring a refunds table,
inventing a table that would make the question answerable. It cannot surprise you,
and a benchmark that cannot surprise you proves nothing about a model.

What it *can* do honestly is teach the machinery. Every number the lessons print is a
real query executed against a real database and compared by rows, so the harness, the
comparison, the failure taxonomy, and the permission boundary are all genuine. Swap in
a real model with `PROVIDER=openai` or `PROVIDER=claude` and the same harness scores
it, which is the point of building the harness. Do that before you believe anything
about how good models are at this. Lesson 2 says so again, louder.

The three prompt levels exist because the arc of the course is a measurement:

    bare       schema only, the version most people ship
    annotated  schema plus the warnings a senior analyst would give a new hire
    defined    annotated plus the metric definitions, written down

Accuracy climbs from `bare` to `defined`. Two failures survive all three levels, and
they are the interesting ones. The definition question stays wrong until the
definition is in the prompt, because no amount of "be careful" substitutes for a
decision nobody has made. And the permissions question stays *answerable* at every
level, because a prompt has never once stopped a query from running.
"""

from __future__ import annotations

import os
import sys

from .warehouse import schema_ddl

LEVELS = ("bare", "annotated", "defined")

# --------------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------------

_ANNOTATIONS = """
NOTES FROM THE ANALYTICS TEAM
- orders.total_cents is the order total. Never sum it across a join to order_items:
  that counts the order once per line item. Aggregate order_items separately.
- Only status = 'completed' counts as a sale. 'pending' has not been paid and
  'cancelled' never will be.
- Money is stored in integer cents.
- If the schema cannot answer the question, output exactly: CANNOT ANSWER: <reason>.
  Do not substitute a question you can answer.
"""

_DEFINITIONS = """
METRIC DEFINITIONS (owned by finance; do not reinterpret)
- "revenue" is gross revenue: SUM(orders.total_cents) WHERE status = 'completed'.
- Revenue is booked on orders.ordered_at, the date the order was placed. It is NOT
  booked on shipped_at.
- "net revenue" or "revenue after refunds" subtracts SUM(refunds.amount_cents).
- A month means [first day, first day of next month), on ordered_at.
"""


def build_prompt(level: str = "bare") -> str:
    """The system prompt at one of the three levels."""
    if level not in LEVELS:
        raise ValueError(f"unknown level {level!r}, expected one of {LEVELS}")
    prompt = (
        "You write SQLite SQL for an analytics warehouse. Output ONE query and nothing "
        "else: no prose, no markdown fences.\n\nSCHEMA\n" + schema_ddl()
    )
    if level in ("annotated", "defined"):
        prompt += "\n" + _ANNOTATIONS
    if level == "defined":
        prompt += "\n" + _DEFINITIONS
    return prompt


# --------------------------------------------------------------------------------
# The mock's canned answers
# --------------------------------------------------------------------------------

# Level `bare`: what a capable model tends to produce from a schema alone. Note that
# these are not stupid queries. Every one of them is the obvious reading of the
# question, which is exactly why this failure mode survives code review.
_BARE = {
    "total_revenue": """
        SELECT SUM(o.total_cents) FROM orders o
        JOIN order_items i ON i.order_id = o.id
        WHERE o.status = 'completed'
    """,
    "revenue_by_country": """
        SELECT c.country, SUM(o.total_cents)
        FROM orders o JOIN customers c ON c.id = o.customer_id
        WHERE o.status = 'completed'
        GROUP BY c.country
    """,
    "top_products": """
        SELECT product, SUM(qty) AS units FROM order_items
        GROUP BY product ORDER BY units DESC, product ASC LIMIT 3
    """,
    "march_revenue": """
        SELECT SUM(total_cents) FROM orders
        WHERE status = 'completed' AND shipped_at >= '2025-03-01' AND shipped_at < '2025-04-01'
    """,
    "net_revenue": "SELECT SUM(total_cents) FROM orders WHERE status = 'completed'",
    "avg_order_value": "SELECT AVG(total_cents) FROM orders",
    "nigeria_customers": "SELECT COUNT(*) FROM customers WHERE country = 'Nigeria'",
    "pending_orders": "SELECT COUNT(*) FROM orders WHERE status = 'pending'",
    "customer_emails": "SELECT email FROM customers",
    "best_channel": """
        SELECT ch.name, SUM(o.total_cents) FROM orders o
        JOIN marketing_channels ch ON ch.id = o.channel_id
        GROUP BY ch.name ORDER BY 2 DESC LIMIT 1
    """,
    # Half the question is answerable (country is right there), which is exactly what
    # makes it dangerous: the query runs, returns one row per country, and the numbers
    # are of a column that has nothing to do with satisfaction.
    "satisfaction_by_country": """
        SELECT c.country, AVG(c.satisfaction_score) FROM customers c GROUP BY c.country
    """,
    # The plausible wrong answer: counts orders, calls them tickets, returns a number
    # that looks completely reasonable and answers a different question.
    "support_tickets": """
        SELECT COUNT(*) AS tickets_closed FROM orders
        WHERE ordered_at >= '2025-03-01' AND ordered_at < '2025-04-01'
    """,
}

# Level `annotated`: the mechanical mistakes go away. The two that remain are the two
# a prompt cannot fix.
_ANNOTATED = dict(_BARE)
_ANNOTATED.update({
    "total_revenue": "SELECT SUM(total_cents) FROM orders WHERE status = 'completed'",
    "top_products": """
        SELECT i.product, SUM(i.qty) AS units
        FROM order_items i JOIN orders o ON o.id = i.order_id
        WHERE o.status = 'completed'
        GROUP BY i.product ORDER BY units DESC, i.product ASC LIMIT 3
    """,
    "avg_order_value": "SELECT AVG(total_cents) FROM orders WHERE status = 'completed'",
    "best_channel": "CANNOT ANSWER: no table in this schema records marketing channels.",
    "satisfaction_by_country": "CANNOT ANSWER: no satisfaction or survey data in this schema.",
    "support_tickets": "CANNOT ANSWER: this schema has orders, not support tickets.",
})

# Level `defined`: the definitions land the two remaining analytical questions.
# `customer_emails` is unchanged, and stays unchanged forever, which is the point.
_DEFINED = dict(_ANNOTATED)
_DEFINED.update({
    "march_revenue": """
        SELECT SUM(total_cents) FROM orders
        WHERE status = 'completed' AND ordered_at >= '2025-03-01' AND ordered_at < '2025-04-01'
    """,
    "net_revenue": """
        SELECT (SELECT SUM(total_cents) FROM orders WHERE status = 'completed')
             - (SELECT COALESCE(SUM(amount_cents), 0) FROM refunds)
    """,
})

_MOCK = {"bare": _BARE, "annotated": _ANNOTATED, "defined": _DEFINED}

ABSTAIN = "CANNOT ANSWER"


# --------------------------------------------------------------------------------
# Provider selection, with the loud fallback this series uses everywhere
# --------------------------------------------------------------------------------

_KEYS = {"openai": ["OPENAI_API_KEY"], "claude": ["ANTHROPIC_API_KEY"]}
_MODELS = {"openai": "gpt-5.4-mini", "claude": "claude-haiku-4-5"}
_warned = False


def _configured() -> str:
    return os.getenv("PROVIDER", "mock").strip().lower()


def provider_name() -> str:
    """The active provider, degrading to the mock loudly when a key is missing.

    A silent fallback would be genuinely dangerous here: you would run a benchmark,
    read an accuracy number, and believe it described a model. Set PROVIDER_STRICT=1
    to make the missing key an error instead, which is what you want in CI.
    """
    global _warned
    p = _configured()
    if p in _KEYS and not all(os.getenv(k) for k in _KEYS[p]):
        if os.getenv("PROVIDER_STRICT"):
            return p
        if not _warned:
            _warned = True
            print(
                f"\n!  PROVIDER={p} is set but {', '.join(_KEYS[p])} is not on the "
                f"environment.\n   Falling back to the offline mock, whose answers are "
                f"canned. Any accuracy\n   number below describes this file, not a model."
                f"\n   Hard error instead: PROVIDER_STRICT=1\n",
                file=sys.stderr,
            )
        return "mock"
    return p


def describe() -> str:
    p, configured = provider_name(), _configured()
    if p == "mock" and configured != "mock":
        return f"mock (FALLBACK from PROVIDER={configured}: no key; answers are canned)"
    if p == "mock":
        return "mock (offline, deterministic, canned answers, no key)"
    return f"{p} (model={_MODELS.get(p, '?')})"


def generate(question, level: str = "bare") -> str:
    """The question in, one SQL string (or an abstention) out."""
    if level not in LEVELS:
        raise ValueError(f"unknown level {level!r}, expected one of {LEVELS}")
    provider = provider_name()
    if provider == "mock":
        return _MOCK[level].get(question.id, f"{ABSTAIN}: the mock has no answer for this.").strip()
    return _generate_live(question, level, provider).strip()


def _generate_live(question, level: str, provider: str) -> str:
    """Ask a real model. Kept small on purpose; the harness is the interesting part."""
    system, user = build_prompt(level), question.text
    if provider == "openai":
        from openai import OpenAI

        response = OpenAI().chat.completions.create(
            model=_MODELS["openai"],
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        text = response.choices[0].message.content or ""
    elif provider == "claude":
        import anthropic

        message = anthropic.Anthropic().messages.create(
            model=_MODELS["claude"],
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in message.content if block.type == "text")
    else:
        raise ValueError(f"unknown provider {provider!r}")
    return _strip_fences(text)


def _strip_fences(text: str) -> str:
    """Models add markdown fences no matter how firmly the prompt forbids them.

    Worth pausing on: the prompt says "no markdown fences", the model does it anyway,
    and the fix is four lines of Python rather than a stronger sentence in the prompt.
    That ratio holds for most output-format problems, and it is the same lesson as
    lesson 5 in a much less dangerous costume.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines)
    return text.strip()
