# Changes from upstream

Source: https://github.com/mattpocock/skills at `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`, `skills/engineering/wayfinder` (MIT, see `LICENSE`).
Every other file in this folder is unchanged.

- `SKILL.md`: removed `disable-model-invocation: true`, because Claude Code blocks a model's own call to such a skill and these seats are agents. With the flag removed and the skills installed in the shared checkout, every seat and the operator's own Claude sessions in this checkout can invoke it automatically, until per-seat skills land (#7).
- `SKILL.md`: the tracker is read from `docs/agents/issue-tracker.md`, not set up by `/setup-matt-pocock-skills`; dropped the local-markdown default.
- `SKILL.md`: removed the `prototype` ticket type and its skill call (no `prototype` skill is vendored, and pm never edits code). The word "prototype" remains in the `task` type's description.
- `SKILL.md`: `research` tickets are resolved by a fresh-context subagent that posts its findings on the ticket, with no `research` skill and no `research/<name>` branch.
- `SKILL.md`: added an "In this rig" section at the end: HITL tickets go to the operator, with `needs-answer` when they're away, and map issues never get `rig-queue`.
