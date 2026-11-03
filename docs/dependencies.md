# Optional integrations and dependency-free core / 可选集成

**PlanShip v1.3 works standalone.** Its only activation condition is that the host actually loads `plan-ship/SKILL.md`. The workflow does **not** require WebCodex Runner, Python, Git, MCP, or any other Skill.

| Optional Skill | Repository | Enhancement |
|---|---|---|
| `code-pact` | [yeqiana/code-pact](https://github.com/yeqiana/code-pact) | Change-scoping and review conventions |
| `gen-ui` | [yeqiana/gen-ui](https://github.com/yeqiana/gen-ui) | Markdown and presentation guidance |

PlanShip embeds its own minimal scope, evidence, plain-language and non-fake-test rules. If both optional Skills are absent, **continue normally**. Do not infer that a Skill in the *other* host's installation has been loaded by the current host.

## Optional Python tools

`preflight.py`, `doc_registry.py`, `validate_docs.py`, `validate_evidence.py` and `plain_quality.py` require Python 3.11+ **only if you explicitly run them**. Native file tooling can write paired Markdown files without Python, but must not claim atomic, checked publication or automated evidence validation when those helpers were not executed.

The optional discovery command is **read-only by default**:

```text
python scripts/preflight.py --project <project> --host codex --read-content --json
```

Only after explicit user approval, install optional Skills into an existing Skills directory **for the specified host**, not another host:

```text
python scripts/preflight.py --project <project> --host codex --install-optional --json
# or --host claude
```

The allowlisted Git sources are `https://github.com/yeqiana/code-pact.git` and `https://github.com/yeqiana/gen-ui.git`. The script rejects Windows SYSTEM profiles, missing host roots, symlink targets, wrong Skill names, mismatched Git origins, clone failures, and concurrent target-directory creation. Existing non-Git copies are reported as **`PRESENT_UNVERIFIED`**, not certified official. Even a matching Git origin does not certify file integrity or runtime activation. New optional installs record checked-out revision hashes; no script in a cloned Skill is executed automatically.

If install fails, **the optional install attempt fails**, but PlanShip's self-contained plan and review process remains usable. No automatic network requests or silent downloads occur during ordinary PlanShip invocation.

## v1.3.1 Preflight status and optional routing

`preflight.py` is a read-only *filesystem diagnostic*, never a host activation probe. `core_has_no_external_dependencies=true` describes the design only. The deprecated `core_ready` value is conservative (`false`); use `plan_ship_activated=NOT_FOUND/NOT_VERIFIED/HOST_UNKNOWN` and actual host session evidence, not file presence, to determine whether the Skill has been invoked. Absence must not cause forced Python setup.

Optional `route_manager.py --install/--remove` uses a cooperative `.plan-ship-route.lock` file and checks the original file's identity and contents immediately before replacement. A conflict stops the operation without overwriting detected external changes. **Portable file operations cannot guarantee atomic compare-and-swap against non-cooperating writers in the final rename window**; avoid concurrent manual edits, back up instructions and resolve stale locks explicitly.
