# Chapter 25: The Database Settles It

*This is the textbook chapter for the Structured Data + AI deep dive, a bonus dive that slots after [Evals](../evals-deep-dive/TEXTBOOK.md) and pairs with [GenAI Security](../genai-security-deep-dive/TEXTBOOK.md). The [README](README.md) is the lab manual; this is the lecture. It covers why generated SQL cannot be scored by reading it, the three failure classes that account for most wrong numbers, the one failure that is not a model problem at all, and where the boundary goes.*

---

## 25.1 The demo that works on the first afternoon

Text-to-SQL has an unusual property among AI features: the prototype is genuinely easy. Put the schema in a prompt, ask for a query, run it. On a small schema with clean naming, a good model gets most questions right, and the first demo is convincing enough that someone asks when it can go to the finance team.

That prototype is not a small version of the production system. It is a different system that happens to produce the same artifact. The gap between them is not model quality, and it is worth naming the four things that actually fill it, because they are the chapter:

You cannot tell whether a generated query is right by looking at it. You will hit a class of bug that inflates numbers rather than breaking them, so nothing surfaces an error. You will discover that half the questions people ask have no defined answer, and the system has been picking one. And you will need the model to be unable to do things, which is not a property text can have.

None of that is about the model. All of it is about what surrounds the model, which is the general shape of this whole series and unusually stark here.

## 25.2 Why the query is a hypothesis

Start with evaluation, because everything else depends on being able to measure.

The obvious approach is to compare the generated query against a reference query written by an analyst. It is cheap, it needs no database, it runs in CI in milliseconds. It also fails in both directions simultaneously, which is worth appreciating as a piece of engineering pathology.

It marks correct queries wrong, because SQL is expressive and one question has many faithful spellings. Aliases or none, a join or a correlated subquery, `IN (...)` or a chain of `OR`, `NOT (a OR b)` in place of `= c`. All return identical rows and share little text.

And it marks catastrophic queries right, because the text carrying the meaning can be tiny. Delete `WHERE status = 'completed'` from a revenue query and you have added every cancelled and never-paid order to the total. Nine characters. A string comparison sees a near-perfect match.

The lab measures both effects on one small set and finds the ranking *inverted*: the broken query scores 67% similar to the reference and the semantically identical one scores 43%. That is worse than a noisy metric. There is no threshold that accepts the correct query and rejects the wrong one, so no amount of tuning fixes it, and the reason is that similarity was never measuring the property in question.

The LLM-judge version deserves the same scrutiny rather than a free pass. Handing both queries to a strong model with a rubric is better than string matching, and it fails in the same direction, because it is also reading text. The difference between two queries that disagree by a quarter of a million dollars often does not appear in either query; it appears in the data, in which rows have three line items and which statuses were never paid. A reader without the database cannot see it. Neither can a reader with a very large context window.

So: run both queries, compare the rows. This is called execution-based evaluation, and it is the standard in the academic benchmarks (Spider, BIRD) for exactly this reason. The price is that your eval now needs a database, seeded with data that makes failures visible, and that price is why teams skip it. Writing the fixture is real work. A string comparison is free. It is also why their eval is green while their dashboard is wrong.

Three judgment calls hide inside "compare the rows", each of which will bite. Row order must be ignored by default, because `GROUP BY` returns facts in whatever order the planner chose, and comparing ordered lists marks correct queries wrong; but it must be respected when the question asked for a ranking, since "top 5" is wrong if the five are misordered. Column names must be ignored, because `SUM(total_cents)`, `revenue`, and `total` are one column with three names; the cost is that a query returning right numbers under misleading headers passes, which is a genuine limitation and the reason a person still reads the queries that pass. And numeric comparison needs a tolerance for floats, which is one more argument for storing money as integer cents.

## 25.3 The bug that inflates instead of breaking

Now the failure that accounts for more wrong analytics numbers than any other, and which almost never surfaces as an error.

A warehouse has parents and children: an order and its line items, a customer and their orders, a campaign and its impressions. Join a parent to its children and the parent's row repeats, once per child. Aggregate a parent column across that join and you have aggregated it once per child. In the lab's tiny fixture, completed revenue goes from $2,979.94 to $5,119.91, a 1.72x inflation, from a query whose join condition is entirely correct.

Three things make this the dangerous one.

It is invisible in review. The query is short, the join is between two tables that genuinely are related, the filter is the one everyone agrees on, and the summed column is the one literally named `total_cents`. There is nothing to point at.

It inflates rather than errors. A query that crashes gets fixed in ten minutes. A query that returns a larger number than expected gets believed, because revenue going up is the outcome everyone wanted, and the number has no obvious upper bound to violate.

And the size of the error is data-dependent, so it moves. The inflation factor is a weighted average, weighted by how many children each parent happens to have, so it changes month to month and cannot be corrected with a constant. A number that was close enough last quarter can be badly wrong this one, with no code change in between.

The fixes are ordinary: do not join what you do not need, since the parent table already holds the total; aggregate the child side to one row per parent before joining; or, least good, aggregate over a distinct parent key. The durable fix is not a fix at all, it is a benchmark question whose gold answer this bug gets wrong, so it cannot come back quietly.

Worth carrying to every other join: after any join, ask whether the row count changed. If it did, any aggregate over a column from the one side is now counting some rows twice. That single comparison catches most of these, and it is cheap enough to put in the harness rather than trusting a reviewer to remember.

## 25.4 The failure that is not a model problem

Then there is the class of wrong answer where the query is correct, the join is right, the filter is right, and the number is still not the one to report.

"How much revenue did we book in March" sounds precise. It contains at least three unstated rulings. Is revenue booked when the order is placed or when it ships, given that some orders straddle the month boundary? Is it gross, or net of refunds? Do pending orders count, which everyone denies until a forecast needs them to? The lab's four tables yield five distinct defensible numbers for that one word, the widest pair 73% apart, and every query producing them is correct SQL that would pass any review checking syntax, joins, and filters.

The model cannot derive the answer, and this is the important part: not because it is not smart enough, but because the answer is not in the schema, the data, or the question. It is in a decision someone made in a meeting, or never made. A system that must produce a query will pick one of the five, silently, consistently enough that nobody notices, until a second team asks the same question through a different route and gets a different number.

This is the ceiling on prompt engineering for analytics, and it is a hard ceiling, which the lab demonstrates rather than asserts. The `annotated` prompt carries four carefully written warnings about joins, statuses, units, and abstention, and it still picks the wrong date column, because "be careful about dates" is not a date column. The `defined` prompt gets it right, and the only thing that level adds is finance's ruling written down. That is not a better prompt in any interesting sense. It is a different input.

The name for writing those rulings down is a semantic layer, or a metric store: revenue defined once, in one place, with an owner, and every query derived from that definition rather than re-deriving it. dbt metrics, Cube, LookML, and Malloy are all versions of the idea, and they predate the current interest in text-to-SQL by years. The AI-specific claim is small and worth stating plainly: a text-to-SQL system on a warehouse with defined metrics works considerably better than one without, and neither the model nor the prompt is what changed. If you are being asked to add natural-language querying to a warehouse where nobody can say what revenue means, the honest sequencing advice is that you have been handed the second half of a project.

The diagnostic is quick. Before blaming the model for a wrong number, ask whether two analysts given the same question would have written the same query. If they would not, the system is working correctly and the specification is missing.

## 25.5 What a prompt cannot do

The last failure is not about correctness at all, and it is the one where this chapter meets [Chapter 20](../genai-security-deep-dive/TEXTBOOK.md).

Ask a team how they stop the model writing to the database and most will quote a line from their system prompt, something close to `READ-ONLY: SELECT statements only. Never write INSERT/UPDATE/DELETE/DROP.` That line is worth keeping. It lowers how often the model reaches for a write, and fewer failed queries is a real benefit.

It is not a control. It is a request, expressed in text, addressed to the least trustworthy component in the system, and evaluated by that same component, with no mechanism behind it. It fails through ordinary model error. It fails deliberately whenever untrusted text reaches the context, which is the subject of [Chapter 7](../prompt-injection-deep-dive/TEXTBOOK.md) and is not exotic: a question can arrive from a user, a ticket, an email, or a row in the very database being queried.

The control is a connection that cannot write. In the lab that is `PRAGMA query_only = ON`, which refuses writes below the SQL parser so no spelling of DELETE gets through, plus an authorizer callback that denies `customers.email` during statement preparation, which is column-level authorization. In Postgres it is a role created with `GRANT SELECT` on named columns, no write grants anywhere, and row-level security for the per-tenant case.

The property that makes these controls rather than filters is that none of them reads the query text. They act on the tables and columns a parsed statement resolved to, so aliasing the column, burying it in a subquery, wrapping it in `UPPER()`, or selecting it in a query with `WHERE 1 = 0` all fail identically. Every design that inspects generated SQL to decide whether to run it is a blocklist, and blocklists lose to the next spelling. The habit worth taking: decide what a query may touch before you know what the query is.

There is a measurement consequence, and the lab's sharpest moment is where it lands. The `defined` prompt scores 100% on the benchmark and will still hand over every customer email, because a correctness metric asks only whether what the system did was right, never whether it should have been permitted. Both statements are true at once: the query is correct, and the query is refused. So run the eval through the restricted connection and score a refusal as its own outcome, neither correct nor an error. The headline drops from 100% to 92% and the number now describes the system you actually deploy. **An eval that runs with more privilege than production is measuring something you do not ship.**

## 25.6 Knowing when not to answer

The final skill is refusal, and it is worth more than another point of accuracy.

Some questions the schema cannot answer. There is no channels table, no satisfaction score, no ticket history, and no join path that reaches one. A system whose job is to produce SQL will produce SQL, and a query against tables that do not exist is well within reach.

The obvious version of this failure is harmless: a query naming `marketing_channels` fails loudly and someone fixes it. The dangerous version is the near miss. A schema with a `campaigns` table built for something else, or a `source` column populated for 3% of rows in 2023, gives you a query that runs, returns rows, and answers a question nobody asked. Nothing in the output says so. Somebody moves a budget.

So abstention belongs in the benchmark as a scored outcome, with questions that have no correct SQL, and refusing them scored as correct. What makes this unusually tractable compared to abstention in open-ended chat is that the ground truth is checkable: whether a schema can answer a question is a fact about the schema, so you build this half of the suite by naming things you know are absent and confirming with a grep. There is no excuse for a text-to-SQL benchmark containing only answerable questions, because such a suite cannot measure the failure that costs the most to find in production.

Measure the other direction on the same dashboard, though, and resist the temptation to present abstention as a free win. A system pushed toward caution starts declining questions it could have handled, which users notice within days and safety metrics never notice at all. Refusing everything scores perfectly and gets switched off.

The engineering that makes refusal work is dull, which is usually the sign it is right. Give the model an explicit, named way to decline, so that refusing is compliance rather than failure to follow instructions; the lab's single added sentence about `CANNOT ANSWER: <reason>` is what flips its behavior. Then make the surrounding code pass that through as an abstention instead of trying to parse it as SQL.

## 25.7 Where this chapter leaves you

The demo is easy and the system is not, and almost none of the difference is model quality. Score by executing, because the query is a hypothesis and only the database settles it. Expect the fan-out join, because it inflates rather than breaks and therefore survives review. Expect to find that your metrics were never defined, and recognize that as a specification gap wearing a model-shaped costume. Put the boundary in the database, where it holds, and keep the prompt's version of it as the hint it always was. Let the system refuse, and measure both directions of that.

The through-line, if you want one sentence: everything that makes this work is a decision written down somewhere the machine can act on it. The metric definition, the reference query, the abstention rule, the column grant. The model is the part that was already easy.
