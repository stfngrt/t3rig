# Changes from upstream

Source: https://github.com/mattpocock/skills at `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`, `skills/engineering/to-spec` (MIT, see `LICENSE`).
Every other file in this folder is unchanged.

- `SKILL.md`: removed `disable-model-invocation: true`, because Claude Code blocks a model's own call to such a skill and these seats are agents. With the flag removed and the skills installed in the shared checkout, every seat and the operator's own Claude sessions in this checkout can invoke it automatically, until per-seat skills land (#7).
- `SKILL.md`: the tracker and labels are read from `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md`.
- `SKILL.md`: the published spec gets `needs-approval` instead of `ready-for-agent`, and never `rig-queue`.
- `SKILL.md`: removed the "Exception" paragraph about prototype snippets (no `prototype` skill).
