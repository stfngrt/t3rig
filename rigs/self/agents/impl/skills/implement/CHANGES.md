# Changes from upstream

Source: https://github.com/mattpocock/skills at `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`, `skills/engineering/implement` (MIT, see `LICENSE`).
Every other file in this folder is unchanged.

- `SKILL.md`: removed `disable-model-invocation: true`, because Claude Code blocks a model's own call to such a skill and these seats are agents. With the flag removed and the skills installed in the shared checkout, every seat and the operator's own Claude sessions in this checkout can invoke it automatically, until per-seat skills land (#7).
- `SKILL.md`: an ambiguous ticket is reported in the final reply, and dev.lead answers with the next task.
- `SKILL.md`: replaced the `code-review` call and "Commit your work" with reporting to dev.lead. dev.review is a separate seat, and impl never commits.
