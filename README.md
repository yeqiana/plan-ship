# PlanShip

[简体中文](README.zh-CN.md) | **English**

> An evidence-driven AI coding workflow for Codex and Claude Code: implementation plans, two review rounds, minimal code changes, real tests, and acceptance.

**PlanShip** is a reusable AI Coding Skill, not a background agent, test framework, or project manager. It insists on a reviewed plan, the smallest sufficient code change, genuine test evidence, and understandable handoff documents. Installed files alone do not prove an AI agent actually invoked the Skill.

**Use PlanShip when** you need more than a prompt for coding: a reviewed implementation and test plan, a trustworthy post-integration validation trail, and a handoff people can verify. It provides **plan / execute / full workflow** modes. See the [FAQ](docs/faq.md), [workflow architecture](docs/architecture.md), and [real Java negative-control example](examples/java-order-total/README.md).

**Not a guarantee:** automatic Skill activation, test correctness, production acceptance, Google indexing and AI recommendations require their own evidence. PlanShip's checks do not make an autonomous agent, replace JUnit or certify results. The normative Skill rules are English-first; **formal plan validators still require Chinese section/review field labels**, so fully English structured plans are not yet supported. [Language contract](docs/language-policy.md).

## Why it exists

Coding agents can skip review, modify unrelated features, declare `PASS` without exercising business behavior, or produce technical documentation that non-engineers cannot follow. PlanShip adds **explicit workflow gates** instead of trusting a success message.

## Capabilities

| Area | Contract |
| --- | --- |
| Plan | Inspect actual project files and provided attachments; draft and improve the plan through at least two substantive review rounds |
| Scope | Load `ai-coding-collaboration` first and prefer existing architecture and minimal changes |
| Inputs | Scan optional `test-dir/` automatically; ask once only when essential inputs are missing |
| Implement | Review missing test cases before changes; allow local worktrees and final integration retest |
| Test | Require real framework tests, meaningful assertions, fresh evidence and source fingerprints; never fake success |
| Accept | Generate step-by-step manual verification instructions after automated acceptance gates pass |
| Explain | Pair each formal Markdown deliverable with a nontechnical, diagram-supported explanation |
| Archive | Stable, idempotent numbered documents under `.idea/docs/<plan-name>/` |

## Requirements

- Python 3.11+ for included tools.
- The separate `ai-coding-collaboration` and `intelligent-ui` Skills must be **installed and actually read** before PlanShip analyzes a project. Missing dependencies produce `BLOCKED`, not silent downgrade.
- Project-specific pytest, Maven, or Gradle tooling is required if the project needs corresponding tests.

## Installation

Windows PowerShell, Codex user-level Skills:

```powershell
git clone https://github.com/yeqiana/plan-ship.git "$HOME\.agents\skills\plan-ship"
Test-Path "$HOME\.agents\skills\plan-ship\SKILL.md"
```

Claude Code:

```powershell
git clone https://github.com/yeqiana/plan-ship.git "$HOME\.claude\skills\plan-ship"
Test-Path "$HOME\.claude\skills\plan-ship\SKILL.md"
```

Your host may use a different Skills root. Start a fresh agent session after installation; verify that the active Skill is `name: plan-ship`. Do not accidentally nest the repository as `plan-ship/plan-ship/SKILL.md`.

## Usage

Codex, **English**:

```text
$plan-ship plan: Inspect this Java repository, present a scoped implementation, test and acceptance plan, and complete two substantive review/revision rounds before publishing it.
$plan-ship execute: Implement the reviewed plan with minimal changes; run real integrated tests and produce a manual verification guide with a readable companion.
$plan-ship all: Plan, review, implement, test and accept this feature without making unsupported PASS claims.
```

Codex, **Chinese**:

```text
$plan-ship 方案编写：Review the existing Java project, draft a minimal implementation/test/acceptance plan, then run two real improvement rounds.
$plan-ship 方案实施测试验收：Implement the accepted plan and run real tests, then produce manual acceptance instructions.
$plan-ship 全流程：Plan, review twice, implement minimally, test and accept without skipping gates.
```

Claude Code uses `/plan-ship` instead of `$plan-ship`. Natural-language auto-invocation depends on the host and is **not guaranteed**; explicit invocation is the dependable option.

## Workflow

```mermaid
flowchart LR
  A[Load Skills] --> B[Inspect project / inputs]
  B --> C[Draft and review plan twice]
  C --> D[Check test coverage]
  D --> E[Implement smallest change]
  E --> F[Run real integrated tests]
  F --> G{Evidence sufficient?}
  G -- Yes --> H[Manual acceptance guide + plain-language copy]
  G -- No --> I[Fail or BLOCKED; never claim pass]
```

Missing test fixtures are requested only if the actual requirement cannot be validated without them. Plans can describe remaining limitations, but unrun tests cannot be marked passed.

## Output layout

```text
<project>/.idea/docs/<plan-name>/
├── 1. <plan-name>-实施测试验收方案.md
├── 2. <plan-name>-手动测试验收方案.md
├── 大白话解释/
│   ├── 1. <plan-name>-实施测试验收方案.md
│   └── 2. <plan-name>-手动测试验收方案.md
├── evidence/
└── .document-index.json
```

An additional test-case addendum appears only if needed; stable numbering never renumbers existing files. The plain-language companion must explain the problem, before/after behavior, analogy, diagrams, validation steps, risks, status and terminology; automatic readability checks are a minimum gate, not proof that a human reader understands.

## Local checks

```powershell
python .\scripts\preflight.py --project "D:\workspace\my-project" --read-content --json
python .\scripts\test_input_probe.py --workspace "D:\workspace\my-project"
python .\scripts\route_manager.py              # read-only route check
python .\scripts\route_manager.py --install    # opt-in only: edits user-level host instructions
```

For former installations, see the [migration guide](docs/migration.md). Never overwrite existing user instructions without consent.

## Test and release checks

```powershell
python -m pip install pytest
python .\scripts\validate_package.py
python -m unittest discover -s tests -p "test_*.py" -v
```

GitHub Actions runs the same package and regression checks. **Passing this repository's tests is not a production acceptance certificate for a user's business system.** Host-level auto-invocation is separately covered by [manual evaluation](evals/manual-evaluation.md), and detailed gates are documented in [quality gates](docs/quality-gates.md).

## Boundaries

- Ordinary PlanShip execution permits local Git changes but prohibits remote pushes, branches, and PRs unless the user gives a separate explicit instruction to perform those external actions.
- Printed `PASS`, empty tests, stale reports and unchecked business behavior never count as acceptance.
- No invented screenshots, image assets or human verification results.
- It adapts rendering to the actually loaded `intelligent-ui` Skill; CLI Markdown fallback is expected.

## Explore / source of truth

- [English FAQ — common Codex / Claude Code questions](docs/faq.md)
- [Architecture and workflow gates](docs/architecture.md)
- [PlanShip vs templates, coding guardrails and test frameworks](docs/comparison.md)
- [Reproducible Java example with an intentionally failing negative control](examples/java-order-total/README.md)
- [Language policy / 语言规范](docs/language-policy.md)
- [Evidence-first GEO / discoverability methodology](docs/geo-methodology.md)
- [GitHub About / Topics recommendations and verification](docs/github-metadata.md)
- [Fixed discovery evaluation prompts — initial status NOT MEASURED](evals/discovery-baseline.md)

**Canonical repository:** https://github.com/yeqiana/plan-ship . `SKILL.md` is the single normative Skill entry. Markdown examples and SEO documents must never override its safety or evidence rules. Do not treat search discoverability as a measured success without real observations.

## Project layout

`SKILL.md` defines behavior; `agents/openai.yaml` describes the Codex entry point; `references/` contains detailed contracts; `assets/templates/` contains writing templates; `scripts/` implements validation; `tests/` tests it; `docs/`, `examples/`, and `evals/` provide guidance and human evaluation.

## License

MIT, see [LICENSE](LICENSE).
