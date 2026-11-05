# Changes from upstream

Source: https://github.com/mattpocock/skills at `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`, `skills/engineering/retro` (MIT, see `LICENSE`).
Every other file in this folder is unchanged.

- `SKILL.md`: removed `disable-model-invocation: true`, because Claude Code blocks a model's own call to such a skill and these seats are agents. With the flag removed and the skills installed in the shared checkout, every seat and the operator's own Claude sessions in this checkout can invoke it automatically, until per-seat skills land (#7).
- `SKILL.md`: removed step 1, which calls the `writing-for-agents` skill (not vendored), and the sentence in the Files list that points to it; renumbered the steps.
- `SKILL.md`: the sources are the ticket's issue thread and the seats' threads, not session logs.
- `SKILL.md`: step 3 gives the candidates to the lead's lessons (the closing comment's `Lessons:` line and `docs/lessons.md`) instead of presenting them to a user: small ones are applied by dev.impl in the commit, bigger ones become issues without `rig-queue`. The lead doesn't edit steering files itself.
- `SKILL.md`: named this rig's steering files (`rigs/self/culture.md`, `role.md`, skills) in the Files list.
