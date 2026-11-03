# Changelog

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
