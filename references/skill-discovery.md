# 默认 Skill 发现（全局先搜，项目与宿主随后）

优先级：**先搜索** Codex 与 Claude 默认本地目录；命中并不代表自动覆盖当前宿主真正生效的版本。所有候选只读，先检查 `SKILL.md`，确认名称与所在目录，必要时读取所引用的 `references/`。无论引用哪种辅助 Skill，都先做相同的检索。

| 检查顺序 | 目录 |
|---|---|
| 1 | `~/.agents/skills/<name>/SKILL.md`（Codex 用户级） |
| 2 | `${CODEX_HOME:-~/.codex}/skills/<name>/SKILL.md`（历史兼容） |
| 3 | `~/.claude/skills/<name>/SKILL.md`（Claude 用户级） |
| 4 | 当前目录沿途至仓库根：`.agents/skills/<name>/SKILL.md` |
| 5 | 当前目录沿途至仓库根：`.claude/skills/<name>/SKILL.md` |
| 6 | 宿主内建技能、插件/组织注册表（需相应接口） |
| 7 | 用户另外指定的目录；若仍缺失再考虑其他来源（不得自行下载） |

Windows 下 `~` 通常代表当前进程的 `%USERPROFILE%`，`CODEX_HOME` 可能另有配置；需核对当前宿主。`discover_skills.py` 只检查当前机器可见的文件系统目录，不会读取另一个电脑上的 Windows 安装位置，不保证能找到插件注册技能。

**从任何工作目录运行的正确方式：**

```powershell
$skillRoot = 'C:\Users\<用户>\.agents\skills\plan-ship' # 替换为实际找到的路径
$project = 'D:\workspace\my-project'
python "$skillRoot\scripts\discover_skills.py" --project "$project" --name intelligent-ui --json
```

使用该工具前先确定 `skillRoot`（来自真实 `SKILL.md` 的父目录），不要切换工作区或写 `python scripts/discover_skills.py`；结果 `found=false` 时还要按宿主提供的技能接口复核。P0 必须同时找到并真正加载 **`ai-coding-collaboration` 与 `intelligent-ui`**。当前用户要求严格执行，任一缺失则必须 BLOCKED，不可自行降级到另一套规则。普通 Markdown 仅在已加载的 intelligent-ui 本身允许的宿主降级范围内合法。建议先执行 `python "<SKILL_ROOT>/scripts/preflight.py" --project "<项目根>"`；该检查只涵盖可见的默认目录，宿主原生注册表仍需人工/宿主接口实际查证。

## v2.3：发现、文件读取、Agent 应用不是一回事

1. 在默认的 Codex / Claude 目录运行 `preflight.py --project "<项目>" --read-content --json`，检查 `ai-coding-collaboration` 与 `intelligent-ui` 的完整 `SKILL.md` 和主文件中直接列出的 `references/*.md`，记录实际路径、SHA-256、读取结果。失败立即 `BLOCKED`。
2. `READY_FILESYSTEM` 仅表示文件被找到，`READ_FILESYSTEM_CONTENT_AGENT_CONFIRMATION_REQUIRED` 仅表示探测器已经真实读取文件；**这两种状态都不能冒充 Agent 已经执行这些规范**。
3. Agent 必须依据当前宿主的技能选择规则核对真正生效的版本，并亲自读取已选中 Skill 的规则及执行所需引用；多个版本需要明确选择，不擅自混合。记录所选路径和真实摘要。宿主插件/内建技能需要使用宿主接口确认，而非用本地文件探测结果替代。
4. 只有完成上述动作并且没有规则冲突，才能在本次会话声明 S 门禁通过并开始分析；如果权限不足、引用不存在或已选版本不一致，必须停止分析。
