# Changes from upstream

Source: https://github.com/mattpocock/skills at `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`, `skills/engineering/improve-codebase-architecture` (MIT, see `LICENSE`).
`HTML-REPORT.md` and `agents/openai.yaml` are unchanged.

- `SKILL.md`: removed `disable-model-invocation: true`, because Claude Code blocks a model's own call to such a skill and these seats are agents. With the flag removed and the skills installed in the shared checkout, every seat and the operator's own Claude sessions in this checkout can invoke it automatically, until per-seat skills land (#7).
- `SKILL.md`: the domain glossary is `docs/glossary.md`, not `GLOSSARY.md`, in the "domain language", "Explore" and vocabulary passages.
- `SKILL.md`: the report is still written to the OS temp directory, but isn't opened in a browser; dropped the `xdg-open`/`open`/`start` instruction. Its path and a summary are posted on the issue instead.
- `SKILL.md`: "If the user named a direction" is now "If the issue or the operator named a
  direction", because nobody reads the lead's thread.
- `SKILL.md`: the description no longer says the skill grills through a pick.
- `SKILL.md`: replaced "ask the user which to explore" and step 3, "Grilling loop", with "Post the candidates and hand off to the operator": post the candidates (with strength and the top recommendation) on the issue, add `needs-answer` and end the turn. The operator picks and is grilled through `dev.pm`, who writes the decisions on the issue.
- `SKILL.md`: added step 4, "Build the chosen refactors", through the dev.impl/dev.review loop. Its bullets are upstream's side effects, reworded because the lead doesn't edit files: a new or sharpened term, or an ADR for a rejected candidate, goes as exact text in the task for dev.impl. The ADR is recorded rather than offered, since the operator's reason arrives on the issue. "Create the file lazily" is dropped. The design-it-twice bullet is unchanged.
