---
name: graphify-architecture-review
description: >-
  Run reusable architecture analysis for codebases using Graphify semantic
  graphs, subagent extraction, graph synthesis, source-search validation,
  graph-shape review, and follow-up refactor planning. Use when asked to
  analyze repo architecture, god nodes, surprising edges, topology, module
  boundaries, or graph-derived cleanup/refactor opportunities.
allowed-tools: Bash, Read, Glob, Grep, Write, Edit, Agent
argument-hint: "<repo path or scoped subtree>"
---

# Graphify Architecture Review

Use this skill to turn a codebase graph into source-validated architecture
insights and concrete refactor plans.

Read `references/SOP.md` before running the workflow. It is the detailed
operating model for this skill.

## Procedure

1. Read repo guidance, architecture docs, planning docs, and search guidance.
2. Identify generated, vendor, asset, raw-log, build, and binary paths to
   exclude or downrank.
3. Ensure `graphify-out/` and `.graphify_*` are ignored unless the user wants
   generated graph artifacts versioned.
4. Run Graphify on the repo or scoped subtree.
5. Generate and inspect `GRAPH_REPORT.md`, `graph.json`, and `graph.html`.
6. Label communities in plain domain language.
7. Filter or discount generic nodes before interpreting architecture.
8. Package first-pass findings into concise review docs.
9. Validate graph claims with source search and file reads.
10. Dispatch investigation agents for god nodes, surprising edges, generated
    questions, and topology anomalies.
11. Dispatch synthesis agents to identify top refactor opportunities from the
    curated docs.
12. Write plans only for source-validated, high-leverage opportunities.
13. Ask fresh agents to review plans before finalizing.

## Subagents

Use subagents for extraction chunks, investigation, synthesis, and plan review.
Give each subagent exact files or docs, one bounded question, and a required
output shape.

Do not delegate final acceptance. Validate important conclusions locally against
source.

## Noise Filtering

Before judging god nodes, bridges, or topology, filter or discount generic
labels such as:

- `.new()`
- `.default()`
- `.drop()`
- `.clone()`
- `.from()`
- `.into()`
- `main()`
- `run()`

Prefer normalization over deletion. Qualify methods by receiver/type when
possible, remove unresolved generic nodes and incident inferred edges, preserve
domain-specific short methods, and treat `.load()`, `.open()`, `.save()`,
`.build()`, and `.parse()` as suspicious but not automatically noisy.

## Insight Extraction

Process `GRAPH_REPORT.md` in this order:

1. Corpus summary and graph size
2. Community hubs and labels
3. God nodes
4. Surprising connections
5. Hyperedges
6. Ambiguous edges
7. Knowledge gaps and thin communities
8. Suggested questions

For each important finding, record graph evidence, source evidence, verdict,
and recommended action. Use verdicts: `good`, `neutral`, `bad`, `artifact`, or
`watchpoint`.

Use Graphify for discovery:

```sh
graphify explain "<node>" --graph graphify-out/graph.json
graphify path "<node-a>" "<node-b>" --graph graphify-out/graph.json
graphify query "<question>" --graph graphify-out/graph.json --budget 2000
graphify query "<question>" --dfs --graph graphify-out/graph.json --budget 2000
```

Use source search for proof. Rewrite graph output as observable source behavior
and search the likely owner path before accepting a graph claim.

## Output Artifacts

Create concise review docs using the repo's preferred docs location, or an
ignored scratch folder until the user chooses a durable location:

- `index.md`
- `overview.md`
- `god-nodes.md`
- `surprising-connections.md`
- `question-answers.md`
- `graph-shape-findings.md`
- one refactor plan per validated opportunity

Keep generated graph artifacts uncommitted unless explicitly requested.

## Graph Shape

Treat graph topology as triage, not proof. Do not trust visual position unless
coordinates are persisted. Filter `contains` edges and generic labels first.
Validate stragglers, bridge nodes, and community boundaries in source.

Classify topology findings as real boundary, watchpoint, fixture noise,
file-node artifact, generic-label artifact, or not actionable.

## Quality Gates

- Graph has nonzero nodes and edges.
- Expected output files exist.
- Chunk failures are below threshold.
- Generated artifacts are ignored or intentionally versioned.
- Strong claims have graph and source evidence.
- Generic-node artifacts are filtered or explicitly classified.
- Refactor plans include acceptance criteria and verification commands.
- Tracked docs pass lint.

## Stop Conditions

Stop when graph findings are classified, high-value questions are
source-validated, weak topology findings are downranked or promoted with
evidence, strong opportunities are captured as plans, and no new validated
opportunity outranks the current plan set.
