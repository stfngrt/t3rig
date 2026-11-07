# Changes from upstream

Source: https://github.com/mattpocock/skills at `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`, `skills/engineering/domain-modeling` (MIT, see `LICENSE`).
`agents/openai.yaml` is unchanged. The copies under `lead/` and `pm/` are identical, because `t3rig` allows
one skill id on two seats only if the files match.

- `SKILL.md`: the glossary is the Sphinx page `docs/glossary.md` and the decisions are pages in
  `docs/adr/` with an `index.md` toctree, not a root `GLOSSARY.md`. Rewrote "File structure", and
  removed the multi-context `GLOSSARY-MAP.md` layout. Added that `docs/agents/` is left alone and that
  `-W` requires every `{term}` reference to resolve.
- `SKILL.md`: renamed `GLOSSARY.md` to `docs/glossary.md` in the description and the "Challenge",
  "Update inline" and "devoid of implementation details" passages.
- `GLOSSARY-FORMAT.md`: renamed the title, replaced "Structure" with a MyST `{glossary}` example (one
  block per subheading, `:sorted:`, extra term lines for synonyms, `_Avoid_` as text), and removed
  "Single vs multi-context repos". The Rules are unchanged except "Group terms under subheadings",
  which now says each subheading has its own `{glossary}` block.
- `ADR-FORMAT.md`: ADRs are pages of the site, new ones go in the `docs/adr/index.md` toctree, and the
  "create the directory lazily" sentence is dropped. The optional Status is a `**Status:**` line, not
  frontmatter.
- `SKILL.md`: added an "In this rig" section at the end. Only dev.impl edits files (dev.lead also writes excerpt files); any other seat writes the glossary entry or ADR text into the ticket and dev.impl applies it.
