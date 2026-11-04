# PlanShip plain-language HTML / 大白话 HTML 交付规则

Only published Markdown inside `.idea/docs/<plan-name>/大白话解释/` receives a same-stem `.html` file. Technical Markdown in the plan directory root **never** receives an HTML companion.

## Why this format

The optional [gen-ui Skill](https://github.com/yeqiana/gen-ui) recommends readable structure, mobile-friendly formatting, explicit evidence statuses and accessible fallback content. PlanShip uses these **presentation principles**, not an interactive UI runtime. HTML is a faithful offline, print-friendly view of the published Markdown; the Markdown remains authoritative. No hidden testing, remote requests, JavaScript, or unsupported interactive features.

## Output example

```text
<workspace>/.idea/docs/MyPlan/
  1. MyPlan-实施测试验收方案.md
  大白话解释/
    1. MyPlan-实施测试验收方案.md
    1. MyPlan-实施测试验收方案.html
  .document-index.json
```

When using optional Python 3.11+ tools:

```text
python <SKILL_ROOT>/scripts/doc_registry.py publish --workspace <workspace> --name MyPlan --key plan --title MyPlan-实施测试验收方案 --technical-file <draft-technical.md> --plain-file <draft-explanation.md>
python <SKILL_ROOT>/scripts/doc_registry.py verify --workspace <workspace> --name MyPlan
python <SKILL_ROOT>/scripts/doc_registry.py sync-html --workspace <workspace> --name MyPlan
```

`publish` writes **four linked files atomically with a recovery journal**: technical Markdown, plain-language Markdown, offline HTML, and index. HTML carries a SHA-256 marker for the exact plain Markdown, and the index stores `html_sha256`. `verify` compares both the HTML hash and a deterministic re-render; missing, edited, orphaned or stale HTML blocks final delivery. Legacy indexed Markdown without HTML is `BLOCKED` until safely backfilled with `sync-html`. Existing unmanaged HTML is never overwritten; missing indexed HTML is never silently recreated.

The zero-dependency renderer `scripts/plain_html.py` supports headings, paragraphs, tables, lists, links, code fences and Mermaid text fallback with responsive CSS and a restrictive Content Security Policy. Raw HTML and dangerous links are escaped. It does **not** claim to render Mermaid as an SVG or execute any UI controls. Mermaid's source and textual explanation remain visible offline.

Without Python, a capable agent may produce the same plain HTML using native host file-writing tools; it must inspect source Markdown consistency and mark automatic atomicity/verification `未验证`. No HTML requirement changes the fact that actual business tests and manual verification remain separate.

## Historical documents

For already-indexed plan documents, run `sync-html` once per named plan folder. It only creates missing HTML where the registered Markdown hashes match; it rejects unmanaged HTML, symlink targets and modified documents. If the operation is interrupted, `recover` / rerunning `sync-html` resolves validated partial state.
