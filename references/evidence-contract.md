> **Test evidence contract / English overview.** Plan validation, real test execution and evidence validation are separate operations. Use fresh framework-generated JUnit XML and logs from the final integrated source tree, map tests to actual production behavior and assertions, bind source/plan/fixture hashes and block incomplete cases. A machine-generated record can be tampered with and is not proof of complete semantic coverage.

# v2.3 严格真实测试证据协议（保留 v2.1 测试数据 schema）

核心区分：`validate_docs.py` 是文档结构和轮次校验；`run_and_record.py` 是严格执行器（需要 pytest/Maven/Gradle 实际产生 JUnit XML 并关联断言）；`validate_evidence.py` 验证**当前代码快照、计划版本、测试执行文件及需求链路的一致性**。这三者都不能替代独立代码评审、实际功能检查或用户的后续人工复验。

## 运行前

- 完成方案门禁 P；如发现用例差距完成 T 并写回方案。**先写回，再跑测试**。
- 本地集成：用 worktree 时先逐任务审查 diff，完成本地合并，记录合并审计；若不用 worktree，也要记录 `worktrees_used=false`、`merged=true`（指变更已在最终项目根工作树中集成）。
- 最终测试在集成工作区根执行，不能拿 worktree 的 isolated 运行记录充当 integrated 记录。
- 确认测试命令安全、已由用户授权。**运行器不提供沙箱隔离**，被调用的 Maven、Gradle、npm、Python 或其他子程序自身可能访问网络或执行 Git 操作；需结合本地 runner 命令策略、权限及网络限制使用。
- 如果不是 Git 仓库或无 HEAD，自动证据门禁会阻断；不要伪造 Git 证据，需记录限制并停止宣称自动验收。

## 命令记录

`<SKILL_ROOT>` 指加载本 Skill 时真实 `SKILL.md` 文件所在的绝对目录，不能按业务项目工作目录猜测。

```powershell
$skillRoot = 'C:\Users\<用户>\.agents\skills\plan-ship' # 按真实路径替换
$project = 'D:\workspace\my-project' # 按实际项目替换
$planDir = "$project\.idea\docs\demo"
$plan = "$planDir\1. demo-实施测试验收方案.md"
$runs = "$planDir\evidence\runs.json"
python "$skillRoot\scripts\run_and_record.py" --workspace "$project" --plan "$plan" --runs "$runs" --stage integrated --cases TC-207,TC-208 --runner pytest --case-map "$planDir\evidence\case-map.json" --report ".idea/docs/demo/evidence/reports/{run_id}.xml" -- python -m pytest -q tests/test_feature.py --junitxml={report}
```

有 `test-dir` 时自动记录其文件 SHA-256；其他测试素材通过 `--fixtures` 列举，未知外部资源必须明确标记未覆盖。`--report` 必须是不存在的 JUnit XML 路径，推荐 `{run_id}` 生成唯一文件名。Maven/Gradle 模式可使用测试框架生成的标准 JUnit XML，但必须确保路径新鲜，且其对应测试真正执行。

输出记录：

- `runs.json`：schema_version=2.1，run_id、UTC 时间、执行命令、真实框架报告/哈希、TC 映射/哈希、测试源码/哈希、阶段、用例 IDs、退出码、源码 fingerprint、Git HEAD、计划 SHA、日志路径/哈希、附件哈希。
- `logs/RUN-*.log`：执行器捕捉到的标准输出和标准错误。

`--cases` 必须与 `--case-map` 内列出的 TC 完全一致。映射中的 `test_id` 必须真实出现于本次 JUnit XML `<testcase>`，且指定源码中的对应测试方法必须具备可识别断言。只打印 `PASS`、空报告、跳过、编译但未测、重复借用一个 test_id 覆盖多个 TC 都被拒绝。**请勿为通过检查而添加无效断言；用例必须真正验证需求。**

## 最终 manifest

参考 `assets/examples/evidence-manifest.example.json`，填入真实 `RUN-xxxxxxxxxxxx`。各字段定义：

- `plan_file`、`runs_file`：相对项目根路径，必须在**同一个 `.idea/docs/<方案名称>/`** 目录内；任何正式 MD 均须同步配对大白话版本。
- `integration.worktrees_used`：是否真实使用过 worktree。
- `integration.merged`：true 表示全部改动已位于最终集成工作树；不是远程合并。
- `integration.merge_audit`：如使用 worktree，必须指向同一方案目录 `evidence/` 内的 JSON 审计文件，包含 `merged_local=true`、当前 `integration_head`、当前 `source_fingerprint`、`reviewed_worktrees` 列表及 `conflict_resolution` 文本。
- `cases`：正式方案**每一个 TC** 都要出现，并必须 PASS，关联最终 integrated RUN。
- `acceptance`：正式方案**每个 REQ** 都必须有唯一 `ACC-xxx`，PASS 且关联至少一个已通过的运行记录及明确的人工/Agent 判断描述。

示例：

```powershell
python "$skillRoot\scripts\validate_evidence.py" --workspace "$project" --plan "$plan" --manifest "$planDir\evidence\manifest.json"
python "$skillRoot\scripts\validate_docs.py" --type manual --workspace "$project" --file "$planDir\2. demo-手动测试验收方案.md" --plan "$plan" --manifest "$planDir\evidence\manifest.json"
```

## 必须阻断的状态

- 任何必测用例失败、未运行、缺 RUN 或映射不正确。
- 计划变更后沿用旧 RUN、源码变更或 worktree 合并后未重新测。
- 日志丢失或哈希改变、输入 fixture 被修改。
- acceptance 未 PASS、存在孤立 REQ 或不属于已通过用例的关联。
- 已使用 worktree 但未提供本地合并审计。

**旧版 v2.0 的 runs 与 manifest 一律无法通过 v2.1 验收，必须重新执行测试而非直接改版本号。**

**证据的信任边界：** 文件由本地执行器生成，但可由本地有写权限的人修改，记录自报覆盖也不能证明质量；它是防止漏项与陈旧结果的可核对门禁，不是不可伪造的安全证明。若需要抗篡改，可在受控 CI/runner 上加只追加日志、签名与命令策略，且仍需人工结果审查。

## v1.3.1 补充：不接受自证正确的断言

- `assert add(3,4) == add(3,4)` 即使真实 pytest PASS，仍没有独立业务预期，源码门禁必须拒绝；简单结果别名比较同样如此。
- Java `service.calculate(...); assertEquals(1,1)` 不观察业务结果，也必须拒绝。有效用例应对实际结果提出与目标代码独立的预期（如 `assertEquals(7, service.calculate(3,4))`）。
- 当前 Python/Java 静态校验输出的 `assertion_check=STRUCTURAL_CHECK_PASS_NOT_SEMANTIC_PROOF` **仅说明基本断言形态可识别**，不能作为 `ACCEPTANCE_PASS`。关键 TC 应在可丢弃副本里实施真实负向/变异控制，保留原通过记录、故障注入后的失败日志、恢复后通过结果及审查说明；不能完成则标 `未验证 / REVIEW_REQUIRED`。

## 业务行为真实性门禁（v2.3）

- **源码层硬性校验**：Python 真实框架测试需引用项目内非测试模块并从业务函数调用得到断言结果，忽略恒真短路与无关常量；不能只 `import` 然后断言常量。Java/JUnit 源码检查同样拒绝仅有断言而未观察实际业务方法的用例。
- **动态行为复核**：对核心 TC，在隔离、可丢弃的副本中让目标业务函数返回错误值或故意制造失败，运行同一真实测试，预期出现失败；记录测试选择、原始结果、变化点、失败日志、恢复状态，禁止在最终工作树上为了证明而破坏业务代码。若无法进行则说明范围及未验证状态，不能以扫描结果代替。
- **不能证明的事**：当前记录器不是可信执行环境；不能防止所有精心编造的测试或授权操作者修改证据。只有权限隔离、独立审查和真实环境回归才能进一步提高证明强度。

## v1.3.2：一致性检查与最终验收证据分离

仅运行 `validate_evidence.py` 默认进行 **consistency-only** 检查。即使返回退出码 0，状态也只是 `CONSISTENCY_PASS_ACCEPTANCE_NOT_VERIFIED`；绝不可作为业务验收通过。

需要审核反事实失败证据时，显式运行：

```powershell
python "<SKILL_ROOT>/scripts/validate_evidence.py" --gate acceptance --manifest "<PLAN_DIR>/evidence/manifest.json" --plan "<PLAN_DIR>/1. 正式方案.md" --workspace "<PROJECT>"
```

最终验收 `acceptance[]` 的每个条目必须附带 `counterfactual` 对象，字段包括：`test_id`（须对应恢复后真实通过的测试）、`mutation_description`（具体故障注入与独立预期，不能空泛）、`negative_report_path`、`negative_report_sha256`、`negative_log_path`、`negative_log_sha256`、`restored_run_id`，以及 `mutation_source_path`（必须是生产源码）、`baseline_source_sha256`（当前已恢复源码）、`mutated_snapshot_path`/`mutated_source_sha256`（变异源码快照）、`mutation_patch_path`/`mutation_patch_sha256`（原始源码到变异源码的统一差异）、`negative_test_source_sha256`（与恢复后 RUN 相同的测试源码指纹）。负向报告必须是同一方案内真实产生的 JUnit XML，且对应 `test_id` 具有 failure/error；日志、报告哈希匹配；恢复 RUN 必须关联最终验收并涵盖该测试。没有此记录、哈希被修改或测试未失败，一律不准放行。

这些本地文件仍可被拥有工作区写权限的人伪造，验收状态只能是 `COUNTERFACTUAL_MUTATION_ARTIFACTS_LINKED_HUMAN_REVIEW_REQUIRED`：**独立审查者仍须核对故障注入、业务预期和恢复过程**。真正业务/用户验收不由脚本自动宣布。`validate_docs.py --type manual` 也会要求这一级证据，防止只靠一致性检查生成终版。

Python AST 静态检查补充拒绝明显不可达的 `if False` / `while False` / `return` 后断言，和 `or (1+1==2)` 等恒真短路；Java 基本过滤 `if(false){...}`。这只是有限保守检测，无法穷举动态条件或反射控制流，真实负向测试才是关键。


## v1.3.3 变异证据防测试预期作弊

`--gate acceptance` 必须校验变异发生在生产源码（不允许 `tests/`、`test-dir/` 等），当前已恢复文件 SHA 与基线一致，变异快照与源文件不同，并且 `difflib.unified_diff` 可从这两个文件精确重建登记的补丁。恢复后测试方法源码与 `negative_test_source_sha256` 一致。仅通过修改测试预期制造红色报告，没有真实生产变异快照及补丁时不能过门禁。

**限制**：可修改的本地快照、补丁、XML 与日志仍无法给出可信执行来源证明。自动工具只能检查相互一致性；独立评审者必须核对实际执行命令、故障注入是否生效、期望是否独立、恢复是否完整。若不可核实，业务验收仍 `未验证`。

## v1.3.4 受控生产变异执行记录

之前的生产变异快照 + 补丁 + 失败报告均可独立制作，无法证明报告来自该变异代码的执行。现在最终 `--gate acceptance` 额外**必须**提供 `counterfactual.mutation_run_record_path` 和 `mutation_run_record_sha256`。

可选执行器 `scripts/run_mutation.py` 目前仅支持 Python + pytest：从**原工作区复制一个临时副本**，在副本中写入登记的生产源码变异，运行指定测试，使用 pytest hook 检查被测模块在目标 testcase 执行期间实际加载的路径/变异 SHA，并比对测试源码 SHA；只有目标 testcase 真实失败、报告/日志与 run ID/nonce 绑定且原工作区未被修改，才写出独立运行记录。随后恢复版本的绿色测试记录仍必须符合原有门禁。

```bash
python scripts/run_mutation.py --workspace <project> --plan <official-plan.md> --source app.py --snapshot <plan/evidence/mutated.snapshot> --patch <plan/evidence/mutation.patch> --test-source tests/test_real.py --node-id tests/test_real.py::test_add --test-id tests.test_real::test_add
python scripts/validate_evidence.py --gate acceptance --workspace <project> --plan <official-plan.md> --manifest <plan/evidence/manifest.json>
```

将执行器 stdout 中的 `record_path` / `record_sha256` 写入 `counterfactual` 的 `mutation_run_record_path` / `mutation_run_record_sha256` 字段。报告与日志路径、SHA 均来自运行记录，不能拼凑其他测试的红色报告。没有该可追溯记录时是 `ACCEPTANCE_NOT_VERIFIED`，不得称作已通过业务验收。

**限定范围**：这是可审查的一致性链条，不是加密签名、OS 沙箱或可信硬件证明。拥有文件写权限者仍可伪造整个证据集；最终输出使用 `CONTROLLED_MUTATION_RUN_LINKED_HUMAN_REVIEW_REQUIRED` 并要求独立人员重跑/复核业务预期。Java、Maven、Gradle 暂未包含受控运行适配器，相关反事实验收应标记 `未验证`，不得把 Java 静态 AST/正则扫描视为通过证明。
