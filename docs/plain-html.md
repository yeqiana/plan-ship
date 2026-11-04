# PlanShip 大白话 HTML 与主入口（v1.3.4）

## 必须交付的内容

只为 **`<项目>/.idea/docs/<方案>/大白话解释/` 下已正式登记的 Markdown** 生成同名 HTML，不改变技术版 Markdown。每个方案目录必须额外生成 **`大白话解释/index.html`**：它是全部已登记大白话 HTML 的静态离线入口，包含编号、标题、登记更新时间及“已登记，语义待独立复核”状态。不存在数据查询、脚本、外部 CDN 或伪造的互动控件。

```text
<project>/.idea/docs/MyPlan/
  1. MyPlan-实施测试验收方案.md
  大白话解释/
    index.html               # 主入口（所有受管文档导航）
    1. MyPlan-实施测试验收方案.md
    1. MyPlan-实施测试验收方案.html
  .document-index.json      # 包含 HTML 和入口页的 SHA-256
```

使用可选 [gen-ui](https://github.com/yeqiana/gen-ui) 的信息设计原则：可读性、层次、移动适配、无障碍、失败状态与证据可见。该 Skill **不**提供静态 HTML 转换 API，不是交互运行时，也不作为 PlanShip 的强制依赖。HTML 由 PlanShip 受管工具或宿主原生文件操作生成，MD 是事实来源。

## 安全覆盖与历史迁移

**不能对所有同名 HTML 全量覆盖。** 按来源分三类：

1. **已登记且当前文件 SHA-256 与索引一致**：允许使用新生成器更新，随后同步更新索引与 `index.html`。
2. **有正式 MD，但尚无受管 HTML**：源 MD 与已登记指纹完全一致、目标 HTML 不存在时，允许补生。
3. **手工维护、未登记、哈希不符、未知来源或孤儿 HTML**：直接 `BLOCKED`，不删、不改，报告冲突和人工处理方式。

可选 Python 3.11+ 脚本（PlanShip 核心工作流仍不依赖 Python）：

```bash
# 默认仅预览可能更新的 HTML 数量，不写入文档
python scripts/doc_registry.py sync-html --workspace <project> --name <plan-name>
# 核对后显式提交更新，包括主入口与索引
python scripts/doc_registry.py sync-html --workspace <project> --name <plan-name> --apply
# 验证 HTML、MD、主入口与索引的全部哈希和确定性生成内容
python scripts/doc_registry.py verify --workspace <project> --name <plan-name>
# 任一步骤异常后检查未完成事务再恢复
python scripts/doc_registry.py recover --workspace <project> --name <plan-name>
```

`publish` 更新技术 MD、大白话 MD、同名 HTML、主入口 HTML 和索引 JSON，使用可恢复事务；`sync-html --apply` 在一个事务内更新当前方案全部有变化的受管 HTML、主入口及索引。注意：这不是浏览器端视觉验收，真正展示效果、图片存在性和可访问性仍需要用户或宿主检查。

## HTML 保真与安全

- 转换表格时，代码跨度中的 `|`、转义竖线 `\|` 都不会拆错列；验收状态 `PASS/FAIL/BLOCKED` 必须保留。无法按列解析的行原样可读显示，不能静默丢弃。
- 安全相对路径图片（如 `![截图](./screenshot.png)`）支持原位展示，但对应本地图片文件必须真实存在；拒绝远程图片、危险协议、绝对路径、越界路径和未转义的原始 HTML。
- Mermaid 保留为带解释的文本流程图，不伪装成 SVG/交互图。
- 无 JavaScript、无外部字体/CDN，适合本地浏览器及打印；普通浏览器的文件 URL 行为可能不同，应做浏览器验收。
- 没有 Python 时可由 Agent 依照本规范用宿主文件工具生成静态 HTML；必须把事务回滚/哈希自动校验标为 **未验证**。
