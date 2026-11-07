# A per-task seat gets a thread per task

**Status:** accepted (#33); supersedes ADR 0001 for per-task seats

{doc}`ADR 0001 <0001-seats-are-threads>` made a {term}`seat` one T3 {term}`thread`, found by its
title. That piled context from every issue into the worker seats' threads. Seats named in
`per_task` in `rig.t3rig.yaml` now get a new thread per task: dev.impl one per issue, which lives
through its fix rounds, and dev.review one per review round. A {term}`task thread`'s title is the
seat's {term}`session name` plus the task (`dev-impl@self #18`, `dev-review@self #18 r2`), so it is
still found by title. The lead starts them with `t3rig send --new --task`, archives an issue's
task threads when it closes, and links them in the closing comment. Long-lived seats (here
dev.lead and dev.pm) keep one thread as in ADR 0001. Task threads start in the project root and
work in the issue's `.worktrees/<n>`, because T3's own worktrees sit outside the repo where the
seats' installed skills and the rig's paths aren't available. `max_parallel` (1 for now) limits how
many issues a per-task seat works at once.
