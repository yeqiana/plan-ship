# PlanShip dependencies: official sources and safe automatic installation

PlanShip has two **required, distinct** Skills. These are the canonical IDs and repositories; don't replace them with other names in new docs or project guidance.

| Skill ID | Purpose | Canonical GitHub source |
| --- | --- | --- |
| `code-pact` | Scope discipline, minimal sufficient changes, risk and review boundaries | [yeqiana/code-pact](https://github.com/yeqiana/code-pact) |
| `gen-ui` | Markdown, diagrams and output presentation | [yeqiana/gen-ui](https://github.com/yeqiana/gen-ui) |

## Automatic bootstrap (default when PlanShip's preflight is invoked)

Before any business project analysis, PlanShip must discover existing installed Skills and try to install **missing** dependencies via `scripts/preflight.py`. The installer uses a fixed allowlist of these two HTTPS clone URLs (no arbitrary URL/user-provided repository input):

```text
https://github.com/yeqiana/code-pact.git
https://github.com/yeqiana/gen-ui.git
```

The destination is an **already existing**, valid Codex or Claude user Skills root. If PlanShip is installed within one of the discovered roots, that root takes priority; otherwise the first existing root is selected in this order:

1. `~/.agents/skills` (Codex modern)
2. `${CODEX_HOME:-~/.codex}/skills` (Codex legacy)
3. `~/.claude/skills` (Claude user)

If both Codex and Claude have separate valid Skills roots, install PlanShip in the relevant host root and launch its preflight **from that host**. Installations do not automatically propagate across unrelated host roots. The installer refuses to create new Agent / Skills roots. It also refuses a Windows SYSTEM service profile; run it as the actual user's host process. Project-local and plugin-provided Skills may already satisfy the dependency without a clone, subject to the host's actual rules.

```powershell
# Default: ensure missing dependencies (network/write only if missing); then read and hash.
python "$HOME\.agents\skills\plan-ship\scripts\preflight.py" --project "D:\workspace\my-project" --read-content --json

# Pure read-only diagnostics: never install.
python "$HOME\.agents\skills\plan-ship\scripts\preflight.py" --project "D:\workspace\my-project" --read-content --no-auto-install --json

# Direct safe bootstrap (same official allowlist):
python "$HOME\.agents\skills\plan-ship\scripts\ensure_dependencies.py" --json
```

Use the real PlanShip installation path when it differs from these examples.

## Safety and failure behavior

- **No automatic overwrites.** If `code-pact/` or `gen-ui/` already exists, verify its frontmatter. If missing, wrong, or unsafe, stop with `BLOCKED_CONFLICT` and require a human to resolve it.
- **No new Agent roots.** If none exists, return `BLOCKED_NO_EXISTING_SKILLS_ROOT` instead of creating one.
- **No arbitrary shell commands in cloned Skills.** Installation downloads files only and verifies each cloned `SKILL.md` declares the expected ID. An Agent must separately inspect and load the actual rules. Never run scripts from an unreviewed clone.
- **Fail closed.** Git unavailability, source mismatch, network failure, permission denial or race => `BLOCKED`, with no false claim of success. Git authentication is handled by the user's existing environment; don't print credentials or embed tokens in clone URLs.
- **Atomic staging.** Clone into a temporary folder under the selected root, validate, and only then rename into the final directory. On errors, remove only the temporary folder, not user-owned files.
- **Sources are moving targets.** A newly cloned `main` is not a pinned release. The installer records the checked-out commit SHA for audit; projects needing a locked dependency set should approve exact revisions and audit the GitHub repositories independently. This file is not a supply-chain security certification.
- **Host truth matters.** `INSTALLED` proves a filesystem clone, not that Codex/Claude automatically selected it, read its references, or followed the instructions. `preflight.py --read-content` only demonstrates the helper's reads. The Agent must perform its own host-specific confirmation before continuing.
- **Legacy aliases.** A dependency stored under an obsolete folder name is never automatically deleted or renamed; an additional candidate may require host-specific manual selection. Leave all user files untouched.

## Required startup sequence

1. Discover PlanShip and dependencies in actual host and workspace registrations.
2. If a dependency is missing from standard installed locations, run default preflight/auto-bootstrap.
3. If Git/network/target verification fails, mark `BLOCKED` and do not begin analysis.
4. Re-discover the installed dependencies and check versions/any competing candidates.
5. Have the Agent actually load **code-pact first**, then **gen-ui** (including required references). An installer or preflight checker must never claim the host loaded them.
6. Only then analyze the business project, inspect test fixtures, draft the plan, and proceed through the established evidence/review gates.
