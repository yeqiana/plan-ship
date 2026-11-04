# Changelog

## 1.3.2 — 2026-11-04

- Split optional evidence validation into consistency-only and strict counterfactual evidence gates. The default output can no longer be confused with final acceptance; manual document validation requires failed-case evidence and restored run correlation.
- Reject obvious unreachable Python/Java assertions and arithmetic-constant short-circuit bypasses; add real pytest negative-control regression tests.
- Opt-in user route management no longer replaces existing user instructions; it only emits a snippet for manual merge. New route files are created exclusively.
- Preserve core Skill independence from Python, WebCodex and additional Skills. Tests and static checks are not semantic or human acceptance.

## 1.3.1 — 2026-11-03

- Reject self-comparisons and simple aliases as business-test evidence in Python and Java; mark assertion checks as structural only, and require independent expected outcomes plus real P0 mutation/negative-control evidence for acceptance.
- Detect parenthetical business-keyword dumps in explanatory copies and report `STRUCTURE_PASS_SEMANTIC_REVIEW_REQUIRED` rather than claiming automatic semantic or human-readable approval.
- Add cooperative route-file locking, file identity/content conflict checks and preserved backups. Non-cooperating writes in the final rename window cannot be made universally atomic with portable Python; conflicting modifications must be investigated manually.
- Correct the optional `preflight` contract: missing PlanShip is `NOT_FOUND`, visible files are not host activation proof, and deprecated `core_ready` no longer claims readiness.
- Add a validated transaction PREPARE record and cautious recovery for pre-journal crashes; unexpected files or human edits remain `BLOCKED`.
- Preserve the zero-required-dependency core workflow. New reverse tests and updated documentation cover the changes.

## 1.3.0 — 2026-11-03

- Core PlanShip workflow no longer depends on WebCodex Runner, Python or optional Skills. Optional tools remain available without being a startup requirement.
- Removed silent optional-Skill download; isolated host-specific discovery and explicit opt-in install, fixed no-replace install race and source-trust labeling.
- Added SYSTEM route protection and document business-concept anchors; extended adversarial tests and H-05 coverage.

## 1.2.0 — 2026-11-03

- Replace former required Skill identifiers with `code-pact` and `gen-ui` in all active contracts and tests.
- Pin dependency installation sources to their verified GitHub repositories; automatically bootstrap missing Skills into an existing host Skills root without overwriting user files.
- Keep the new bootstrap strictly separate from actual host Skill loading and evidence-backed acceptance.
- Add offline adversarial tests for non-existent directories, failed clones, conflicts, and idempotency.


## 1.1.0 — 2026-11-03

- English-first authoritative `SKILL.md`, bilingual activation keywords and Codex discovery description; preserved the Chinese workflow modes, folder identifiers and safety gates.
- Added evidence-first FAQ, workflow architecture, neutral comparisons, language contract and GEO methodology with a fixed evaluation prompt set. No invented indexing or AI mention measurements.
- Added a small runnable Java smoke harness with an actual negative-control failure and automated tests; this does not constitute acceptance of a user's project.
- Added a Java-enabled CI step and repository discoverability contract checks. Suggested GitHub About/Topics must be separately applied and verified.

## 1.0.0 — 2026-11-03

- 独立产品命名为 **PlanShip**，正式 Skill ID、调用名和路由标记统一为 `plan-ship`。
- 基于此前方案交付工作流的成熟功能：两轮评审、最小改动、`test-dir` 条件询问、真实测试证据和双副本文档。
- 增加中英文 README、MIT 许可、编辑器规则、CI、人工行为评测说明和迁移说明。
- 明确安装并不代表宿主实际调用，不能声称未经验证的自动触发已通过。
- 新版本源码指纹使用不同命名域，历史证据应重新校验或重跑；没有静默接受旧版验收报告。
