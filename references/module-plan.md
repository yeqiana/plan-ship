> **Plan module / English overview.** Before analyzing, really load prerequisite Skills. Review actual repository code, attachments, optional fixtures and existing edits. Present a complete v0 plan, then perform two distinct evidence-backed review/revision cycles with a final recheck. Keep scope minimal and publish paired, stable-numbered Markdown. Plan-only mode never writes business code.

# 模块 A：方案编写执行细则

## A0 输入核验

读取需求、当前会话附件及其可访问内容、项目目录、仓库约束、构建脚本、测试基础设施、已有相关实现。只依据实际看到的内容写事实；缺失说明“未确认”。

开始前检查：

1. 根目录：`git rev-parse --show-toplevel`（非 Git 项目则用实际项目根）。
2. 工作树：`git status --short`，识别并保留已有改动。
3. 指令：`AGENTS.md`、`CLAUDE.md`、仓库编码约定、测试规范（存在时读取）。
4. 用户附件：记录名称、用途、关键约束。无法读取则写明，不猜内容。
5. `test-dir/`：存在时读取与需求相关文件清单，不存在直接跳过。
6. **在开始 A0 项目分析前**先完成 P0：实际加载 `ai-coding-collaboration` 再加载 `intelligent-ui`；任一缺失必须 BLOCKED，不允许推测技能内容。

## A1 v0 初版输出

必须先在对话中呈现完整可读的初版 MD，至少包含：

- 背景与目标、功能点、非目标、验收定义。
- 当前代码路径、已有流程、最小变更文件清单/影响矩阵；声明拒绝的过度设计及理由。
- 架构/数据/API/依赖变更（没有也写“本次不涉及”）。
- 实施顺序、风险、兼容与回滚方案。
- 正常/边界/异常/回归测试：每项都标明 ID、输入、操作、预期、测试方式。
- 验收命令与证据格式（命令先核对是否项目真实存在）。
- 尚未核实的假设、可能阻断点及处理策略。

初版标为 `v0 初版（待评审）`，不在 `.idea/docs/` 保存“最终”文件。

## A2 两轮强制评审与补强

每轮至少：

1. **评审**：选择一个明确的检查视角（例如需求追踪、接口兼容/回归、异常与运维），逐条检查方案，并引用代码路径或需求片段等可检查证据。
2. **问题**：按 `阻断 / 重要 / 建议` 分级。找不到问题也需明确写“本轮未发现新阻断”，对下一轮可验证性做实质增强，不能捏造 bug。
3. **补强**：更新正文，同时记录原问题、具体增补点、原因、效果。至少两轮都有可证明的修订。
4. **复核**：核对修订确实覆盖发现项；如果仍有阻断问题，继续进行额外评审—补强循环。

至少形成 `v0 → R1 → v1 → R2 → v2 → 最终复核`，任一轮不得与前一轮完全重复同样的泛泛评论。

## A3 最终结构门禁

校验：

- 需求—改动—测试—验收矩阵闭合；没有只写“后续测试”的空洞项。
- 明确“不改什么”，关键回归用例齐全。
- 设计有具体文件/函数/接口定位（不能访问源码则列未确认项，不得假装已核实）。
- 两轮评审与补强记录内容不同、可追踪；最终复核无阻断。
- 输出给用户的 Markdown 与保存的 Markdown 内容一致、信息完整。

按照 `doc_registry.py init/publish` 落盘到 `<repo>/.idea/docs/<方案名称>/<编号>. <方案名称>-实施测试验收方案.md`，并同步生成 `大白话解释/` 下同编号副本。技术版与解释版一起校验，不得更新一个而漏掉另一个。详见 `references/plain-language.md`。日期按项目/宿主本地日期，不在方案中使用未来结果冒充实测。
