> **Gen UI presentation alignment, not a runtime dependency.** The actual local `gen-ui/SKILL.md` recommends legible hierarchy, concise evidence, accessible labels, honest statuses and a complete noninteractive fallback. Follow a host-loaded version when available, otherwise use these built-in presentation rules.

# Gen UI 风格的大白话 HTML（可选集成）

- `gen-ui` 官方源码：[yeqiana/gen-ui](https://github.com/yeqiana/gen-ui)。它是**呈现规则**，不是 HTML 渲染引擎，也不是 PlanShip 的强制依赖。
- 仅对 `.idea/docs/<方案名>/大白话解释/` 下已经登记的正式 Markdown 生成同名 `.html`；根目录技术 MD **不生成 HTML**。
- 页面本地打开、响应式、可打印。标题层级、操作步骤、真实测试状态、数据表格和风险说明必须可读；不能因为美观隐藏失败或未验证状态。
- HTML 内容与大白话 MD 对应；原 Markdown 是权威来源，不得另行总结、补造数据。采用安全 HTML 转义，无脚本、无外部字体/CDN，禁止把用户输入当作可执行标记。
- Mermaid 在离线 HTML 中按文本流程图展示，保留源 Markdown 的箭头/节点说明。没有实际渲染器时，不承诺复杂流程图会渲染成图像。
- 有 Python 时建议 `scripts/doc_registry.py publish` 同步生成三种文档和索引，`verify` 核查 HTML 指纹及一致性，旧文档用 `sync-html` 做安全补齐。无 Python 时宿主原生工具也可生成 HTML，但必须人工核对配对与版本并标记自动原子性未验证。
- `gen-ui` 的交互演示协议不适用于离线报告页面：**不生成假按钮、滑块或任何没有运行时的互动**。

参见 [大白话规范](plain-language.md)、[HTML 交付说明](../docs/plain-html.md)。
