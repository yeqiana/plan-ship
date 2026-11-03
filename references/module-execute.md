> **Implementation and acceptance module / English overview.** Validate the reviewed plan first. If test cases are missing, draft and improve them through two review rounds before implementation, then update the plan. Assign non-overlapping worktree ownership, merge locally, test the final integrated tree, validate fresh real test evidence and only then publish the manual acceptance guide plus its readable companion. Never claim user-performed checks are complete.

# 模块 B v2.2：实施测试验收具体操作顺序

## B0 先校验方案

核对方案与实际项目、依赖、Git 工作树、会话附件。不得在没有正式方案门禁的情况下开始编码。

```text
python "<SKILL_ROOT>/scripts/validate_docs.py" --type plan --file "<PLAN_DIR>/<number>. <方案名称>-实施测试验收方案.md" --workspace "<PROJECT>"
```

## B1 测试用例缺口门禁

每条 REQ 必须有测试和可判定验收标准。检查正常、异常、边界、回归、权限、幂等、并发（项目适用时）；若缺口，先创建 `assets/templates/testcase-addendum.md` 的新实例（草案不可标为最终），两轮独立评审与两次实际补强，最终复核 PASS 后校验：

```text
python "<SKILL_ROOT>/scripts/validate_docs.py" --type testcases --file "<PLAN_DIR>/<number>. <方案名称>-测试用例补充.md" --plan "<PLAN_DIR>/<number>. <方案名称>-实施测试验收方案.md" --workspace "<PROJECT>"
```

将新增用例及审查记录写回正式计划，记录 `CHG-xxx`、旧/新版本、修改前/后、来源文档及校验结论；增量修订计划仍保留完整的两轮及必要的新轮次评审。再执行计划结构校验；先成功后实施。若无缺口，在执行日志记录已检查及为何充分，不生成无用补充文档。

## B2 变更范围及本地并行

建立 `任务 → 允许文件 → 基线 commit → 当前脏状态 → 负责人/worktree → TC` 表。禁止默认清空或 stash 用户改动，禁止多个分支无协调修改同一文件。每个 worktree 自检后，审查 `git diff`、基线、测试记录、冲突风险；只允许本地 merge/cherry-pick，禁止 git push、创建远端分支或远端 PR。

**必须先完成全部本地集成，再进行最终测试。** 使用 worktree 时生成 `<PLAN_DIR>/evidence/merge-audit.json`（参考 `assets/examples/merge-audit.example.json`）：审查过的本地 worktrees、冲突/依赖处置、集成时 `git HEAD` 和源码指纹。`integration.merged=true` 表示当前项目根包含全部目标改动，**不代表远端合并**。

## B3 测试与证据（不伪造）

根据项目构建工具发现真实测试命令，禁用未经授权的网络、生产、危险操作。仅在最终工作树执行 `run_and_record.py --stage integrated`，保存真实执行测试框架产生的全新 JUnit XML、逐 TC 映射的真实 test-id 和具有断言的测试源码、日志、时间、exit_code、工作区源码指纹和方案哈希；若 `test-dir` 存在必须自动枚举并保存文件哈希；其他输入通过 `--fixtures` 指定。若某个测试没有实际报告、源码没有可识别断言，必须 BLOCKED。

记录每次失败，修复并重跑；失败中发现用例缺口时回 B1 **先补用例再继续编码**。不要把 `echo PASS`、只有编译而无测试断言的输出、未实际访问的接口等当成完整用例覆盖。运行器拒绝只打印 PASS 的命令，也不允许用 v2.0 自报证据升级。运行器自身没有防网络/防二次子进程远端写入的隔离能力；若证据不足必须 BLOCKED，不能宣称通过。

## B4 验收门禁

填写 `assets/examples/evidence-manifest.example.json`（必须替换示例 RUN），对每个 TC 标记状态并引用最终 RUN，对每个 REQ 关联 ACC 通过条件、实际观察、RUN。执行：

```text
python "<SKILL_ROOT>/scripts/validate_evidence.py" --manifest "<PLAN_DIR>/evidence/manifest.json" --plan "<PLAN_DIR>/<number>. <方案名称>-实施测试验收方案.md" --workspace "<PROJECT>"
```

失败、阻断、未运行、源码/方案改变、日志失效、缺最终合并证据时不能通过。**并行时先 merge、再测、最后才验收**。

## B5 手动验收指南（A 通过后）

编写逐步操作、输入/预期、异常、备份/清理、旧功能回归及证据；先编写初稿，再进行两轮“评审→实际补强”，独立复核通过后与同编号大白话版一起登记在 `<PLAN_DIR>`：

```text
python "<SKILL_ROOT>/scripts/validate_docs.py" --type manual --file "<PLAN_DIR>/<number>. <方案名称>-手动测试验收方案.md" --plan "<PLAN_DIR>/<number>. <方案名称>-实施测试验收方案.md" --manifest "<PLAN_DIR>/evidence/manifest.json" --workspace "<PROJECT>"
```

若用户后续真正进行了手动操作，单独记录结果，不能提前写“用户手动复验通过”。

## B6 新版文档同步门禁

正式 MD 及关联 JSON/XML/log 都必须留在同一 `PLAN_DIR=<项目根>/.idea/docs/<方案名称>/` 下（证据子目录为 `evidence/`）；**不再向 `.idea/docs` 根目录散写文件**。

每次新建/修改正式 MD：先由 Agent 真实编写技术版及大白话解释版，保存于 `.drafts/`，再用 `doc_registry.py publish --key <固定逻辑键>` 同步发布；重写主方案时复用 `--key plan`，编号不变。所有正式交付 MD 用 `doc_registry.py verify` 扫描孤儿文件、过期配对、哈希失配。运行器证据路径、case-map、manifest、日志和框架报告必须属于同一 PLAN_DIR；不得跨方案复用测试记录。
