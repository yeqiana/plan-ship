> **Optional discovery.** PlanShip v1.3 core does not require, download or activate `code-pact` / `gen-ui`. Files in a different host directory are never proof the current host loaded them. Python is only a diagnostic helper, never the startup gate.

# Skill 发现与可选集成

1. 主 Skill `plan-ship` 在宿主实际加载后可直接使用，无 WebCodex、Python 或其他依赖。
2. 如果宿主已经具备 `code-pact` / `gen-ui`，可以按宿主优先级选择加载，未加载时按 PlanShip 自带最小改动和普通 Markdown 规范继续。
3. **默认无网络和文件安装副作用**。Python 可选诊断：`python scripts/preflight.py --project "<项目>" --host codex --read-content --json`，支持 `--host claude`。如未指定宿主，报告 `UNKNOWN`，绝不把另一个宿主的 Skill 当作当前宿主已加载。
4. 只有在用户明确授权时加 `--install-optional --host codex|claude`，详见 [安装安全说明](../docs/dependencies.md)。失败不阻断核心流程；不能谎称依赖或宿主已加载。


## 文件发现和宿主加载不是一回事

- `discover_skills.py` 只是读取文件系统中的候选，不证明 Agent 主动加载；跨宿主候选只列为 `other_host_candidates`。
- `preflight.py` 默认只读；返回 `READY_CORE_*` 仅表示 PlanShip 核心没有辅助依赖阻断，不意味着外部 Skill 已加载。
- 如需可选安装，必须显式选择宿主且使用已有真实用户目录，Windows SYSTEM 环境拒绝安装。

## 安装边界

可选安装必须由用户明确要求；不会覆盖已有 Skill、不会自动运行下载来的脚本、也不会把非 Git 来源标记为官方可信。无 Python 时完全跳过这些辅助工具即可。
