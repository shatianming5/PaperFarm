# Historical Plans Archive

`docs/plans/` stores historical design and implementation snapshots captured during the early build-out.

These files are valuable as engineering history, but they are **not** the current runtime contract.

## Use This Folder For

- Understanding why earlier decisions were made
- Tracing feature evolution over time
- Reviewing deprecated alternatives

## Do Not Treat As Canonical Runtime Docs

Some historical plan examples still mention old internals (for example: `idea_program.md`, `experiment_program.md`, direct `control.json` authority, or pre-refactor orchestration helpers).

Current architecture and runtime boundaries should be taken from:

- `README.md`
- `docs/architecture-review.md`
- `docs/repo_inventory.md`

Rule of thumb:

- If historical plans conflict with current code/docs, follow current code/docs.
