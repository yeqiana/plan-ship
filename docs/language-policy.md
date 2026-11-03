# Language and translation policy / 语言规范

**One authority, multiple entry points.** [`SKILL.md`](../SKILL.md) is the single authoritative normative Skill file, written in English with Chinese trigger examples. The [`README.md`](../README.md) and [`README.zh-CN.md`](../README.zh-CN.md) are user guides, not competing rulebooks.

## English

- Use English for public discovery metadata, English user requests and the primary explanation of technical contracts.
- Explicitly retain Chinese terms used as activation keywords (`方案编写`, `方案实施测试验收`, `全流程`, `两轮评审`, `手动验收方案`) and identifiers required by existing real projects (`大白话解释/`).
- Do not translate machine flags (`--workspace`), JSON keys, Skill IDs (`plan-ship`, `ai-coding-collaboration`, `intelligent-ui`), evidence states (`PASS`, `BLOCKED`), stable document numbers, or repository links.
- A plain-language companion follows the user's language, even when its storage directory remains `大白话解释/`. Do not pass off a machine-generated explanation as validated by a real nontechnical user.
- **Current limitation:** `scripts/validate_docs.py` still requires Chinese structural headings, review fields and terminal status keys. English narrative and titles can coexist with those labels, but a fully English formal MD structure is not supported by this release. Do not translate validated labels silently.
- The source reference files may contain Chinese implementation details. Any translation of normative constraints must preserve semantics. Where translation is incomplete, state that transparently instead of claiming full internationalization.
- When editing a contract, check its linked examples, both READMEs, CLI docs, metadata, tests and README anchors for parity.

## 中文

- 用户用中文提问时，按中文输出；保留中文模式名称和方案目录规则。
- 英文化是提升英文开发者理解与 Skill 发现能力，不是变更 Python 校验脚本、真实测试门禁或原有中文用户体验。
- 中英文有不一致时，以实际 `SKILL.md` 与执行脚本中可验证的约束为准，及时修正说明文档，不自动猜测另一语言的意思。
