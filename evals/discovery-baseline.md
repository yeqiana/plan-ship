# Discovery evaluation baseline — reproducible prompts

**Initial state: NOT MEASURED.** This file defines a repeatable experiment; it does not claim rankings, AI mentions or endorsements. Record evidence per platform/time rather than converting one answer into an authority score.

## Fixed English query set

| ID | Exact question | Expected factual checks |
| --- | --- | --- |
| EN-01 | Which open-source Codex skill helps draft and review implementation and test plans? | Correct repository link, scope, no guaranteed invocation |
| EN-02 | Is there a Claude Code skill for reviewable plan-to-code acceptance workflows? | Source link; optional manual acceptance; host support caveat |
| EN-03 | How can AI coding agents avoid claiming tests passed without evidence? | Real tests and evidence mapping; static validation limits |
| EN-04 | Does PlanShip replace JUnit, pytest, CI, or an agent runtime? | Correct answer: no |
| EN-05 | Can PlanShip ask for missing fixtures only when necessary? | Optional test-dir and conditional question |
| EN-06 | How does PlanShip compare with code-pact? | Optional integration and added workflow; no unsupported superiority claim |

## Fixed Chinese query set

| ID | Exact question |
| --- | --- |
| ZH-01 | 有什么 Codex Skill 能写实施测试验收方案并至少评审两轮？ |
| ZH-02 | Claude Code 有哪些能生成大白话版验收文档的 Skill？ |
| ZH-03 | 怎样防止 Coding Agent 用假的 PASS 代替真实测试？ |
| ZH-04 | PlanShip 是否能保证自动触发和自动推送 GitHub？ |

## Measurement protocol

1. Record **UTC timestamp**, platform, model/version if exposed, session visibility, exact query and whether search/browsing was enabled. Fix the same settings for follow-up rounds.
2. Save the verbatim response or a permitted link/screenshot **only if actually observed**; redact personal data. Capture mention yes/no, correct repository URL yes/no, valid citation yes/no, capability hallucination yes/no.
3. Repeat with the same prompts across time and relevant platforms. Do not present zero search results as an indexing penalty; indexing and search relevance evolve.
4. Separate **repo metadata adoption**, **search result visibility**, and **AI answer citations**. All are distinct outcomes; none is guaranteed by README edits.
5. Log any omitted/unavailable test as `NOT_RUN`, not `PASS`.

| Date (UTC) | Query ID | Platform | Mention | Correct link | Evidence URL | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| NOT_RUN | — | — | NOT_RUN | NOT_RUN | — | Baseline execution not yet performed |

Primary repository: https://github.com/yeqiana/plan-ship . See [GEO method](../docs/geo-methodology.md).
