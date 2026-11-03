# Reproducible Java example — catch a real incorrect result

This **illustrative smoke harness** demonstrates how a test must depend on real logic and an expected result. It is not JUnit, not PlanShip's framework-evidence protocol and **not evidence of acceptance of a user's project**. Real Java projects should use their own JUnit/Maven/Gradle tests and PlanShip's evidence gates.

## Requirement

A shopping order's total in cents equals the sum of its non-negative line items. Negative inputs are rejected and an empty order totals zero. **Non-goal:** no payment system, database or API is added for this demonstration.

## Files

- [`src/OrderTotal.java`](src/OrderTotal.java): the small production function being verified.
- [`src/OrderTotalCheck.java`](src/OrderTotalCheck.java): an executable test harness with assertions that reference production behavior.

## Run (JDK 17+)

From this folder, using either PowerShell or a POSIX shell:

```text
javac -d out src/OrderTotal.java src/OrderTotalCheck.java
java -cp out OrderTotalCheck
```

The correct implementation prints `Java order-total smoke checks: passed (3 checks)` and exits successfully. This is an **expected output**, not evidence that the reader ran it.

## Negative control (in an isolated copy only)

For an intentionally broken version, change the source copy's `total = Math.addExact(total, amount);` to `total = Math.addExact(total, amount) + 1;` and compile/run again. The first check must throw `AssertionError` and exit nonzero. Never leave this mutation in the shipping source tree. The repository's automated [test](../../tests/test_java_example.py) performs this negative control in a temporary directory and restores nothing because it never modifies the tracked files.

## Why the negative control matters

A test that asserts `2 == 2` would pass whether the order calculation was broken or correct. A test that calls `OrderTotal.totalCents(125,275)` and expects `400` can detect a wrong result. Even here, one passing smoke harness does not prove all real-world business cases or rule out malicious test code. See the [FAQ](../../docs/faq.md) and [evidence limits](../../references/evidence-contract.md).
