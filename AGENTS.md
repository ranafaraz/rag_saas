## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Project agent workflow

- Start every substantial code task by activating this repository with Serena and reading Serena's initial instructions when the Serena MCP tools are available.
- Prefer Serena symbolic navigation and Graphify graph queries before broad file reads or repeated text search. Use `rg` when direct text search is the right tool.
- Keep `graphify-out/` local and untracked. Refresh it with `graphify update .` after meaningful code or architecture changes.
- Keep root `AGENTS.md` current when project conventions, setup commands, verification steps, or architecture boundaries change.
- When the conversation becomes long, expensive, or hard to resume, write a handover prompt that includes current goal, completed work, changed files, pending work, verification status, and known risks so a new session can continue cleanly.

## Product direction

- Build this as a horizontal open-core RAG SaaS for teams embedding tenant-scoped knowledge search and chat into their own web apps, mobile apps, CRMs, and internal tools.
- Treat education content as demo data only. Avoid hard-coding education-specific product assumptions into core APIs, billing, onboarding, or integration docs.
- Prioritize tenant isolation, API-key lifecycle, usage enforcement, integration ergonomics, evals, and observability before adding more connectors.

## Verification

- Frontend: run `npm run lint` from `frontend/`.
- Core backend: run `make test-core` when the Python environment is available.
- RAG backend: run `make test-rag` when the Python environment is available.
- Full backend: run `make test` before release branches when local services and dependencies are available.
