# PlanShip 质量门禁与发布验收

## 阶段与证据

| 门禁 | 必须完成的事实 | 未完成时 |
|---|---|---|
| S · Skills | 实际加载主 `plan-ship`；可选发现 `code-pact`、`gen-ui`，缺失不阻断、不默认自动下载 | 未加载 PlanShip 才无法宣称启用 Skill；可选集成缺失不影响核心流程 |
| I · Inputs | 分析真实项目、附件与 `test-dir/`；仅在关键文件必需且缺失时提出一次明确询问 | 不得声称依赖该文件的测试通过 |
| P · Plan | 初稿、两轮有差异的评审补强、需求-测试-验收追踪、最小改动范围 | 不得实施 |
| T · Test design | 缺少用例时补齐并至少两轮评审，不需要时不产生冗余文档 | 不得针对缺口实施 |
| B · Build/integration | 本地分支或 worktree 合并、冲突审计、变更范围检查 | 不得用分支测试冒充集成测试 |
| A · Actual tests | 集成后真实测试框架运行，断言实际业务结果，绑定新鲜报告和代码/输入指纹 | `FAIL`/`BLOCKED`/`未验证`，不能写 PASS |
| M · Manual guide | A 满足后生成可照做的操作步骤，两轮评审补强并生成大白话副本 | 不得宣称完整交付 |
| D · Docs | `.idea/docs/<方案>/` 成对 MD、编号幂等、一致性与可恢复校验 | 不得发布正式文档 |

## 真实测试：什么才叫通过

1. 测试执行器必须真实运行框架，产生新鲜 JUnit XML 或该框架正式结果。
2. 测试用例 ID 与真实测试方法映射，断言有明确输入、预期与业务代码调用。
3. 故意改变关键业务输出时，相关测试应该实际失败（隔离环境/恢复后重测）。
4. 产物绑定最终集成源码、方案版本、关键 `test-dir` 文件指纹和原始日志；不得使用过期报告。
5. `pytest -q` 或 Maven 构建成功不自动代表业务验收成功；无运行条件明确报告 `BLOCKED`。

**v1.3.1 判定规则：** `_python_source_has_assertion` / `_java_source_has_assertion` 只完成 `STRUCTURAL_CHECK_PASS_NOT_SEMANTIC_PROOF`。必须拒绝 `assert add(3,4)==add(3,4)`、`assertEquals(1,1)`、仅比较业务输出的简单别名等无独立预期的断言。P0 必须留下独立预期、可审查的反事实/变异负向测试（故意破坏业务行为时测试变红）、恢复后重新通过的证据。**自动结构检查通过不等于业务验收通过。**

**不可当作通过的例子：** `echo PASS`、`assert True`、空测试、编译成功、手填 `manifest.json`、截图不存在却写“已截图”、Agent 自己声称“已手动验收”。

## 文档发布

有 Python 时可用 `doc_registry.py publish` 以逻辑键稳定分配编号；技术版和解释版必须一起更新。`verify` 校验成对内容、索引和基础大白话结构；发布中断可以按 `recover` 指引恢复，但不能自动覆盖人工修改。

大白话文档必须让不懂技术的人能说清：目标、前后变化、流程、异常、验证操作。自动脚本只能防止缺结构或复制原文，不能保证真实读者已经理解。

## Git 操作边界

业务工作流默认只允许本地 `branch/worktree/commit/merge`，禁止远端分支、推送、PR。此次维护仓库的外部推送属于用户明确授权的单独发布操作，不改变 Skill 在业务项目中的默认限制。实际防误推仍需要 Runner 权限控制。

## 发布本仓库的最低证据

- 运行 `python scripts/validate_package.py`。
- 运行完整 `python -m unittest discover -s tests -p 'test_*.py' -v`。
- 用真实 Codex/Claude 宿主分别尝试显式调用和自然语言调用，记录是否确实加载，不能用结构测试替代。
- 检查中英文 README 链接、安装命令、旧名称残留、MIT 和 CI 配置。
- 核对 Git 提交及远端分支；不可把“本地 commit 成功”称为“push 成功”。

**无 Python 时：** 宿主原生文件操作仍可创建双副本与稳定编号，但必须逐项手动复核，并标注“自动编号/一致性和事务回滚未验证”。核心业务测试的真实性要求不降低。

## v1.3.2 最终验收门禁

- `CONSISTENCY_PASS_ACCEPTANCE_NOT_VERIFIED` 仅说明源指纹/报告/用例映射一致，不是验收通过。
- `--gate acceptance` 逐需求检查真实失败的反事实 JUnit XML、对应测试、日志 SHA-256 以及恢复 RUN。缺失或错误则阻断。
- `COUNTERFACTUAL_EVIDENCE_CHECK_PASS_HUMAN_REVIEW_REQUIRED` 也只证明证据形式可核查，尚须独立评审故障注入是否针对关键业务预期。
- `validate_docs.py --type manual` 不再在仅有一致性文件时放行；业务人工复验始终标记为 `未执行` 直到用户实际操作。
