# Lessons learned

What did not go according to plan while building this repository. Entries written when
the surprise happened, not reconstructed afterwards.

## Check the planted numbers before writing the prose about them

- **Expected:** The fixture was designed so that one order with three line items would
  demonstrate the fan-out bug, and the docstring said the inflation was $1,299.98,
  which is that order's total counted twice extra.
- **Actual:** Two other orders also have two line items each, so the real inflation is
  $2,139.97. The prose was written from the design intent rather than from a query, and
  it was wrong the moment a second multi-item order was added to the seed data.
- **Next time:** In a teaching repository every number in prose is a claim about code.
  Run the query, paste the output, then write the sentence. Better still, compute the
  figure in the example itself so it cannot drift; three of the examples now do this,
  and the two that quote a constant are pinned by `tests/test_warehouse.py`.

## A gold query with an ambiguity in it is not gold

- **Expected:** "Top 3 products by units sold" was a simple ranking question, useful
  mainly for testing order-sensitive comparison.
- **Actual:** The first reference query summed `order_items.qty` with no join to
  `orders`, so it counted units from a cancelled order and a pending one. The benchmark
  was asserting an answer to a question it had not settled, which is the exact failure
  the lesson on metric definitions is about, sitting in the file that defines the
  benchmark.
- **Next time:** Read every gold query as if grading it. If two analysts could defend
  different results, the question is underspecified and the reference query is quietly
  making the ruling. Write the ruling into a comment beside it, which also gives the
  next person something to disagree with explicitly.

## An open cursor is a lock

- **Expected:** Lesson 5 needed the owner connection to actually run a `DELETE` and then
  rebuild the fixture, so the lesson would demonstrate its central claim rather than
  print an assertion about it.
- **Actual:** `database table is locked`. The read-only analyst connection had been
  used for SELECTs, and in SQLite's shared-cache mode each unclosed cursor holds a read
  lock on the tables it touched, which blocks writers on other connections. A harness
  that only ever reads had deadlocked the process maintaining the fixture.
- **Next time:** Close cursors, and be suspicious of "this connection only reads" as a
  reason a component cannot cause a lock problem. `execute.run()` now closes in a
  `finally`. The second half of the fix was less obvious: the owner's own uncommitted
  write transaction also had to be committed and the connection closed before the
  rebuild, because a new connection to a shared-cache database is still a different
  connection.

## Writing the example first showed the module was missing a verdict

- **Expected:** `evaluate.py`'s five verdicts would be enough, and the capstone would
  just run the existing scorer against the restricted connection.
- **Actual:** A query refused by the permission boundary came back as ERROR, which put
  "the model wrote SQL that does not parse" and "the model tried to read PII and was
  stopped" in the same bucket. The number that most needed watching was hidden inside
  the one nobody looks at twice.
- **Next time:** When a new execution context is introduced, check whether it produces
  a new *kind* of outcome before reusing the existing categories. The BLOCKED verdict
  came out of writing the capstone, not out of designing the scorer, which is an
  argument for writing the thing that uses a module before finalizing the module.

## A test that rebuilds the fixture cannot detect damage to it

- **Expected:** `test_the_data_is_untouched_afterwards` verified that refused writes
  left the warehouse intact.
- **Actual:** It called `connect()` to check, and `connect()` drops and recreates every
  table. The test passed unconditionally and would have passed just as happily if every
  write had succeeded.
- **Next time:** For any test asserting that something did *not* happen, ask what would
  make it fail, then make that thing happen and watch it fail. This one now checks
  through the connection that existed before the writes, and was confirmed by running a
  real `DELETE` and seeing the assertion break.
