# 从旧版 Skill 迁移到 PlanShip

旧名称：`project-plan-delivery`。新名称：**`plan-ship`**，对应 Codex `$plan-ship` / Claude `/plan-ship`。新仓库根目录直接包含 `SKILL.md`。

## 安全迁移步骤

1. 先备份已有旧 Skill 目录及用户级 `AGENTS.md` / `CLAUDE.md`，不要在原目录直接覆盖。
2. 安装新仓库到 `~/.agents/skills/plan-ship`（Codex）或 `~/.claude/skills/plan-ship`（Claude）。
3. 如果过去执行过旧版 `route_manager.py --install`，应先用**旧版脚本**的 `--remove` 清除旧标记，再使用新版本的 `route_manager.py --install`。新版本不自动移除旧标记，以免破坏其他规则。
4. 新建 Agent 会话，显式调用 `$plan-ship` 或 `/plan-ship`，检查主 Skill 和依赖的实际加载路径。
5. 已生成的 `.idea/docs/<方案>/` 不应被自动移动或重排；复用既有证据前必须重新校验。新版本的源码指纹算法域已使用 `plan-ship-v1`，旧版证据可能需要重新执行并记录。
6. 确认新版本正常使用后，再自行处理旧目录；不要同时启用两个自动路由造成触发冲突。

## 为什么不做静默兼容别名

Skill 的自动触发由宿主控制。继续保留两个有效名称，会造成同一请求匹配两个版本，难以确定真正执行的是哪份规则。因此新版本只有一个正式 ID `plan-ship`。迁移需要明确进行。

## 升级后核对

- `[ ]` 生效目录中的 `SKILL.md` 第一段是 `name: plan-ship`。
- `[ ]` `agents/openai.yaml` 中使用 `$plan-ship`。
- `[ ]` 用户常驻路由中不再存在旧版的触发片段。
- `[ ]` `code-pact` / `gen-ui` 已找到并实际读取。
- `[ ]` 测试没有被跳过，实际验收状态真实。
