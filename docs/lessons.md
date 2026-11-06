# Lessons

What the self rig learned from each issue, one dated entry per issue, newest last. When the lead
closes an issue or labels it `needs-answer`, the entry is appended in the same commit (by dev.impl),
which also applies any lesson that is clearly right and small. Bigger lessons become new issues without
`rig-queue`. See {doc}`development`.

## 2026-11-05: [#2](https://github.com/stfngrt/t3rig/issues/2) Docs site and CI

Written afterwards by the lead; the issue predates the rule.

- A question for the operator was closed away with its issue. The rule now keeps such issues open
  with `needs-answer`. The README-shortening question is still open there.

## 2026-11-05: [#4](https://github.com/stfngrt/t3rig/issues/4) Design for #3

Written afterwards by the lead; the issue predates the rule.

- Each review fix round introduced new inconsistencies, so with two rounds the final edits go
  unreviewed.
- Seats can't read outside the repo, so the lead re-pastes OpenRig excerpts each round.
- `ruff format --check` also formats Python blocks in Markdown, so a doc can fail CI.

## 2026-11-05: [#5](https://github.com/stfngrt/t3rig/issues/5) Context management research

Written afterwards by the lead; the issue predates the rule.

none recorded (it predates the rule)

## 2026-11-05: [#7](https://github.com/stfngrt/t3rig/issues/7) Per-seat skills design

- The lead re-pasted excerpts every round; a shared, gitignored excerpts file inside the repo would
  save that.
- The two-round review cap leaves the last edits unreviewed; consider a third, re-check-only round.

## 2026-11-05: [#8](https://github.com/stfngrt/t3rig/issues/8) Project manager seat and vendored skills

- `t3rig up` without `--yes` starts the seats when there are no skill changes, so "show the plan"
  isn't safe. Make it never start without `--yes`, or add `--plan`.
- Each fix round broke something nearby, so dev.impl should re-read every edited paragraph whole
  before replying.

## 2026-11-05: [#10](https://github.com/stfngrt/t3rig/issues/10) Domain model as a glossary and ADRs

- Seats got different subsets of the OpenRig excerpts, so review flagged a correct citation. Give
  reviewers the same excerpt file as the implementer.

## 2026-11-05: [#11](https://github.com/stfngrt/t3rig/issues/11) Make the rig's learning stick

- Each rule added to one role contradicted `culture.md` or another role (pm vs lead on who talks to
  the operator, retro vs lessons). Applied: `culture.md` now says to check the culture and every role
  for the same topic when changing a rule.
- Bigger lessons from tonight became issues without `rig-queue` (linked in #11's closing comment).

## 2026-11-06: [#15](https://github.com/stfngrt/t3rig/issues/15) Run the rig from the tracker

- The ticket added an answer ping but didn't say what the pinged seat does next; review caught it.
  Applied: `dev.pm`'s role now says a ticket that adds a ping or label transition names what the
  receiving seat does with it.
- `watch` wasn't running when dev.impl finished, so the lead never heard and the operator had to
  nudge. Nothing tells a seat that `watch` is down.
- On first sight, `watch` pings for an issue with `rig-queue` even when it's already `in-progress`,
  so a restart re-pings work under way. Left as is: harmless, and useful if the lead crashed.
