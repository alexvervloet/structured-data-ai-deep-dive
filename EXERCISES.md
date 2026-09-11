# Exercises

Predict before you run. The point of each of these is the gap between what you expected
and what happened, and you only get that gap if you commit to an answer first.

Each section pairs with one lesson. Answers are collapsed; open them after you've
written yours down.

---

## Section 1: Schema grounding

**Predict.** The `bare` prompt contains the full schema. It still gets the total revenue
question wrong. Given that every table and column it needs is right there in front of
it, what kind of mistake is left to make?

<details><summary>▸ Answer</summary>

The kind that comes from knowing the schema and not the data. The generated query joins
`orders` to `order_items`, which is a completely reasonable thing to do with two tables
in that relationship, and it inflates the total by 1.72x. Nothing in the DDL says how
many line items a typical order has, or that summing a parent column across that join
double counts.

The general form: a schema tells the model what exists. It doesn't say what's true.
Cardinality, which statuses mean money, whether refunds are already netted out, which
of two date columns the business uses. All absent, all decisive.
</details>

**Recall.** Name the two things the `defined` level adds over `annotated`, and say which
one is a prompting technique.

<details><summary>▸ Answer</summary>

It adds the metric definitions: revenue is gross, booked on `ordered_at`, and net
revenue subtracts refunds. Neither is a prompting technique. Both are decisions someone
in finance made, transcribed into the prompt.

Worth sitting with, because the accuracy jump from 83% to 100% is entirely attributable
to them. If you reported that as "prompt engineering improved accuracy by 17 points" you'd
be describing the work incorrectly, and the next team to try it would go looking
for the technique instead of the meeting.
</details>

---

## Section 2: Execution-based evaluation

**Predict.** Two candidate queries. One drops `WHERE status = 'completed'` from the
reference. The other rewrites the reference completely, using an alias and
`WHERE NOT (status = 'cancelled' OR status = 'pending')`. Rank them by text similarity
to the reference, then by correctness.

<details><summary>▸ Answer</summary>

The rankings are opposite. The broken one is a 67% text match and returns $1,629.98 too
much. The correct one is a 43% match and returns the identical answer.

The consequence is stronger than "string matching is noisy". Because the wrong query is
*more* similar than the right one, there's no threshold anywhere that accepts one and
rejects the other. The metric can't be tuned into working. It's measuring the wrong
property, and the only repair is to measure a different one.
</details>

**Do.** Add a fourth candidate to `CANDIDATES` in `examples/02_execution_based_eval.py`
that is *very* close in text to the reference and returns a different answer. How small
a change can you make?

<details><summary>▸ Answer</summary>

One character will do it: change `'completed'` to `'completed '` and the filter matches
nothing. `SUM` over no rows returns NULL rather than 0, so the answer isn't merely
wrong, it's a different type, and any code adding it to another figure will fail
somewhere far away from the cause.

Comparisons like `>=` to `>` on a date boundary, or `AND` to `OR` in a two-clause WHERE,
are similarly tiny and similarly total.
</details>

---

## Section 3: The fan-out join

**Predict.** Seven completed orders, eleven line items between them. Before running,
what inflation factor do you expect from summing `orders.total_cents` across the join?

<details><summary>▸ Answer</summary>

Not 11/7 = 1.57x. The actual figure is 1.72x.

Each order is over-counted in proportion to its own line count, so the result is an
average weighted by order value. Here the weighting works against you: order 1002 has
both the most line items and the largest total, pushing the error above the row ratio.
Flip that (many small orders with many lines, one large order with one line) and the
error lands below it.

Which is the real lesson. The size of this bug depends on which rows happen to have
many children, so it moves month to month and there's no constant that corrects it.
</details>

**Do.** Write a query that answers "total completed revenue" correctly *while still
joining* `order_items`. Then say why you wouldn't ship it.

<details><summary>▸ Answer</summary>

Aggregate the child side to one row per parent first:

```sql
SELECT SUM(o.total_cents)
FROM orders o
JOIN (SELECT order_id, COUNT(*) AS lines FROM order_items GROUP BY order_id) i
  ON i.order_id = o.id
WHERE o.status = 'completed';
```

You wouldn't ship it because the join contributes nothing to the answer. `orders`
already holds the total. The best fix for a fan-out bug is usually to delete the join,
and a query carrying a join it doesn't need is a fan-out bug waiting for the next
person to add a `SUM`.
</details>

**Stretch.** Add the row-count check from the lesson to `askdb/evaluate.py` as a warning
on any candidate query whose join changes the row count and which aggregates a column
from the parent side. Then decide whether it should be a warning or a failure.

---

## Section 4: Metric definitions

**Predict.** The `annotated` prompt warns about joins, statuses, units, and abstention,
in four carefully written sentences. Does it get "revenue booked in March" right?

<details><summary>▸ Answer</summary>

No. It picks `shipped_at` and comes in $450 low, because one order was placed on March
31st and shipped April 1st.

None of the four warnings is a ruling on when revenue is booked, and no number of
additional careful sentences would be, because the information isn't the kind that can
be inferred. Someone has to decide. The `defined` level works for exactly one reason:
somebody did, and wrote it down.
</details>

**Recall.** You're handed a wrong number from a text-to-SQL system. What's the first
question to ask, before looking at the model, the prompt, or the retrieval?

<details><summary>▸ Answer</summary>

Would two analysts, given this question, have written the same query?

If the answer is no, the system is working correctly and the specification is missing.
Chasing it as a model problem will consume a sprint and produce a prompt that encodes
one analyst's preference without anyone agreeing to it.
</details>

**Do.** Add a benchmark question whose gold query encodes a ruling you disagree with.
Run the suite. Notice that the suite is now enforcing a decision, which is the point of
one, and that changing the number means changing the gold query where someone will see
it in review.

---

## Section 5: Permissions

**Predict.** The `defined` prompt scores 100%. What does that number not cover?

<details><summary>▸ Answer</summary>

Whether the system should have been allowed to do what it did. Correctness asks whether
the answer was right. `SELECT email FROM customers` is a completely correct answer to
"list every customer's email address", and it's the query you least want your system to
run successfully.

Scored on the analyst connection, the same run reports 92% with one BLOCKED, and the
missing 8% is the safety property becoming visible in the metric.
</details>

**Predict.** The authorizer denies `customers.email`. Which of these get through?

```sql
SELECT c.email AS contact FROM customers AS c
SELECT (SELECT email FROM customers WHERE id = 1)
SELECT UPPER(email) FROM customers
SELECT email FROM customers WHERE 1 = 0
select EMAIL from CUSTOMERS
SELECT * FROM customers
```

<details><summary>▸ Answer</summary>

None. Including the last one, because `SELECT *` resolves to a column list that includes
`email`, and including the fourth, which would have returned no rows anyway; the
authorizer fires during statement preparation, before anything runs.

The reason all six fail is that nothing in `askdb/permissions.py` reads the SQL. SQLite
calls the authorizer with the tables and columns the parsed statement resolved to, so
aliases, subqueries, functions, case, and whitespace are all already gone by then.

Try writing a regex that catches all six and nothing else. The exercise is worth ten
minutes precisely because of how it goes.
</details>

**Do.** Add a `salary` column to `customers`, add it to `DENIED_COLUMNS`, and write a
question whose only correct answer requires it. What verdict should the benchmark give?

<details><summary>▸ Answer</summary>

BLOCKED, and that's the right outcome rather than a gap. The question is answerable by
the schema and not answerable by this role, which is a distinction worth having in the
output. A system that reports it as an ERROR loses the information that the query was
fine and the permissions stopped it, and that's exactly the signal you want to watch.
</details>

---

## Section 6: Abstention

**Predict.** Which of these three unanswerable questions produces the most dangerous
wrong answer, and why?

1. "Which marketing channel drove the most revenue?"
2. "What is the average customer satisfaction score by country?"
3. "How many support tickets did we close in March?"

<details><summary>▸ Answer</summary>

The third, then the second, then the first.

The first invents `marketing_channels`, which fails loudly. Nothing bad happens.

The second is worse because half of it is answerable: `country` is right there, so the
query has a real GROUP BY and a shape that looks correct, and only the measure is
fictional.

The third is the worst, because counting orders in March returns a number that is
completely plausible, correctly computed, and about a different thing. Nothing in the
output indicates that "tickets" and "orders" aren't the same concept. This is the near
miss, and it's the reason abstention matters more than one more point of accuracy.
</details>

**Recall.** What single change to the prompt makes the model start refusing?

<details><summary>▸ Answer</summary>

Telling it that refusal is an allowed output: `If the schema cannot answer the question,
output exactly: CANNOT ANSWER: <reason>`.

A model asked only to write SQL will write SQL, because that's compliance. Giving it a
named, licensed way to decline changes refusal from a failure to follow instructions
into following them. The surrounding code then has to pass that through as an abstention
rather than trying to parse it as SQL, which is the unglamorous half.
</details>

**Do.** Push abstention too far. Add "If you are not completely certain, output CANNOT
ANSWER" to the prompt and rerun the suite. Watch the ABSTAINED count rise on questions
the system used to get right, and decide what you'd tell a user whose reasonable
question was declined.

---

## Capstone

**Predict.** `--connection owner` and the default both run the same queries against the
same data. Which reports a higher number, and which one would you put in a document?

<details><summary>▸ Answer</summary>

The owner connection reports 100%; the analyst connection reports 92%. The lower one is
the number that describes the system you deploy, so it's the only one worth reporting.

The general rule is worth more than this example. An eval that runs with more privilege
than production is measuring a system you don't ship, and it'll always report a
better number than the truth, which is the direction that never prompts anyone to
investigate.
</details>

**Do.** Point it at your own schema. Copy the DDL for six or eight tables people
actually query into `askdb/warehouse.py`, seed enough rows that a fan-out is visible,
and write ten questions your analysts get asked, with a gold query for each.

The tenth question is where the work is. Somewhere around the sixth you'll hit one
where writing the reference query requires deciding what a word means, and you won't
be the person who gets to decide. That's the project.

---

### Where to take it next

Run the whole suite against a real model with `PROVIDER=claude` or `PROVIDER=openai` and
compare it against the mock's numbers. Everything the mock told you about the harness
holds. Nothing it told you about model behavior does, and this is the run that replaces
it.
