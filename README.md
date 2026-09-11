# Structured Data + AI: A Guided Deep Dive

Most of what a company actually knows is in a database, not a document. So the request
arrives eventually: let people ask questions in English and have a model write the SQL.
The demo works on the first afternoon, which is the problem, because everything that
makes it dangerous shows up later and quietly.

This course is about the later part. It builds a text-to-SQL system and then does the
work that separates a demo from something you'd let a finance team read: executing
the generated SQL against a real database and comparing the rows, catching the join
that silently multiplies revenue, discovering that "revenue" was never defined, putting
a permission boundary somewhere a prompt can't reach, and teaching the thing to refuse
questions the schema can't answer.

The one big idea:

> **A generated query is a hypothesis. The database is the only thing that can settle it.**

Everything follows from taking that literally. You can't score SQL by reading it, so
the eval keeps a database. You can't trust a prompt to enforce read-only, so the
connection does. You can't tell whether "March revenue" is right without a ruling on
what March revenue means, so the benchmark stores the ruling.

Every lesson runs offline, deterministically, on the standard library. No key, no
service, no container. Point it at a real model when you want to measure one.

[TEXTBOOK.md](TEXTBOOK.md) is the lecture that goes with this lab manual, and
[EXERCISES.md](EXERCISES.md) turns each lesson into a prediction you make before you
run it. Either order works.

---

## An honest word about the mock

The default model is a lookup table. Its answers were hand-written to reproduce the
mistakes real models make on real warehouses, and it can't surprise you, which means
**no accuracy number in this repository tells you anything about how good models are at
text-to-SQL.** That isn't what it's for.

What's real is everything around it: the database, the queries, the execution, the
row-by-row comparison, the failure taxonomy, and the permission boundary. Those are the
parts you'd build yourself, and they're the parts worth learning. When you want a
number about a model, set `PROVIDER` and run the same harness against it. The harness
is the deliverable.

---

## What you'll build

```text
question in English
      │
      ▼
  prompt  ── schema ── analyst notes ── metric definitions
      │                                        │
      ▼                                        │  the part that is not prompting
  generated SQL                                │
      │
      ├── CANNOT ANSWER ──────────────► scored as abstention
      │
      ▼
  restricted connection ── writes refused, PII columns denied
      │                          │
      │                          └────────────► scored as blocked
      ▼
  rows ──── compared against the reference query's rows
      │
      ▼
  verdict: correct / wrong / error / abstained / overreached / blocked
```

---

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python check_setup.py
```

`check_setup.py` should print "Ready." It needs Python 3.11+ and nothing else.

To run against a real model instead of the mock:

```bash
pip install -e '.[claude]'                 # or '.[openai]'
PROVIDER=claude secrun python hands_on/benchmark.py --level defined
```

`check_setup.py` treats `PROVIDER` set with no key as an error rather than falling back
quietly, because a benchmark that silently scores canned answers is worse than one that
doesn't run.

---

## 1. What the model is allowed to know

Putting the schema in the prompt is the first thing every tutorial says, and the
sentence it usually comes with is wrong: grounding makes invented table names *rarer*,
not impossible. What's worth measuring is what else in the prompt changes the answer.
Three levels, from a bare schema to written-down metric definitions.

```bash
python examples/01_schema_grounding.py
```

Accuracy goes from 33% to 100% across the three levels. Both ends of that are
misleading in ways the rest of the course unpicks.

---

## 2. Why you can't score SQL by reading it

The tempting eval compares the generated query against a reference query as text. It's
cheap and it fails in both directions at once. On this set the ranking is *inverted*:
the query that forgot `WHERE status = 'completed'` is a 67% text match and wrong by
$1,629.98, while the query that means exactly the same thing matches at 43%.

```bash
python examples/02_execution_based_eval.py
```

There's no similarity threshold that separates them, because similarity isn't
measuring the thing you care about. Run the query, compare the rows.

---

## 3. The join that multiplies your revenue

Join `orders` to `order_items` and sum `orders.total_cents`, and each order is counted
once per line item. Completed revenue inflates from $2,979.94 to $5,119.91. The query
looks correct, the join condition *is* correct, and the number is 1.72x too big.

```bash
python examples/03_join_fanout.py
```

The lesson shows the duplication row by row, three correct alternatives, and the
one-query check that catches it: did the join change the row count?

---

## 4. The query is right and the answer is still wrong

"How much revenue did we book in March?" carries at least three unstated decisions:
booked on order date or ship date, gross or net of refunds, and whether pending counts.
This warehouse yields five distinct defensible numbers for the one word, the widest pair
73% apart.

```bash
python examples/04_metric_definitions.py
```

This is the ceiling on prompt engineering for analytics, and it's hard. The
`annotated` prompt is full of good advice and still picks the wrong date column,
because none of that advice is a decision about when revenue is booked. What fixes it
is finance's ruling written down, which is a different input rather than a better prompt.

---

## 5. The eval says 100% and the system isn't safe

The `defined` prompt scores 100%. It'll also hand over every customer email address,
because a correctness metric only asks whether what the system did was right, never
whether it should have been allowed to.

```bash
python examples/05_permissions.py
```

`READ-ONLY: SELECT only` in a system prompt is worth keeping and isn't a control. It's
a request, in text, addressed to the least trustworthy component in the system, and
evaluated by that same component. The control is `PRAGMA query_only` plus an authorizer
callback that denies `customers.email` during statement preparation. Neither reads the
query text, which is why an alias, a join, and a subquery all fail identically where a
regex would have missed all three. In Postgres this is a role with `GRANT SELECT` on
named columns and no write privileges.

---

## 6. Refusing to answer

"Which marketing channel drove the most revenue?" has no answer in this schema. A system
that produces plausible SQL anyway is worse than one that returns a wrong number,
because the wrong number is at least about your data.

```bash
python examples/06_abstention.py
```

Abstention is scored as its own outcome, in both directions: refusing what you can't
answer is correct, and refusing what you could have answered is a real cost that a
safety-only metric will happily push you toward.

---

## Capstone: the benchmark

```bash
python hands_on/benchmark.py                      # all levels, restricted connection
python hands_on/benchmark.py --level defined      # one level
python hands_on/benchmark.py --show-sql           # every generated query
python hands_on/benchmark.py --connection owner   # the flattering number
```

Everything at once: generate, execute through the restricted connection, compare rows,
report by verdict and by category, exit non-zero below a threshold so it gates a change
in CI.

The default connection is the analyst's, and that's the capstone's argument. **If your
eval runs with more privilege than production, it's measuring a system you don't
deploy.** Compare the two runs: `--connection owner` reports 100% and the permission
failure disappears from the output entirely.

---

## From this repo to your warehouse

The shortcuts that make this course free and readable are the ones a real system
replaces:

| Here | In production |
|------|---------------|
| Four tables, hand-seeded | Your schema, or a subset of it with realistic cardinality |
| SQLite in memory | The warehouse, with a role created for this purpose |
| `PRAGMA query_only` + authorizer | `GRANT SELECT (col, …)`, no write grants, row-level security per tenant |
| 12 questions written for the lesson | 20-50 questions your analysts are actually asked, with rulings |
| Metric definitions in the prompt | A semantic layer (dbt metrics, Cube, LookML) the model queries |
| A canned mock | The model you're choosing between, scored on the same suite |
| One shot per question | Retry on error, feeding the database's message back in |
| No result shown to a human | The query displayed beside its answer, always, for the person who has to trust it |

The last row isn't a small one. Every system in this space that works long-term shows
the SQL to the person reading the number, because the reader is the last defense against
a query that is confident, well-formed, and about the wrong thing.

---

## File map

```
check_setup.py              ← run first
README.md                   ← this lab manual
TEXTBOOK.md                 ← the lecture (Chapter 25)
EXERCISES.md                ← predict, then run
LESSONS.md                  ← what surprised us while building this
askdb/
  warehouse.py              ← the SQLite fixture, seeded so each failure is visible
  generate.py               ← question -> SQL, three prompt levels, mock or real model
  execute.py                ← run a query; failures are outcomes, not exceptions
  compare.py                ← same answer or not, by rows
  questions.py              ← the benchmark, and the trap in each question
  evaluate.py               ← verdicts: correct/wrong/error/abstained/overreached/blocked
  permissions.py            ← the read-only, column-denying connection
examples/
  01_schema_grounding.py    ← three prompt levels, measured
  02_execution_based_eval.py← why text comparison is inverted on this set
  03_join_fanout.py         ← $2,979.94 becomes $5,119.91
  04_metric_definitions.py  ← five numbers, one word
  05_permissions.py         ← 100% correct and still unsafe
  06_abstention.py          ← refusing, and the cost of refusing too much
hands_on/
  benchmark.py              ← capstone: the whole harness, with a CI gate
tests/                      ← pins the fixture's numbers so the prose cannot drift
```

---

## Where this sits in the series

The lecture chapter is [Chapter 25](TEXTBOOK.md) of the
[AI Engineering Textbook](https://github.com/alexvervloet/ai-engineering-deep-dive).
The dives it leans on most:

- [Evals](https://github.com/alexvervloet/evals-deep-dive): this is one execution-based
  eval built end to end. The general discipline, judges, significance, and CI gates, is
  there. Read it first or after; both work.
- [Prompt Engineering](https://github.com/alexvervloet/prompt-engineering-deep-dive):
  lesson 05 of that dive writes the text-to-SQL prompt. Lessons 1 and 4 here are what
  happens when you measure it.
- [GenAI Security](https://github.com/alexvervloet/genai-security-deep-dive) and
  [Prompt Injection](https://github.com/alexvervloet/prompt-injection-deep-dive):
  lesson 5 is one instance of their central claim, that the model is an untrusted
  principal and not a security boundary.
- [AI Data Engineering](https://github.com/alexvervloet/ai-data-engineering-deep-dive):
  the same permissions argument, applied to a retrieval corpus rather than a warehouse.
