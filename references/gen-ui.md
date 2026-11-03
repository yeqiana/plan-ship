> **Gen UI compatibility / English overview.** Load the actual installed gen-ui Skill and apply its effective host rules. Terminal-only hosts should get complete, copyable Markdown; never invent rendered controls, charts or screenshots. Layout should never conceal real tests, failures or blockers.

# Gen UI 适配（强依赖）

## 必须先发现

PlanShip v1.3 自带最小改动与普通 Markdown 规范，`code-pact`、`gen-ui` 都是可选增强。当前宿主实际拥有并已加载时才遵守，缺失不阻断项目分析，不自动下载；不能拿记忆中的摘要冒充加载。

若实际 Skill 定义和下述摘要有差异，以实际找到的当前宿主有效版本为准。任一缺失时 BLOCKED，不得伪称严格执行，也不能自动使用记忆中的旧版内容替代。

## 已知的 gen-ui v1 兼容要点

- **有兼容 UI renderer/工具时**：按真实 `references/ui-protocol.md` 生成组件树；如果该协议要求 `schema_version`, `mode`, `summary`, `fallback_markdown`, `ui`，严格填写和校验。
- **只有终端/普通 Markdown 时**：输出清晰、完整、可自包含的 Markdown，不裸露 JSON 组件树，不虚构按钮、状态或已经渲染的图表。
- **宿主有自己的 UI 机制时**：先遵循宿主合法组件和工具能力，避免假定其他平台的私有交互协议可用。
- **视觉排版**：结论和状态先行；复杂对比使用表格，多阶段任务使用步骤；避免大卡片墙，避免冗长重复，移动端阅读友好。
- **数据与交互**：不虚构执行结果、指标、证据；UI 不是执行授权；核心结论、失败和安全限制必须在 Markdown 退化内容中保留。
- **最终落盘 MD**：一律能在 GitHub、VS Code、IDEA 的常规 Markdown 预览器中直接阅读和复制执行；不依赖渲染器。

## 推荐用户可见结构

```
结论/当前门禁状态
关键变更与风险（短表格）
评审轮次（R1/R2/Rn 与证据）
测试/验收结果（命令、退出码、失败与阻塞）
文件路径/本地提交状态
手动复现步骤（若已实际验收通过）
```

交互式视图绝不能取代实际 `.idea/docs/` 文件或执行日志。
