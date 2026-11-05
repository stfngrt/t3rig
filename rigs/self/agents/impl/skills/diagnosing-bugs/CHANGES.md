# Changes from upstream

Source: https://github.com/mattpocock/skills at `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`, `skills/engineering/diagnosing-bugs` (MIT, see `LICENSE`).
Every other file in this folder is unchanged.

- `SKILL.md`: questions and the ranked hypothesis list go in impl's final reply to dev.lead, not to the user.
- `SKILL.md`: removed the human-in-the-loop loop (item 10 and the Agent-runnable clause), because impl can't ask a person, and did not copy `scripts/hitl-loop.template.sh`.
- `SKILL.md`: step 8 (bisection harness) no longer says to `git bisect run`; it forbids `git bisect` and checking out other commits in the shared checkout, and the perf branch's "then bisect" became narrowing down with the harness.
- `SKILL.md`: the correct hypothesis is stated in the final reply, since dev.lead writes the commit message.
