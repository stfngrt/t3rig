# Changes from upstream

Source: https://github.com/mattpocock/skills at `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`, `skills/engineering/code-review` (MIT, see `LICENSE`).
Every other file in this folder is unchanged.

- `SKILL.md` line 13: the tracker is read from `docs/agents/issue-tracker.md`, not set up by `/setup-matt-pocock-skills`.
- `SKILL.md` line 19: the fixed point is named by dev.lead and defaults to the uncommitted changes (`git diff HEAD`, no commit list). Nothing named and nothing uncommitted is reported in the final reply instead of asked of the user.
- `SKILL.md` lines 29 and 32 (spec source): item 1 also names the issue in dev.lead's request, and item 4 skips the Spec sub-agent with "no spec available" instead of asking.
- `SKILL.md` still says "the user" and mentions pull requests, branches and GitLab in places (for example line 29, `!67`, and the description). Left as upstream; the rig has no PRs yet.
