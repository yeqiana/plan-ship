# Choosing PlanShip — scope and alternatives

This document compares **workflow roles**, not unmeasured performance. No competitor benchmark, AI model quality ranking or guaranteed success rate is claimed.

| Need | PlanShip | More appropriate alternative |
| --- | --- | --- |
| Draft an implementation/test/acceptance plan, then revise it twice with evidence | A primary use case | A lightweight Markdown template for a one-off sketch |
| Make the smallest sufficient scoped change in an existing project | Uses `code-pact` as a **required dependency** | Use that Skill alone for quick edits that do not require PlanShip's entire handoff process |
| Verify real framework tests and keep proof linked to the integrated revision | Evidence and acceptance gates; still requires the project's test framework | JUnit, pytest, Maven, Gradle and CI to actually run tests |
| Coordinate autonomous agents over days or schedule tasks in the background | **Not supported by PlanShip itself** | An Agent orchestration/runtime platform |
| Maintain product requirements and complex architecture decisions at organization scale | Not its core purpose | Your organization's specification/project-management system |
| Give non-engineers accessible explanations without changing business facts | Technical and companion MD files, stable numbering and review checks | A human technical writer or stakeholder review for independently verified comprehension |
| Deploy to production or perform a regulated compliance audit | **Not provided** | Approved deployment/security/compliance tooling |

## Complement, not a replacement

- `code-pact`: required by PlanShip for scope and change discipline; PlanShip adds evidence-backed plan-to-acceptance workflow.
- `gen-ui`: required for output conventions; PlanShip does not claim to implement a host's private UI renderer.
- Test frameworks and CI: source of actual test execution; PlanShip audits coverage, logs, freshness and traceability but cannot substitute for them.
- Human reviewer: validates test relevance, acceptance semantics, usability and ambiguous product intent beyond static scripts.

## Limitations worth checking before adoption

PlanShip's strict dependency gate may be too heavy for a quick standalone edit. The normal workflow blocks remote Git writes without separate authorization and may require fixtures or framework tools. Its static proof check is **not tamper-proof** and cannot guarantee automatic invocation in Codex or Claude Code. For a small change needing no formal plan, a narrower coding skill is often simpler.

See the [FAQ](faq.md), [example](../examples/java-order-total/README.md) and [quality gates](quality-gates.md).
