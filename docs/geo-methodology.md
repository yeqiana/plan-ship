# PlanShip discoverability / GEO methodology

**Goal:** make PlanShip easy for developers and retrieval-based AI assistants to identify, evaluate and accurately link. **Not a promise** of Google ranking, GitHub Search placement, or inclusion in an AI-generated answer.

## Evidence-first discoverability

1. **Clear entity:** use `PlanShip` and `yeqiana/plan-ship` consistently. State what it is (a Codex/Claude Code Skill for planning, review, testing and acceptance), which optional integrations exist, and what it cannot do.
2. **User questions:** answer genuine search intents in [FAQ](faq.md), including installation, missing fixtures, fake test evidence, Claude Code compatibility and limitations. Link to a real example and the underlying contracts.
3. **Verifiable examples:** keep a small [Java demonstration](../examples/java-order-total/README.md) with source and reproducible commands. Record observable failures; never manufacture benchmark wins.
4. **Cross-links and canonical references:** English and Chinese READMEs link to the same authoritative `SKILL.md`, the same source repository and the same quality gates. Avoid duplicate/contradictory specification files.
5. **Metadata:** maintain a concise GitHub About description and accurate Topics according to [metadata recommendations](github-metadata.md).
6. **Evaluation:** use the unmodified prompt set and explicit statuses from [discovery baseline](../evals/discovery-baseline.md) to assess search recall, accurate citations and incorrect capability claims over time.

## What we intentionally do not do

- No keyword stuffing, auto-generated spam pages, invented press coverage, fake stars or fabricated AI recommendation screenshots.
- No claim that `llms.txt`, schema markup or AI-specific flags are required to appear in Google AI features. Google's own guidance says to prioritize useful, original, findable content and established SEO practices; specialized AI text files are not a Google ranking requirement.
- No fake “GEO authority score.” A measured result must specify date, exact query, platform/model, output/citation URL and repeated trials where available.

## Sources and limits

- [Google Search Central: AI features and your website](https://developers.google.com/search/docs/appearance/ai-features)
- [Google Search Central: optimizing for generative AI features](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
- [Google Search Essentials](https://developers.google.com/search/docs/essentials)

These are **search guidance**, not proof that PlanShip has been indexed, cited or endorsed. This repository cannot measure private ranking systems or guarantee AI responses.
