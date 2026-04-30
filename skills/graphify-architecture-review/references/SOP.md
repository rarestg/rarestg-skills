# Graphify Architecture Review SOP

Use this SOP to turn a codebase graph into source-validated architecture
insights and concrete refactor plans. It is written for any repo where
Graphify can generate a semantic graph and where agents can inspect source.

## Expected Inputs

- A target repo or scoped subtree.
- Repo guidance, if present: contributor notes, architecture docs, design docs,
  plan workflow docs, search guidance, and test strategy docs.
- Graphify generated artifacts:
  - `graphify-out/GRAPH_REPORT.md`
  - `graphify-out/graph.json`
  - `graphify-out/graph.html`
  - `graphify-out/manifest.json`
  - `graphify-out/cost.json`
- Scratch space for generated chunk JSON, subagent notes, and working docs.
- A source-search tool for validation. Prefer semantic search when available;
  fall back to `rg` and direct file reads.
- Subagents for extraction, investigation, synthesis, and review.

## Core Rules

- Treat graph output as a lead generator, not proof.
- Validate every important graph claim against source.
- Keep generated graph artifacts out of commits unless explicitly requested.
- Commit or preserve only curated findings, decisions, and refactor plans.
- Prefer concise documents over large pasted graph output.
- Use human judgment for prioritization, boundaries, and plan quality.
- Use subagents for bounded investigation, not final acceptance.
- Start the review corpus early; use it as input for second-wave planning.

## 1. Prepare The Repo

1. Read repo orientation docs before running graph analysis.
2. Identify the current product or system boundaries.
3. Identify generated, vendor, build, binary, decorative, and raw-log paths.
4. Decide whether to include tests, docs, archived plans, examples, and sample
   data.
5. Include tests by default, but classify fixture hubs separately from product
   architecture.
6. Include historical docs only when they may explain current architecture;
   classify them as current, deferred, archived, or tooling-only.
7. Ensure `graphify-out/` and `.graphify_*` are ignored by git and semantic
   search unless the project intentionally versions analysis artifacts.

## 2. Build The Graph

1. Run Graphify detection on the selected repo or subtree.
2. If the corpus is too broad, scope to source plus relevant architecture docs.
3. Split semantic extraction into directory-coherent chunks of about 20 to 25
   files.
4. Put each image, audio, or video artifact in its own work unit when semantic
   extraction needs multimodal context.
5. Run AST extraction and semantic extraction in parallel when possible.
6. Dispatch semantic extraction agents with exact file lists.
7. Require each extraction agent to write valid JSON with `nodes`, `edges`, and
   optional `hyperedges`.
8. Validate each chunk before merging.
9. Deduplicate nodes by id.
10. Merge AST and semantic extraction outputs.
11. Build the graph, cluster communities, label communities, and generate:
    `GRAPH_REPORT.md`, `graph.json`, and `graph.html`.
12. Stop if the graph is empty or more than half the semantic chunks failed.

### Extraction Agent Prompt

```text
Read only the listed files. Produce a graph fragment as valid JSON with nodes,
edges, and optional hyperedges. Mark each edge EXTRACTED, INFERRED, or
AMBIGUOUS. Focus on named concepts, architecture boundaries, shared data,
non-obvious semantic links, and rationale. Do not re-extract imports if AST
extraction already covers code. Output JSON only.
```

## 3. Normalize Or Filter Noise

Apply filtering before serious interpretation. If the tool cannot filter before
clustering, create a filtered graph copy and rerun clustering/reporting.

Default noisy labels:

- `.new()`
- `.default()`
- `.drop()`
- `.clone()`
- `.from()`
- `.into()`
- `main()`
- `run()`

Use caution with names like `.load()`, `.open()`, `.save()`, `.build()`, and
`.parse()`. These may be generic noise or important domain methods depending
on receiver/type.

Preserve semantic signal:

- Prefer normalizing methods to `Type::method()` or `receiver.method()`.
- Remove unresolved generic nodes and incident inferred call edges.
- Keep domain-specific methods even when their names are short.
- Do not ignore tests wholesale.
- Downweight test fixture hubs, generated DTO leaves, file nodes, and setup
  helpers when judging architecture.
- Record every filtering rule so later readers understand what signal was
  removed.

## 4. Read `GRAPH_REPORT.md`

Process the generated report in this order:

1. Corpus summary and graph size.
2. Community hubs and labels.
3. God nodes.
4. Surprising connections.
5. Hyperedges.
6. Ambiguous edges.
7. Knowledge gaps and thin communities.
8. Suggested questions.

For each important finding, classify it as:

- `good`: intentional architecture worth preserving.
- `neutral`: real connection with acceptable tradeoffs.
- `bad`: real connection that indicates drift, duplication, or misplaced
  policy.
- `artifact`: graph/extraction/test/doc noise, not a codebase problem.
- `watchpoint`: not worth changing now, but worth tracking if the area grows.

## 5. Package First-Pass Findings

Create a small review corpus. Use whatever folder convention the repo already
uses; otherwise use an ignored scratch folder until the user chooses where
durable docs belong.

Recommended documents:

- `index.md`: read order, generated graph artifacts, and what each doc covers.
- `overview.md`: graph size, useful commands, top findings, and immediate
  interpretation.
- `god-nodes.md`: high-degree nodes, source paths, why each is central, and
  whether it is healthy, risky, fixture noise, or artifact.
- `surprising-connections.md`: each surprising edge, why it exists, how it is
  wired today, verdict, and possible fix.
- `question-answers.md`: concise answers to generated questions, grouped by
  subsystem when useful.
- `graph-shape-findings.md`: topology anomalies, bridge nodes, stragglers,
  artifacts, and watchpoints.

Each finding should include:

- graph evidence
- source evidence
- verdict
- recommended action

Avoid pasting large graph output. Link or name the generated artifact instead.

## 6. Query The Graph, Then Validate In Source

Use Graphify for discovery:

```sh
graphify explain "<node>" --graph graphify-out/graph.json
graphify path "<node-a>" "<node-b>" --graph graphify-out/graph.json
graphify query "<question>" --graph graphify-out/graph.json --budget 2000
graphify query "<question>" --dfs --graph graphify-out/graph.json --budget 2000
```

Then rewrite the graph result as a behavioral source question:

```sh
mgrep search "Where does this behavior happen, and which module owns it?" <likely/path>
rg "symbol_or_label" <likely/path>
```

Validation rules:

- Open source files and tests before accepting a graph edge.
- Prefer scoped searches over repo-wide searches.
- Search for observable behavior, not just labels.
- If graph and source disagree, trust source and mark the graph finding as an
  artifact or ambiguity.

## 7. Dispatch First-Wave Investigation Agents

Use focused agents after the first-pass corpus exists.

Suggested work units:

- one agent for god nodes
- one agent for surprising connections
- one or more agents for generated questions, grouped by subsystem
- one agent for graph-shape/topology anomalies if needed

Investigation agent prompt:

```text
Read the graph review docs and inspect source for the assigned finding.
Answer in concise terms. Explain why the graph connected these nodes, how the
code is wired today, whether the connection is good, neutral, bad, artifact, or
watchpoint, and what long-term change is warranted if any. Use source evidence.
```

Each investigation agent should produce:

- concise answer
- source paths and symbols
- verdict
- risk or opportunity
- recommended action

Human judgment is required to merge answers, discard weak claims, and decide
which findings deserve durable plans.

## 8. Run Second-Wave Refactor Synthesis

After the review corpus exists, ask multiple agents to independently identify
the top cleanup or refactor opportunities.

Synthesis prompt:

```text
Read the curated graph review docs. Return the top 3 architecture cleanup
opportunities. For each, explain the signal, whether it is source-validated or
graph noise, expected code impact, deletion test, smallest durable refactor,
and verification commands. Prefer high-leverage changes over broad rewrites.
```

Compare overlap across agents. Prefer opportunities that:

- remove duplicate policy
- deepen an existing good boundary
- reduce drift between similar flows
- simplify overloaded implementations
- keep public APIs stable
- make tests more clearly express product contracts

Do not create plans for:

- graph artifacts
- purely visual topology oddities
- one-off fixture noise
- speculative rewrites without source evidence

## 9. Write Refactor Plans

Create one plan per durable opportunity. Use the repo's existing planning
format if one exists; otherwise use this structure:

```markdown
# Title

## Purpose

One paragraph describing the intended improvement.

## Current State

Short bullets naming the current modules, flows, and tests.

## Problem

Explain the architectural risk, not just code size.

## Plan

Small ordered steps. Preserve good public seams unless the evidence says
otherwise.

## Acceptance

Observable end state and deletion tests.

## Verification

Commands and source-search checks.
```

Plan-review agent prompt:

```text
Review this refactor plan against the graph review docs and source. Find
ambiguity, missing acceptance criteria, overreach, and verification gaps.
Suggest concise edits only when they materially improve execution.
```

Accept review feedback only when it tightens scope, prevents ambiguity, or
catches missing validation.

## 10. Evaluate Graph Shape Carefully

Topology can reveal leads, but it is weaker than source-validated document
investigation.

Do:

- filter `contains` edges before judging boundaries
- filter generic nodes before computing bridge/god-node conclusions
- inspect low-degree nodes with mostly external edges
- inspect true cross-community bridge edges
- inspect files split across unrelated communities
- compare topology claims to source ownership

Do not:

- infer architecture from visual position alone
- trust HTML layout when coordinates are physics-generated
- refactor because a community looks skinny or oval
- treat test fixture hubs as product hubs without source validation
- treat archived docs as current behavior without checking source

Classify shape findings as real boundary, watchpoint, fixture noise, file-node
artifact, generic-label artifact, or not actionable.

## 11. Quality Gates

Graph build gates:

- graph has nonzero nodes and edges
- expected output files exist
- community labels are readable
- chunk failures are below threshold
- generated artifacts are ignored

Insight gates:

- every strong claim has graph evidence and source evidence
- every generic-node bridge is filtered or classified
- every surprising edge has a verdict
- every generated question has a concise answer or explicit deferral
- topology claims are not based on visual layout alone

Planning gates:

- every plan has purpose, current state, problem, plan, acceptance, and
  verification
- every plan has a deletion test or simplification test
- plan-review feedback has been considered
- docs lint passes for tracked docs

## 12. Failure Modes

- Generic nodes create false cross-community bridges.
- Method labels lose receiver/type identity.
- Test setup helpers become god nodes.
- Archived plans look like current architecture.
- Docs/tooling metadata gets mistaken for product coupling.
- Visual layout physics creates fake stragglers.
- Semantic search over-ranks docs because the query is too broad.
- Subagents return invalid JSON or unsupported speculation.
- Refactor plans optimize graph aesthetics instead of codebase maintainability.

## 13. Stop Conditions

Stop when:

- graph findings are classified as real, watchpoint, or artifact
- high-value graph questions are source-validated
- topology anomalies have been downranked or promoted with evidence
- the strongest opportunities are captured as concise plans
- no new source-validated opportunity outranks the current plan set
