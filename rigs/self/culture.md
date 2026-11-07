# Team culture

This team develops t3rig, the tool it's running on. Read `README.md` first, then the pages it lists
under "Working on t3rig".

- Keep messages short, and report honestly what you did and didn't verify.
- Keep changes small, and match the existing code style.
- Keep process light. Process is there to get work done, not for its own sake. dev.pm speaks for
  the operator, so a decision, approval or close that dev.pm gives on the operator's behalf counts
  as the operator's. Small fixes (a wording change in a role, the culture or a doc) don't need an
  issue: commit them straight to `main` with a clear message.
- Don't commit, push, or change anything outside this repo except where your task says to.
- A restricted seat stops for approval when it reads files outside this repo, so don't ask it to. If
  it needs something from outside, dev.lead reads it, writes the relevant text
  to `<main checkout>/.t3rig/excerpts/<n>.md` for issue `<n>`, and gives the seat that file's full
  path, so it resolves from a worktree.
- Among dev.lead, dev.impl and dev.review, only dev.impl edits files; dev.lead's one exception is
  those excerpt files.
- Only dev.pm grills the operator or talks to them about new work. Other seats put questions in their
  final reply to their dispatcher. The lead still takes tasks from the operator, and posts its
  questions for the operator with `needs-answer` on issues; the operator answers them with dev.pm.
- Each issue is worked in its own git worktree, `.worktrees/<N>` on the branch `issue-<N>`, and the
  main checkout stays on `main`. Only dev.lead creates, commits in and removes worktrees. Never run
  anything that disturbs the main checkout or another worktree, such as `git stash`, `git checkout`,
  `git switch`, `git reset` or `git clean`.
- The rig posts to GitHub under the operator's account until it has its own bot identity. So start
  every issue body, comment, pull request description and pull request review you write with
  `🤖 <seat> (t3rig) · <thread link>`, such as
  `🤖 dev.lead (t3rig) · https://app.t3.codes/threads/...`. That tells the operator's posts and the
  rig's apart, and leads to the session that wrote each one. Get your thread link once per thread:
  it's the `link` in your row of `t3rig ps --json <rig>`, run with the same command and rig path as
  the `send` command in your brief. A per-task seat (dev.impl, dev.review) takes the row whose
  `task` is its thread's task. Commits the lead makes end with a trailer
  `Rig-Session: dev.lead <thread link>`, and also one for dev.impl's task thread when dev.impl
  wrote the change, naming the task: `Rig-Session: dev.impl #18 <thread link>`.
- Review rounds: at most `review_rounds` from `rig.t3rig.yaml` (2 here) per change, unless the issue
  body has a line `Review rounds: N`. Round 1 reviews the whole change; later rounds check only the
  fixes and what they broke, with no new nitpicks. At the limit, remaining findings go under "Left
  open" in the closing comment, or into a new issue if they're real bugs, and the lead decides
  whether the change ships.
- Don't write to Claude Code's auto memory, which seats share with the operator's own sessions (you
  still read it at startup). Your durable record is the issues and `docs/lessons.md`.
- When you change a rule in one role or in this file, check this file and every role for the same
  topic, and keep them consistent.
