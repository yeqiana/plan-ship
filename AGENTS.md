# PlanShip repository development guidance / 仓库开发约定

This file guides maintainers only. The authoritative user-facing Skill contract is [`SKILL.md`](SKILL.md), not this file. Keep translations semantically equivalent, avoid keyword stuffing, keep `code-pact` and `gen-ui` as optional integrations, and never claim unobserved GEO/search rankings or host invocations. Run the package and full tests before release; publish only explicitly scoped changes.

## 中文开发约定

仅约束**维护本仓库**的 Coding Agent，不替代安装到业务工程后的 `SKILL.md`。

- 修改前检查 `SKILL.md`、有关 `references/` 和测试，优先最小改动。
- 保留 `code-pact`、`gen-ui` 可选集成名称，不作为硬依赖，它们是其他 Skill，不属于本仓库改名范围。
- 改 Skill 触发名、路径或规则时，同步更新 `agents/openai.yaml`、路由脚本、README（中英文）、示例与测试。
- 不得伪造测试成功；运行 `python scripts/validate_package.py` 和 `python -m unittest discover -s tests -p 'test_*.py' -v`，不能执行时如实报告。
- 不改用户原有工作区的其他仓库或未提交变更；需外部 Git 写入时必须得到明确授权。
- Git 提交说明用中文，三段格式：类型、空行、改动模块、空行、项目名。例如：

```text
feat: 完善方案工作流校验

文档门禁,测试证据

plan-ship
```

- Optional integration IDs and URLs are [code-pact](https://github.com/yeqiana/code-pact) and [gen-ui](https://github.com/yeqiana/gen-ui). Never auto-install without user approval; opt-in bootstrap stays within the selected host root, never overwrites existing Skills and does not imply host loading.
