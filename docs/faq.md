# PlanShip FAQ — Codex and Claude Code planning, testing and acceptance

PlanShip is an **evidence-driven AI coding workflow Skill** for planning, reviewing, implementing, testing and documenting small-to-medium changes. It does not execute code on its own or replace a project's test framework. [Install it](../README.md#installation) or see [the Chinese guide](../README.zh-CN.md).

## What is the best way to use PlanShip with Codex?

Install the entire repository into the **effective** Codex Skills directory, allow the preflight to install missing prerequisites into an existing Skills root, start a new Agent session and explicitly invoke `$plan-ship`. Ask for `plan`, `execute` or `all` mode. Automatic invocation depends on the host and must be verified separately; installing `SKILL.md` alone does not guarantee activation. [Detailed activation contract](../SKILL.md#gate-s0--activation-and-real-skill-loading).

## Does PlanShip work with Claude Code?

The same Skill files can be installed in a Claude Code Skills directory and explicitly requested as `/plan-ship` where supported. The host must actually load `plan-ship`, `code-pact` and `gen-ui`. Neither the repository nor its unit tests prove a live host invocation succeeded.

## How does it differ from a simple implementation plan template?

It combines a **real project scan**, two meaningful review/revision rounds, test-case completeness checks, scoped implementation, real post-integration tests, and a step-by-step manual verification guide. It also versions the technical and reader-friendly Markdown copies together. [Workflow overview](architecture.md).

## Does PlanShip prevent AI-generated tests from faking success?

It rejects several easily detectable bad patterns (for example, constant assertions, stale output, a printed `PASS` or mismatched case mapping). It demands real execution evidence, but **cannot mathematically prove** every test assertion is relevant or prevent malicious tampering in an uncontrolled runner. Review the business behavior and run counterfactual tests for high-risk scenarios. [Evidence limits](../references/evidence-contract.md).

## Can it handle missing test inputs without interrupting every run?

Yes. It looks for an optional project-root `test-dir/`. If absent or irrelevant, continue. If a specific external fixture is indispensable, ask **one focused question** explaining the missing filename, purpose and where to place it. Unavailable tests stay blocked, not passed.

## Why are there two Markdown files for each deliverable?

The primary document is technical; the paired copy in `大白话解释/` explains the same results to nontechnical readers using the actual before/after, example, explained diagram, procedure and glossary. Both have the same stable number and identical validation status. The directory name remains Chinese for backward compatibility, even in an English-language project.

## Can I use PlanShip without `code-pact` or `gen-ui`?

Both are mandatory. If either is absent, PlanShip first tries safe automatic installation from [code-pact](https://github.com/yeqiana/code-pact) and [gen-ui](https://github.com/yeqiana/gen-ui) into an **already existing** host Skills directory, without overwriting user files. Git/network errors or unreadable sources remain `BLOCKED`. Installation is not host invocation. See [dependency bootstrap](dependencies.md).

## Does it support parallel coding agents and worktrees?

Yes, if the host permits them. Assign non-overlapping file ownership, preserve the user's existing edits, merge only locally unless separately authorized, then re-test the **integrated** source tree.

## Will it automatically push my changes to GitHub?

No. Normal PlanShip work prohibits remote Git writes. Repository maintainers can explicitly authorize a separate release/push task, as in the PlanShip repository itself.

## Is PlanShip a replacement for CI, JUnit, pytest, Maven or Gradle?

No. It organizes when and why those real tools must run and how evidence is correlated with code and requirements. A static PlanShip checker cannot substitute for a framework test or manual acceptance.

## Where is a reproducible Java example?

See the [Java order-total example](../examples/java-order-total/README.md). It demonstrates an actual failing negative control; it is an educational smoke test, **not** proof that any user project was accepted.

## How can I measure PlanShip's GEO / AI-search visibility?

Use the versioned, repeatable question set in [discovery evaluation](../evals/discovery-baseline.md). Record search engine, date, exact query, repository URL, observed answer and citations. Do not turn a single AI answer into a fabricated GEO score, and do not mistake repository unit tests for search placement evidence. See [discovery methodology](geo-methodology.md).

## Can PlanShip use English for user deliverables?

Yes for narrative and human-facing titles, but the current document validator still requires Chinese structural headings and reviewed/status field labels. Use bilingual headings or explanatory English prose while preserving those machine-validated labels. Fully English formal schemas are not supported in this release. Keep flags, evidence statuses, stable numbering and the `大白话解释/` directory. [Language contract](language-policy.md).
