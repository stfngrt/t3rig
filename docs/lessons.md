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

## 2026-11-06: [#17](https://github.com/stfngrt/t3rig/issues/17) Vendor the architecture skills (step 1)

- Upstream skills talk to "the user" in the agent's own conversation. In the rig nobody reads the
  lead's thread, so every such line has to point at the issue instead; check for it when vendoring.
- `#17` was queued while its blocker `#16` was still waiting for approval. The lead split off the
  part that didn't depend on it.

## 2026-11-06: [#16](https://github.com/stfngrt/t3rig/issues/16) `t3rig serve`

- Review found that the in-server watch loop could die silently and that the localhost page was
  open to DNS rebinding. Neither was in the issue. Applied: the reviewer's role now checks long-running
  loops and network listeners for both.
- `serve` couldn't be tried on the real rig while `t3rig watch` held its lock, and nobody opened the
  page in a browser. A UI change needs a person to look at it before it's called done.

## 2026-11-06: [#2](https://github.com/stfngrt/t3rig/issues/2) Short README

- Cutting the README broke 15 citations to its sections in ADRs and design docs. Cite docs pages,
  not README sections, since the README is now only an intro.

## 2026-11-06: [#9](https://github.com/stfngrt/t3rig/issues/9) Worktree and pull request per issue

- Review tried every `gh` and `git` command the roles name in a throwaway repo, and found the draft
  pull request step fails when nothing is committed. Workflow text with commands gets the same check.
- The docs build ran only after a merge to `main`, so pull requests could merge with a broken `-W`
  build. Applied: the docs workflow builds on pull requests too.

## 2026-11-06: [#16](https://github.com/stfngrt/t3rig/issues/16) `serve --host` (first pull request)

- The first change through the worktree and pull request loop went through as written; review
  posted its findings on the PR.
- IPv6 `--host` passed its own tests but got 400 on every request, because the tests built the
  allowed list and the middleware compared the bracketed form. Test an address through the real
  request path for each address family.

## 2026-11-06: [#18](https://github.com/stfngrt/t3rig/issues/18) Traceable sessions and watch health

- `watch`'s lock and state are keyed by the rig file's path, so in a worktree `ps` on the relative
  rig path said `watch` was down while it ran. Seats use the main checkout's rig path from their
  brief.
- T3 lists no archived threads, so `log --all` wasn't built; `--thread <id>` covers a known id.
- SSH pushes to GitHub kept hanging; pushing over HTTPS with `gh`'s credential helper worked.

## 2026-11-06: [#17](https://github.com/stfngrt/t3rig/issues/17) Seat-thread module and glossary renames

- The in-memory T3 adapter first returned list and show data as one dict, so a test could pass
  while real `ps` showed no pending requests. An in-memory adapter must keep the real adapter's
  data shapes apart.
- `#17`'s rename scope was added in a comment the lead missed when planning; read every comment
  before planning, not only the body and the last one.

## 2026-11-06: [#19](https://github.com/stfngrt/t3rig/issues/19) Calmer status page

- The preview host has only monospace fonts installed (`fc-match sans-serif` is Liberation Mono), so
  screenshots there don't show the real font. `gh` can't attach images to a PR; screenshots stay
  on the host.
- The page showed the queue by number after #18 moved the lead to board order. A change to how
  work is picked needs every view of the queue checked.

## 2026-11-06: [#22](https://github.com/stfngrt/t3rig/issues/22) Notices to dev.pm

- The in-memory T3 doesn't start a run on send, so tests couldn't show a notice loop that real T3
  would cause (an alert about the notify seat, noticed to itself). Review found it by reasoning about
  the real adapter; when an adapter skips a side effect, write down which ones.
- The issue's table said "a failed run", but only three things were ALERTs. Check an event list
  against what the code actually raises, not what its docs say.
